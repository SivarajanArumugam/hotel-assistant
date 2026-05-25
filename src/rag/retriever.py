import json
import logging
import os
from typing import List, Optional, Tuple, Dict

from core.config import settings
from agent.prompts import QUERY_REWRITE_PROMPT

logger = logging.getLogger(__name__)

_chroma_client = None
_collection = None
_embedding_model = None
_bm25_corpus = None
_bm25_index = None
_cross_encoder = None
_domain_description: Optional[str] = None


def _get_chroma_collection():
    global _chroma_client, _collection
    if _collection is None:
        import chromadb
        _chroma_client = chromadb.PersistentClient(path=settings.chroma_db_path)
        _collection = _chroma_client.get_collection(settings.collection_name)
    return _collection


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer(settings.embedding_model)
    return _embedding_model


def _get_bm25():
    global _bm25_corpus, _bm25_index
    if _bm25_index is None:
        from rank_bm25 import BM25Okapi
        col = _get_chroma_collection()
        results = col.get(include=["documents"])
        _bm25_corpus = results["documents"]
        tokenized = [doc.lower().split() for doc in _bm25_corpus]
        _bm25_index = BM25Okapi(tokenized)
    return _bm25_index, _bm25_corpus


def _get_cross_encoder():
    global _cross_encoder
    if _cross_encoder is None:
        from sentence_transformers import CrossEncoder
        _cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-2-v2")
    return _cross_encoder


def _get_domain_description() -> str:
    global _domain_description
    if _domain_description is None:
        meta_path = os.path.join(settings.chroma_db_path, "doc_meta.json")
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            _domain_description = data.get("domain_description", "")
        except Exception:
            _domain_description = ""
    return _domain_description


def _rewrite_query(query: str) -> str:
    try:
        from groq import Groq
        domain_desc = _get_domain_description()
        prompt = QUERY_REWRITE_PROMPT.format(domain_description=domain_desc, query=query)
        client = Groq(api_key=settings.groq_api_key)
        completion = client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        return completion.choices[0].message.content.strip()
    except Exception:
        return query


def _rrf_merge(dense_ids: List[str], bm25_ids: List[str], k: int = 60) -> List[str]:
    scores: Dict[str, float] = {}
    for rank, doc_id in enumerate(dense_ids):
        scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (k + rank + 1)
    for rank, doc_id in enumerate(bm25_ids):
        scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (k + rank + 1)
    return sorted(scores, key=lambda x: scores[x], reverse=True)


def retrieve_context(query: str) -> str:
    """
    Runs the full 6-stage hybrid RAG pipeline.
    Returns formatted context string or "[RAG unavailable: ...]" on error.
    """
    try:
        words = query.strip().split()
        if len(words) <= 10:
            rewritten_query = _rewrite_query(query)
        else:
            rewritten_query = query

        col = _get_chroma_collection()
        embed_model = _get_embedding_model()

        bge_query = f"Represent this sentence for searching relevant passages: {rewritten_query}"
        query_embedding = embed_model.encode([bge_query])[0].tolist()

        dense_results = col.query(
            query_embeddings=[query_embedding],
            n_results=min(10, col.count()),
            include=["documents"],
        )
        dense_ids = dense_results["ids"][0]
        dense_docs_map = dict(zip(dense_results["ids"][0], dense_results["documents"][0]))

        bm25_index, bm25_corpus = _get_bm25()
        all_ids = col.get(include=[])["ids"]
        tokenized_query = query.lower().split()
        bm25_scores = bm25_index.get_scores(tokenized_query)
        bm25_ranked = sorted(range(len(bm25_scores)), key=lambda i: bm25_scores[i], reverse=True)[:10]
        bm25_ids = [all_ids[i] for i in bm25_ranked]

        merged_ids = _rrf_merge(dense_ids, bm25_ids)[:6]

        all_docs = col.get(ids=merged_ids, include=["documents"])
        doc_map = dict(zip(all_docs["ids"], all_docs["documents"]))
        merged_docs = [doc_map[mid] for mid in merged_ids if mid in doc_map]

        cross_encoder = _get_cross_encoder()
        pairs = [(query, doc) for doc in merged_docs]
        scores = cross_encoder.predict(pairs)
        reranked = sorted(zip(scores, merged_docs), key=lambda x: x[0], reverse=True)
        top_docs = [doc for _, doc in reranked[: settings.top_k_retrieval]]

        return "\n\n---\n\n".join(top_docs)

    except Exception as e:
        return f"[RAG unavailable: {e}]"
