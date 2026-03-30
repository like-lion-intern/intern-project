# rerank.py
from __future__ import annotations

from typing import List
import re
import os

from dotenv import load_dotenv

load_dotenv()

_TRANSFORMERS_AVAILABLE = True
try:
    import torch
    import torch.nn.functional as F
    from torch import Tensor
    from transformers import AutoTokenizer, AutoModel
except Exception:
    _TRANSFORMERS_AVAILABLE = False
    torch = None
    F = None
    Tensor = None
    AutoTokenizer = None
    AutoModel = None


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


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

    def rerank(self, query: str, passages: List[str], top_k: int = 3) -> List[str]:
        if not passages:
            return []
        if len(passages) <= top_k:
            return passages[:top_k]

        query_emb = self.get_embeddings([query], input_type="query")
        passage_embs = self.get_embeddings(passages, input_type="passage")

        scores = (query_emb @ passage_embs.T).squeeze(0)
        top_indices = torch.topk(scores, min(top_k, len(passages))).indices.tolist()
        return [passages[i] for i in top_indices]


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


def _simple_keyword_rerank(query: str, candidates: List[str], top_k: int = 3) -> List[str]:
    query_terms = set(re.findall(r"[가-힣A-Za-z0-9]+", query.lower()))
    scored = []

    for idx, cand in enumerate(candidates):
        clean = _strip_segment_prefix(cand).lower()
        cand_terms = set(re.findall(r"[가-힣A-Za-z0-9]+", clean))
        overlap = len(query_terms & cand_terms)

        # 길이가 너무 짧은 근거는 살짝 불리하게
        length_bonus = min(len(clean) / 100.0, 1.0)
        score = overlap + 0.1 * length_bonus

        scored.append((score, idx, cand))

    scored.sort(key=lambda x: (-x[0], x[1]))
    return [cand for _, _, cand in scored[:top_k]]


def rerank_evidence(item_context: str, candidates: List[str], top_k: int = 3) -> List[str]:
    if not candidates:
        return []

    deduped = []
    seen = set()
    for c in candidates:
        norm = _normalize_text(c)
        if norm and norm not in seen:
            seen.add(norm)
            deduped.append(c)

    if len(deduped) <= top_k:
        return deduped[:top_k]

    reranker = get_reranker()

    if reranker is None:
        return _simple_keyword_rerank(item_context, deduped, top_k=top_k)

    original_map = []
    clean_candidates = []
    for c in deduped:
        cleaned = _strip_segment_prefix(c)
        original_map.append((cleaned, c))
        clean_candidates.append(cleaned)

    try:
        top_results = reranker.rerank(item_context, clean_candidates, top_k=top_k)
    except Exception:
        return _simple_keyword_rerank(item_context, deduped, top_k=top_k)

    final_output = []
    used = set()
    for res in top_results:
        res_norm = _normalize_text(res)
        for cleaned, original in original_map:
            if _normalize_text(cleaned) == res_norm and original not in used:
                final_output.append(original)
                used.add(original)
                break

    if not final_output:
        return _simple_keyword_rerank(item_context, deduped, top_k=top_k)

    return final_output[:top_k]
