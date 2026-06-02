#!/usr/bin/env python
"""Run each FAQ SQL against the live DB and report pass/fail.

Usage:
    uv run python scripts/test_faq_sql.py

Env vars:
    DB_URL          — PostgreSQL connection string (from .env)
    TEST_SCHOOL_ID  — UUID to inject as school_id for testing

The script injects AND {primary_table}.school_id = '{TEST_SCHOOL_ID}' via the
production SQLRunner so the injection logic is identical to live behaviour.
"""
import os
import sys
import json

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from rag.models import FAQEntry
from core.models.sql import SQLResult
from core.execution_layer.runner import SQLRunner

FAQ_PATH = "rag/faq.jsonl"
PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
SKIP = "\033[33mSKIP\033[0m"


def main() -> None:
    db_url = os.environ.get("DB_URL", "")
    school_id = os.environ.get("TEST_SCHOOL_ID", "")

    if not db_url:
        print("ERROR: DB_URL not set", file=sys.stderr)
        sys.exit(1)
    if not school_id:
        print("ERROR: TEST_SCHOOL_ID not set", file=sys.stderr)
        sys.exit(1)

    runner = SQLRunner(db_url)
    entries: list[FAQEntry] = []
    with open(FAQ_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(FAQEntry(**json.loads(line)))

    passed = failed = skipped = 0
    for entry in entries:
        # Skip parameterized entries — placeholder SQL won't execute meaningfully
        if entry.has_variables:
            print(f"{SKIP}  {entry.id:<45}  (parameterized)")
            skipped += 1
            continue
        sql_result = SQLResult(sql=entry.sql, confidence_score=1.0, warnings=[], value_extractions={})
        try:
            run = runner.run(sql_result, school_id, entry.primary_table)
            print(f"{PASS}  {entry.id:<45}  rows={run.row_count}")
            passed += 1
        except Exception as e:
            print(f"{FAIL}  {entry.id:<45}  {e}")
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed, {skipped} skipped (parameterized)")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
