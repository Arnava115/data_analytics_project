from __future__ import annotations

import argparse
import logging
import sys

from src.config import load_config
from src.ingest import RAW_DIR, _http_client, download_month, download_reference, discover_months
from src.quality import run_tests
from src.transform import finalize, init_warehouse, transform_month

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("citypulse")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="City Pulse ETL: ingest TLC, build marts, test.")
    parser.add_argument("--skip-ingest", action="store_true", help="Reuse parquet already in data/raw")
    parser.add_argument("--ingest-only", action="store_true")
    parser.add_argument("--transform-only", action="store_true")
    parser.add_argument("--test-only", action="store_true")
    args = parser.parse_args(argv)

    if args.test_only:
        failures = run_tests()
        if failures:
            log.error("Tests failed:\n%s", "\n".join(failures))
            return 1
        log.info("All tests passed")
        return 0

    cfg = load_config()
    keep_raw = bool(cfg.get("keep_raw", False))
    n = int(cfg["months"])

    if args.ingest_only:
        download_reference()
        with _http_client() as client:
            months = discover_months(n, client=client)
            for ym in months:
                download_month(ym, client=client)
        return 0

    download_reference()

    with _http_client() as client:
        if args.skip_ingest or args.transform_only:
            months = sorted(
                p.name.replace("fhvhv_tripdata_", "").replace(".parquet", "")
                for p in RAW_DIR.glob("fhvhv_tripdata_*.parquet")
            )
            if not months:
                months = discover_months(n, client=client)
        else:
            months = discover_months(n, client=client)

        init_warehouse()
        for i, ym in enumerate(months):
            dest = RAW_DIR / f"fhvhv_tripdata_{ym}.parquet"
            if not dest.exists():
                if args.skip_ingest or args.transform_only:
                    raise FileNotFoundError(dest)
                download_month(ym, client=client)
            transform_month(str(dest), ym, first=(i == 0))
            if not keep_raw and dest.exists():
                dest.unlink()
                log.info("Removed %s after aggregating (keep_raw=false)", dest.name)

    finalize()
    failures = run_tests()
    if failures:
        log.error("Tests failed:\n%s", "\n".join(failures))
        return 1
    log.info("Pipeline complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
