from __future__ import annotations

import logging
from pathlib import Path

from src.config import SQL_DIR
from src.transform import connect

log = logging.getLogger("citypulse.quality")


def run_tests() -> list[str]:
    """Run SQL tests. Each file must return zero rows. Returns failure messages."""
    con = connect(read_only=True)
    failures: list[str] = []
    try:
        test_dir = SQL_DIR / "tests"
        for path in sorted(test_dir.glob("*.sql")):
            rel = path.name
            rows = con.execute(path.read_text()).fetchall()
            if rows:
                messages = [str(r[0]) for r in rows]
                log.error("FAIL %s: %s", rel, messages)
                failures.extend(f"{rel}: {m}" for m in messages)
            else:
                log.info("PASS %s", rel)
    finally:
        con.close()
    return failures
