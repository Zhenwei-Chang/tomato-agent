import hashlib
import importlib.util
from functools import lru_cache
from pathlib import Path
from ..schemas.common import ToolFailure, ErrorCode


@lru_cache(maxsize=16)
def load_source(path: Path):
    if not path.is_file():
        raise ToolFailure(ErrorCode.DEPENDENCY_ERROR, "Existing source module unavailable", path=str(path))
    name = "_tomato_asset_" + hashlib.sha256(str(path).encode()).hexdigest()[:16]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=32)
def file_hash(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def json_clean(value):
    """Convert pandas/numpy NaN to JSON null, never emit nonstandard NaN."""
    import json
    import numpy as np
    import pandas as pd
    if isinstance(value, dict):
        return {str(k): json_clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_clean(v) for v in value]
    if isinstance(value, np.ndarray):
        return json_clean(value.tolist())
    if value is None or (not isinstance(value, (str, dict, list)) and pd.isna(value)):
        return None
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (pd.Timestamp, Path)):
        return str(value)
    return value
