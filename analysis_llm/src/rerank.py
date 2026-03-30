# rerank.py
from __future__ import annotations

import os
import re
from typing import Any, List

from dotenv import load_dotenv

load_dotenv()

_TRANSFORMERS_AVAILABLE = True
try:
    import torch
    import torch.nn.functional as F
    from torch import Tensor
    from transformers import AutoModel, AutoTokenizer
except Exception:
    _TRANSFORMERS_AVAILABLE = False
    torch = None
    F = None
    Tensor = None
    AutoTokenizer = None
    AutoModel = None


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


def _candidate_text(candidate: Any) -> str:
    if isinstance(candidate, dict):
        return _normalize_text(candidate.get("span_text", ""))
    return _normalize_text(candidate)


def average_pool(last_hidden_states: "Tensor", attention_mask: "Tensor") -> "Tensor":
    last_hidden = last_hidden_states.masked_fill(~attention_mask[..., None].bool(), 0.0)
    denom = attention_mask.sum(dim=1)[..., None].clamp(min=1)
    return last_hidden.sum(dim=1) / denom


class E5Reranker:
    def __init__(self, model_name: str = None):
        if not _TRANSFORMERS_AVAILABLE:
            raise RuntimeError("transformers/torch is not available")

        model_name = model_name or os.getenv("E5_MODEL_NAME", "intfloat/multilingual-e5-small")
        self.model_name = model_name
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name)
        self.model.to(self.device)
        self.model.eval()

    def get_embeddings(self, texts: List[str], input_type: str = "query") -> "Tensor":
        prefix = "query: " if input_type == "query" else "passage: "
        prefixed_texts = [prefix + _normalize_text(text) for text in texts]

        batch_dict = self.tokenizer(
            prefixed_texts,
            max_length=512,
            padding=True,
            truncation=True,
            return_tensors="pt",
        )
        batch_dict = {k: v.to(self.device) for k, v in batch_dict.items()}

        with torch.no_grad():
            outputs = self.model(**batch_dict)
            embeddings = average_pool(outputs.last_hidden_state, batch_dict["attention_mask"])

        embeddings = F.normalize(embeddings, p=2, dim=1)
        return embeddings

    def score(self, query: str, passages: List[str]) -> List[float]:
        if not passages:
            return []

        query_emb = self.get_embeddings([query], input_type="query")
        passage_embs = self.get_embeddings(passages, input_type="passage")
        scores = (query_emb @ passage_embs.T).squeeze(0)
        return scores.tolist()


_reranker = None
_reranker_failed = False


def get_reranker(model_name: str = None):
    global _reranker, _reranker_failed
    if _reranker_failed:
        return None
    if _reranker is None:
        try:
            _reranker = E5Reranker(model_name=model_name)
        except Exception:
            _reranker_failed = True
            _reranker = None
    return _reranker


def _strip_segment_prefix(text: str) -> str:
    text = _normalize_text(text)
    if text.startswith("[segment ") and "]" in text:
        return text.split("]", 1)[1].strip()
    return text


def _simple_keyword_scores(query: str, candidates: List[Any]) -> List[float]:
    query_terms = set(re.findall(r"[가-힣A-Za-z0-9]+", query.lower()))
    scores: List[float] = []

    for candidate in candidates:
        clean = _strip_segment_prefix(_candidate_text(candidate)).lower()
        cand_terms = set(re.findall(r"[가-힣A-Za-z0-9]+", clean))
        overlap = len(query_terms & cand_terms)
        length_bonus = min(len(clean) / 100.0, 1.0)
        local_bonus = 0.05 * float(candidate.get("local_score", 0.0)) if isinstance(candidate, dict) else 0.0
        scores.append(overlap + 0.1 * length_bonus + local_bonus)

    return scores


def rerank_evidence(item_context: str, candidates: List[Any], top_k: int = 3) -> List[Any]:
    if not candidates:
        return []

    deduped: List[Any] = []
    seen = set()
    for candidate in candidates:
        text = _candidate_text(candidate)
        polarity = candidate.get("polarity", "") if isinstance(candidate, dict) else ""
        dedupe_key = (text, polarity)
        if text and dedupe_key not in seen:
            seen.add(dedupe_key)
            deduped.append(candidate)

    if not deduped:
        return []

    reranker = get_reranker()
    clean_candidates = [_strip_segment_prefix(_candidate_text(candidate)) for candidate in deduped]

    try:
        if reranker is not None:
            scores = reranker.score(item_context, clean_candidates)
        else:
            scores = _simple_keyword_scores(item_context, deduped)
    except Exception:
        scores = _simple_keyword_scores(item_context, deduped)

    ranked = sorted(
        zip(deduped, scores),
        key=lambda item: (-float(item[1]), -float(item[0].get("local_score", 0.0)) if isinstance(item[0], dict) else 0.0),
    )

    output = []
    for candidate, score in ranked[:top_k]:
        if isinstance(candidate, dict):
            enriched = dict(candidate)
            enriched["rerank_score"] = round(float(score), 4)
            output.append(enriched)
        else:
            output.append({"span_text": _candidate_text(candidate), "rerank_score": round(float(score), 4)})

    return output
