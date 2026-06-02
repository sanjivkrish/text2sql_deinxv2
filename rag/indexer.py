import re
import json
from datetime import datetime, timezone
from rank_bm25 import BM25Okapi
from rag.models import FAQEntry, FAQIndex, CorpusDoc

_STOP = frozenset({
    "the", "a", "an", "of", "for", "is", "are", "which", "who",
    "in", "at", "do", "does", "to", "from", "with", "by", "how",
})
_DML_RE = re.compile(
    r'\b(insert|update|delete|drop|truncate|alter|create|grant|revoke)\b',
    re.IGNORECASE,
)


def tokenize(text: str) -> list[str]:
    words = re.findall(r'\b\w+\b', text.lower())
    return [w for w in words if w not in _STOP and len(w) > 1]


def build_index(src_path: str, dst_path: str) -> FAQIndex:
    entries: list[FAQEntry] = []
    with open(src_path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = FAQEntry(**json.loads(line))
            except Exception as e:
                raise ValueError(f"Line {lineno}: parse error — {e}") from e
            if _DML_RE.search(entry.sql):
                raise ValueError(f"Line {lineno} ({entry.id!r}): forbidden SQL keyword in sql field")
            entries.append(entry)

    if not entries:
        raise ValueError("faq.jsonl is empty — nothing to index")

    # Build corpus: one doc per question + each alt_question
    corpus_docs: list[CorpusDoc] = []
    for entry in entries:
        for text in [entry.question] + entry.alt_questions:
            corpus_docs.append(CorpusDoc(tokens=tokenize(text), entry_id=entry.id))

    raw_corpus = [doc.tokens for doc in corpus_docs]
    if not any(raw_corpus):
        raise ValueError("All corpus documents tokenized to empty — corpus has no usable tokens")
    bm25 = BM25Okapi(raw_corpus)

    # Compute max_self_score: score each doc against its own tokens, take global max
    max_self = 0.0
    for i, doc in enumerate(corpus_docs):
        if doc.tokens:
            score = float(bm25.get_scores(doc.tokens)[i])
            if score > max_self:
                max_self = score

    if max_self == 0.0:
        max_self = 1.0  # degenerate corpus guard

    idx = FAQIndex(
        version=1,
        built_at=datetime.now(timezone.utc).isoformat(),
        entries=entries,
        corpus=corpus_docs,
        max_self_score=max_self,
    )

    with open(dst_path, "w", encoding="utf-8") as f:
        json.dump(idx.model_dump(), f, indent=2)

    return idx
