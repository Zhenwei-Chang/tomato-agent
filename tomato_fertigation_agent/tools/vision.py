from .base import Outcome, RGB_LIMITS
from ..adapters.loading import file_hash
from pathlib import Path


def image_evidence(data,result):
    image = Path(result['image_path'])
    evidence = [{'evidence_id':'input_rgb','source':str(image),'attributes':{'sha256':file_hash(image),'scope':'view'}}]
    if result['embedding_source'].endswith('cache'):
        evidence.append(data.evidence('data/processed/image_embeddings.csv',result['image_path']))
    return evidence


def get_image_embedding(data, vision, args):
    result = vision.embedding(args)
    return Outcome(result,'view',evidence=image_evidence(data,result),
                   model_version='v05_imagenet_resnet18_frozen', confidence='UNKNOWN',
                   reasons=['512D representation; retrieval similarity is not calibrated confidence'], limitations=RGB_LIMITS)


def analyze_rgb(data, vision, args):
    result = vision.analyze(args)
    return Outcome(result,'view',model_version='v05_frozen_resnet18_heads',confidence='LOW',
                   warnings=RGB_LIMITS[:1], reasons=['Unresolved background shortcut and domain shift'],
                   evidence=image_evidence(data,result)+[data.evidence('outputs/checkpoints/'+p) for p in result['model_heads']],
                   limitations=RGB_LIMITS+['Current and future heads estimate aggregated View targets; no individual plant crop','Estimates are not observed phenotype'])
