import json
from rank_bm25 import BM25Okapi
from rag.models import FAQEntry, FAQIndex, MatchResult
from rag.indexer import tokenize

DIRECT_THRESHOLD = 0.85
FEW_SHOT_THRESHOLD = 0.60


class RAGRetriever:
    def __init__(self, index_path: str = "rag/faq_index.json"):
        with open(index_path, encoding="utf-8") as f:
            data = json.load(f)
        self._index = FAQIndex(**data)
        self._bm25 = BM25Okapi([doc.tokens for doc in self._index.corpus])
        # Build lookup: entry_id → FAQEntry
        self._entry_map: dict[str, FAQEntry] = {e.id: e for e in self._index.entries}

        # Precompute self-score for each corpus doc
        self._doc_self_scores: list[float] = []
        for i, doc in enumerate(self._index.corpus):
            if doc.tokens:
                score = float(self._bm25.get_scores(doc.tokens)[i])
                self._doc_self_scores.append(score)
            else:
                self._doc_self_scores.append(1.0)

    def search(self, query: str) -> MatchResult:
        tokens = tokenize(query)
        if not tokens:
            return MatchResult(tier="MISS", entry=None, score=0.0, top_k=[])

        raw_scores = self._bm25.get_scores(tokens)

        # Deduplicate: keep best score per entry_id, and track the best doc index
        entry_best: dict[str, float] = {}
        entry_best_doc_idx: dict[str, int] = {}
        for i, doc in enumerate(self._index.corpus):
            score = float(raw_scores[i])
            if score > entry_best.get(doc.entry_id, 0.0):
                entry_best[doc.entry_id] = score
                entry_best_doc_idx[doc.entry_id] = i

        if not entry_best or max(entry_best.values()) == 0.0:
            return MatchResult(tier="MISS", entry=None, score=0.0, top_k=[])

        # Rank entries by score descending
        ranked = sorted(entry_best.items(), key=lambda x: x[1], reverse=True)
        ranked_entries = [self._entry_map[eid] for eid, _ in ranked if eid in self._entry_map]

        if not ranked_entries:
            return MatchResult(tier="MISS", entry=None, score=0.0, top_k=[])

        best_entry = ranked_entries[0]
        top_k = ranked_entries[:3]
        best_raw = entry_best[best_entry.id]

        # Normalize by the self-score of the specific corpus doc that best matched
        best_doc_idx = entry_best_doc_idx[best_entry.id]
        doc_self = self._doc_self_scores[best_doc_idx]
        normalized = best_raw / doc_self if doc_self > 0 else 0.0
        # Cap at 1.0 (floating point can exceed slightly for near-exact matches)
        normalized = min(normalized, 1.0)

        # has_variables entries are capped below DIRECT threshold
        effective_score = normalized
        if best_entry.has_variables:
            effective_score = min(normalized, FEW_SHOT_THRESHOLD - 0.01)

        if effective_score >= DIRECT_THRESHOLD:
            return MatchResult(tier="DIRECT", entry=best_entry, score=normalized, top_k=[])
        elif normalized >= FEW_SHOT_THRESHOLD:
            return MatchResult(tier="FEW_SHOT", entry=best_entry, score=normalized, top_k=top_k)
        else:
            return MatchResult(tier="MISS", entry=None, score=normalized, top_k=[])
