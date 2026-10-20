import numpy as np


def standardized_similarity(query, candidates, stats):
    columns = stats['features']
    mean = np.asarray(stats['mean'], dtype=float)
    scale = np.asarray(stats['scale'], dtype=float)
    q = (np.asarray([query[c] for c in columns], dtype=float) - mean) / scale
    x = (candidates[columns].to_numpy(float) - mean) / scale
    distance = np.sqrt(np.nanmean((x - q) ** 2, axis=1))
    return np.exp(-distance)


def cosine_similarity(query, candidates):
    q = np.asarray(query, dtype=float)
    x = np.asarray(candidates, dtype=float)
    denominator = np.linalg.norm(x, axis=1) * np.linalg.norm(q)
    score = np.divide(x @ q, denominator, out=np.zeros(len(x), dtype=float), where=denominator > 0)
    return np.clip(score, 0, 1)


def hybrid_score(components: dict[str, np.ndarray], weights: dict[str, float]):
    total = sum(float(weights[name]) for name in components)
    if total <= 0:
        raise ValueError('Similarity weights must sum to a positive value')
    return sum(components[name] * float(weights[name]) for name in components) / total


def weighted_mean(values, weights):
    values = np.asarray(values, dtype=float); weights = np.asarray(weights, dtype=float)
    valid = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    return float(np.average(values[valid], weights=weights[valid])) if valid.any() else None
