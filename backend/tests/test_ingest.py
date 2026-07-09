import sqlite3

from app.services.ingest import run_ingest


def test_reingest_does_not_duplicate_records():
    # Issue #1: re-running ingest should leave the record set unchanged,
    # not append a second copy of every row.
    conn = sqlite3.connect(":memory:")
    try:
        run_ingest(conn)
        first = conn.execute("SELECT COUNT(*) AS n FROM records").fetchone()[0]
        run_ingest(conn)
        second = conn.execute("SELECT COUNT(*) AS n FROM records").fetchone()[0]
    finally:
        conn.close()
    assert second == first


def test_reingest_does_not_duplicate_catalog():
    # The catalog is already idempotent (INSERT OR REPLACE on a PRIMARY
    # KEY); this guards that the fix to records keeps it that way.
    conn = sqlite3.connect(":memory:")
    try:
        run_ingest(conn)
        first = conn.execute("SELECT COUNT(*) AS n FROM catalog").fetchone()[0]
        run_ingest(conn)
        second = conn.execute("SELECT COUNT(*) AS n FROM catalog").fetchone()[0]
    finally:
        conn.close()
    assert second == first