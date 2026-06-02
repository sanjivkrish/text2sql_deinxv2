#!/usr/bin/env python
"""CLI: build BM25 index from rag/faq.jsonl → rag/faq_index.json

Usage:
    uv run python scripts/build_faq_index.py
    uv run python scripts/build_faq_index.py --src rag/faq.jsonl --dst rag/faq_index.json
"""
import sys
import argparse
from rag.indexer import build_index


def main() -> None:
    parser = argparse.ArgumentParser(description="Build BM25 FAQ index")
    parser.add_argument("--src", default="rag/faq.jsonl", help="Source JSONL file")
    parser.add_argument("--dst", default="rag/faq_index.json", help="Output index file")
    args = parser.parse_args()

    try:
        idx = build_index(args.src, args.dst)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Built index -> {args.dst}")
    print(f"  Entries:       {len(idx.entries)}")
    print(f"  Corpus docs:   {len(idx.corpus)}")
    print(f"  max_self_score: {idx.max_self_score:.4f}")


if __name__ == "__main__":
    main()
