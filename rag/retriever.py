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

    def search(self, query: str) -> MatchResult:
        tokens = tokenize(query)
        if not tokens:
            return MatchResult(tier="MISS", entry=None, score=0.0, top_k=[])

        raw_scores = self._bm25.get_scores(tokens)
        best_raw = float(raw_scores.max())

        if best_raw == 0.0:
            return MatchResult(tier="MISS", entry=None, score=0.0, top_k=[])

        normalized = best_raw / self._index.max_self_score

        # Deduplicate: keep best score per entry_id
        entry_best: dict[str, float] = {}
        for i, doc in enumerate(self._index.corpus):
            score = float(raw_scores[i])
            if score > entry_best.get(doc.entry_id, 0.0):
                entry_best[doc.entry_id] = score

        # Rank entries by score descending
        ranked = sorted(entry_best.items(), key=lambda x: x[1], reverse=True)
        ranked_entries = [self._entry_map[eid] for eid, _ in ranked if eid in self._entry_map]

        if not ranked_entries:
            return MatchResult(tier="MISS", entry=None, score=0.0, top_k=[])

        best_entry = ranked_entries[0]
        top_k = ranked_entries[:3]

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
