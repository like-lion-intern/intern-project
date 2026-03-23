"""
Evidence reranking module.

item_context와 evidence 후보 텍스트 사이의 의미적 유사도를 계산하여
가장 관련성 높은 상위 k개의 evidence를 선택한다.

E5-small 임베딩 기반으로 코사인 유사도를 계산하며,
모델 로드 실패 시 키워드 오버랩 기반 fallback을 사용한다.
"""
from __future__ import annotations

import math
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

# ─── 캐시 ──────────────────────────────────────────────────────────────────
_rerank_model = None
_rerank_loaded = False


def _get_rerank_model():
    global _rerank_model, _rerank_loaded
    if _rerank_loaded:
        return _rerank_model
    _rerank_loaded = True
    try:
        from sentence_transformers import SentenceTransformer
        _rerank_model = SentenceTransformer(
            "intfloat/multilingual-e5-small",
            device="cpu",
        )
        logger.info("[rerank] e5-small 로드 완료")
    except Exception as exc:
        logger.warning("[rerank] 모델 로드 실패, keyword fallback 사용: %s", exc)
        _rerank_model = None
    return _rerank_model


# ─── 코사인 유사도 ──────────────────────────────────────────────────────────
def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ─── keyword overlap fallback ──────────────────────────────────────────────
def _keyword_score(query: str, text: str) -> float:
    q_words = set(query.split())
    t_words = set(text.split())
    if not q_words:
        return 0.0
    return len(q_words & t_words) / len(q_words)


# ─── 메인 함수 ──────────────────────────────────────────────────────────────
def rerank_evidence(
    item_context: str,
    candidates: List[str],
    top_k: int = 3,
) -> List[str]:
    """
    item_context와 의미적으로 가장 유사한 candidates 상위 top_k개를 반환.

    Args:
        item_context: 항목 평가 기준 설명 텍스트
        candidates: evidence 후보 문자열 목록
        top_k: 반환할 상위 개수

    Returns:
        유사도 순으로 정렬된 상위 top_k개의 evidence 문자열
    """
    if not candidates:
        return []
    if len(candidates) <= top_k:
        return candidates

    model = _get_rerank_model()

    if model is not None:
        try:
            query = f"query: {item_context}"
            docs = [f"passage: {c}" for c in candidates]
            all_texts = [query] + docs
            vecs = model.encode(all_texts, batch_size=32, normalize_embeddings=True)
            q_vec = vecs[0].tolist()
            scored = [
                (_cosine(q_vec, vecs[i + 1].tolist()), candidates[i])
                for i in range(len(candidates))
            ]
            scored.sort(key=lambda x: x[0], reverse=True)
            return [text for _, text in scored[:top_k]]
        except Exception as exc:
            logger.warning("[rerank] 임베딩 실패, keyword fallback: %s", exc)

    # fallback: keyword overlap
    scored = [(_keyword_score(item_context, c), c) for c in candidates]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [text for _, text in scored[:top_k]]
