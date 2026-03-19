import json
import os

def load_data(date, base_path="."):
    """
    Loads features.json and semantic_chunks.json for a given date.
    """
    candidate_roots = [
        base_path,
        os.path.join(base_path, "data"),
    ]

    features_path = None
    chunks_path = None

    for root in candidate_roots:
        candidate_features = os.path.join(root, "features", f"{date}.json")
        candidate_chunks = os.path.join(root, "semantic_chunks", f"{date}.json")
        if os.path.exists(candidate_features) and os.path.exists(candidate_chunks):
            features_path = candidate_features
            chunks_path = candidate_chunks
            break

    if features_path is None or chunks_path is None:
        searched = ", ".join(os.path.abspath(root) for root in candidate_roots)
        raise FileNotFoundError(
            f"Could not find feature/chunk files for {date}. Searched roots: {searched}"
        )

    with open(features_path, "r", encoding="utf-8") as f:
        features_data = json.load(f)

    with open(chunks_path, "r", encoding="utf-8") as f:
        chunks_data = json.load(f)

    return features_data, chunks_data
