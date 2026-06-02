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

        # Precompute per-entry self-scores for per-entry normalization
        self._entry_self_scores: dict[str, float] = {}
        for i, doc in enumerate(self._index.corpus):
            if doc.tokens:
                score = float(self._bm25.get_scores(doc.tokens)[i])
                current = self._entry_self_scores.get(doc.entry_id, 0.0)
                if score > current:
                    self._entry_self_scores[doc.entry_id] = score

    def search(self, query: str) -> MatchResult:
        tokens = tokenize(query)
        if not tokens:
            return MatchResult(tier="MISS", entry=None, score=0.0, top_k=[])

        raw_scores = self._bm25.get_scores(tokens)

        # Deduplicate: keep best score per entry_id
        entry_best: dict[str, float] = {}
        for i, doc in enumerate(self._index.corpus):
            score = float(raw_scores[i])
            if score > entry_best.get(doc.entry_id, 0.0):
                entry_best[doc.entry_id] = score

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

        # Normalize by this entry's own self-score (not global max)
        entry_self = self._entry_self_scores.get(best_entry.id, self._index.max_self_score)
        normalized = best_raw / entry_self if entry_self > 0 else 0.0

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
