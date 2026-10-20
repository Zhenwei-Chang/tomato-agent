from datetime import timedelta
from functools import lru_cache
import joblib
import numpy as np
import pandas as pd
from .loading import load_source, file_hash
from ..schemas.common import ToolFailure, ErrorCode


class ModelAdapter:
    def __init__(self, data):
        self.data = data
        self.root = data.root

    @lru_cache(maxsize=4)
    def model(self, filename):
        path = self.root / 'outputs/checkpoints' / filename
        if not path.is_file():
            raise ToolFailure(ErrorCode.MODEL_NOT_AVAILABLE, 'Required saved checkpoint missing', artifact=str(path))
        try:
            return joblib.load(path)
        except Exception as exc:
            raise ToolFailure(ErrorCode.MODEL_NOT_AVAILABLE, 'Checkpoint cannot be loaded', exception_type=type(exc).__name__) from exc

    def height(self, args):
        filename = 'height_t7_exact__B0__categorical__gradient_boosting.joblib'
        model = self.model(filename)
        columns = list(model.feature_names_in_)
        features, values, observed = self.data.prediction_features(args, columns)
        predicted = float(model.predict(features)[0])
        if not np.isfinite(predicted):
            raise ToolFailure(ErrorCode.INTERNAL_ERROR, 'Model returned a nonfinite prediction')
        return {'plant_id':args.plant_id,'year':args.year,'date':str(args.date),
                'prediction':{'height_t7_cm':predicted,'target_date':str(args.date+timedelta(days=7)), 'horizon_days':7},
                'current_state':{'height_t0_cm':values['height_t0'],'lai_t0':values['lai_t0']},
                'input_window':{'start':values['env_window_start'],'end':values['env_window_end']},
                'model':{'name':'HistGradientBoostingRegressor','version':'v03_locked_B0','artifact':str(self.root/'outputs/checkpoints'/filename),'sha256':file_hash(self.root/'outputs/checkpoints'/filename),'n_features':len(columns)},
                'source_status':str(observed.target_source_status),'forecast_assumes_current_state_available':True}


class VisionAdapter:
    def __init__(self, data, models):
        self.data, self.models = data, models
        self.encoder = None
        self.transform = None

    def resolve(self, args):
        if args.requested_scope.value != 'view':
            raise ToolFailure(ErrorCode.UNSUPPORTED_SCOPE, 'RGB supports View-level results only; no single-plant RGB mapping')
        views = self.data.table('data/indexes/view_date_dataset.csv')
        if args.image_path:
            from pathlib import Path
            path = Path(args.image_path).resolve()
            allowed = (self.data.settings.raw, self.data.settings.inputs.resolve())
            if not any(path == root or root in path.parents for root in allowed):
                raise ToolFailure(ErrorCode.INVALID_ARGUMENT, 'Image must be under configured raw root or agent inputs directory')
            rows = views[views.image_path.map(lambda x: Path(x).resolve() == path)]
        else:
            rows = views[(views.view_id == args.view_id) & (views.image_date == str(args.date))]
            if len(rows) != 1:
                raise ToolFailure(ErrorCode.DATA_NOT_FOUND, 'Exact View/date representative image unavailable')
            from pathlib import Path
            path = Path(rows.iloc[0].image_path)
        if not path.is_file():
            raise ToolFailure(ErrorCode.DATA_NOT_FOUND, 'Image file unavailable', path=str(path))
        metadata = rows.iloc[0][['view_id','image_date','year','physical_view_id']].to_dict() if len(rows) == 1 else {'view_id':None,'image_date':None,'year':None,'physical_view_id':'UNKNOWN'}
        return path, metadata

    def load_encoder(self):
        if self.encoder is None:
            import torch
            from pathlib import Path
            weights = Path(torch.hub.get_dir())/'checkpoints/resnet18-f37072fd.pth'
            if not weights.is_file():
                raise ToolFailure(ErrorCode.MODEL_NOT_AVAILABLE, 'Frozen ImageNet weights missing from local cache; no automatic download')
            source = load_source(self.data.root/'src/models/vision.py')
            transforms = load_source(self.data.root/'src/data/vision_dataset.py')
            self.encoder = source.ResNet18Regressor('frozen', pretrained=True).cpu().eval()
            self.transform = transforms.build_image_transform(False)
        return self.encoder

    def embedding(self, args):
        path, metadata = self.resolve(args)
        table = self.data.table('data/processed/image_embeddings.csv')
        from pathlib import Path
        rows = table[table.image_path.map(lambda x: Path(x).resolve() == path.resolve())]
        if len(rows) == 1:
            vector = rows[[f'embedding_{i}' for i in range(512)]].to_numpy(float)[0]
            source = 'v05_frozen_backbone_cache'
        else:
            import torch
            from PIL import Image, UnidentifiedImageError
            encoder = self.load_encoder()
            try:
                with Image.open(path) as im:
                    tensor = self.transform(im.convert('RGB')).unsqueeze(0)
            except (OSError, UnidentifiedImageError) as exc:
                raise ToolFailure(ErrorCode.INVALID_ARGUMENT, 'Image cannot be decoded') from exc
            with torch.no_grad():
                vector = encoder.embedding(tensor).numpy().reshape(-1)
            source = 'live_frozen_backbone_forward'
        if vector.shape != (512,) or not np.isfinite(vector).all():
            raise ToolFailure(ErrorCode.MODEL_NOT_AVAILABLE, 'Embedding has invalid dimensions or nonfinite values')
        return {'image_path':str(path), **metadata, 'embedding':vector.tolist(), 'dimension':512,'encoder':'ImageNet ResNet18 frozen backbone','embedding_source':source}

    def analyze(self, args):
        data = self.embedding(args)
        x = np.asarray(data['embedding']).reshape(1,-1)
        current = self.models.model('v05__current__frozen_resnet18_head.joblib')
        future = self.models.model('v05__future__frozen_resnet18_head.joblib')
        data['prediction'] = {'current_view_mean_height_cm':float(current.predict(x)[0]), 'future_view_mean_height_t7_cm':float(future.predict(x)[0]), 'horizon_days':7}
        data['model_heads'] = ['v05__current__frozen_resnet18_head.joblib','v05__future__frozen_resnet18_head.joblib']
        if not args.include_embedding:
            data.pop('embedding')
        return data
