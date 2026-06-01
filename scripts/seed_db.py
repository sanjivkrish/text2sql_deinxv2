#!/usr/bin/env python3
"""Seed the local postgres DB from JSON files in dataset/."""
import os, sys, json
sys.path.insert(0, ".")
import psycopg
from psycopg.types.json import Jsonb
from pathlib import Path

DATASET_DIR = Path("dataset")

# Order matters due to FK constraints
SEED_ORDER = [
    "schools",
    "academic_years",
    "classes",
    "class_sections",
    "class_section_years",
    "subjects",
    "staff",
    "staff_qualifications",
    "staff_certifications",
    "staff_experience",
    "students",
    "student_addresses",
    "admission_applications",
]

def load_json(name: str) -> list[dict]:
    path = DATASET_DIR / f"{name}.json"
    if not path.exists():
        print(f"  [skip] {name}.json not found")
        return []
    with open(path) as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get("data", [])

def coerce_value(v):
    """Convert Python dicts to Jsonb so psycopg3 can adapt them for JSONB columns.
    Replace '[REDACTED]' placeholder strings with None to avoid type errors on DATE/UUID columns."""
    if isinstance(v, dict):
        return Jsonb(v)
    if isinstance(v, str) and v == "[REDACTED]":
        return None
    return v

def insert_rows(conn, table: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    cols = list(rows[0].keys())
    placeholders = ", ".join(["%s"] * len(cols))
    col_list = ", ".join(cols)
    sql = f"INSERT INTO public.{table} ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
    count = 0
    for row in rows:
        try:
            with conn.cursor() as cur:
                # Use a savepoint so a failed row doesn't abort the whole transaction
                cur.execute("SAVEPOINT sp")
                cur.execute(sql, [coerce_value(row.get(c)) for c in cols])
                cur.execute("RELEASE SAVEPOINT sp")
                count += 1
        except Exception:
            with conn.cursor() as cur:
                cur.execute("ROLLBACK TO SAVEPOINT sp")
    return count

def main():
    db_url = os.environ.get("DB_URL", "postgresql://postgres:root@localhost:5432/dv1")
    with psycopg.connect(db_url) as conn:
        for table in SEED_ORDER:
            rows = load_json(table)
            if rows:
                n = insert_rows(conn, table, rows)
                print(f"  {table}: {n}/{len(rows)} rows inserted")
        conn.commit()
    print("Seeding complete.")

if __name__ == "__main__":
    main()
