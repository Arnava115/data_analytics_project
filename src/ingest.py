from __future__ import annotations

import logging
import zipfile
from datetime import date
from pathlib import Path

import httpx
from dateutil.relativedelta import relativedelta

from src.config import (
    RAW_DIR,
    REF_DIR,
    TAXI_ZONES_ZIP_URL,
    TLC_TRIP_URL,
    ZONE_LOOKUP_URLS,
    ensure_dirs,
    load_config,
)

log = logging.getLogger("citypulse.ingest")

TIMEOUT = httpx.Timeout(connect=30.0, read=None, write=None, pool=30.0)
ZONE_LOOKUP_PATH = REF_DIR / "taxi_zone_lookup.csv"
TAXI_ZONES_ZIP_PATH = REF_DIR / "taxi_zones.zip"
TAXI_ZONES_GEOJSON_PATH = REF_DIR / "taxi_zones.geojson"


def _http_client() -> httpx.Client:
    return httpx.Client(
        timeout=TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": "city-pulse/1.0 (marketplace analytics portfolio)"},
    )


def download_file(url: str, dest: Path, *, client: httpx.Client | None = None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    close = False
    if client is None:
        client = _http_client()
        close = True
    try:
        if dest.exists() and dest.stat().st_size > 1_000_000:
            head = client.head(url)
            total = int(head.headers.get("content-length") or 0)
            if not total or dest.stat().st_size == total:
                log.info("Cached %s (%s MB)", dest.name, f"{dest.stat().st_size / 1e6:.0f}")
                return dest
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length") or 0)
            if dest.exists() and (
                (total and dest.stat().st_size == total) or (not total and dest.stat().st_size > 10_000_000)
            ):
                log.info("Cached %s (%s MB)", dest.name, f"{dest.stat().st_size / 1e6:.0f}")
                return dest
            tmp = dest.with_suffix(dest.suffix + ".part")
            done = 0
            last_bucket = -1
            with tmp.open("wb") as fh:
                for chunk in resp.iter_bytes(1024 * 1024):
                    fh.write(chunk)
                    done += len(chunk)
                    if total:
                        bucket = int(10 * done / total)
                        if bucket != last_bucket:
                            last_bucket = bucket
                            log.info(
                                "  %s  %s%% (%s / %s MB)",
                                dest.name,
                                bucket * 10,
                                f"{done / 1e6:.0f}",
                                f"{total / 1e6:.0f}",
                            )
            tmp.replace(dest)
        log.info("Wrote %s", dest)
        return dest
    finally:
        if close:
            client.close()


def discover_months(n: int, *, client: httpx.Client) -> list[str]:
    """Find the n most recent TLC months that return HTTP 200."""
    cursor = date.today().replace(day=1)
    found: list[str] = []
    # TLC publishes with ~2 month lag; walk back up to 18 months.
    for _ in range(18):
        ym = cursor.strftime("%Y-%m")
        url = TLC_TRIP_URL.format(year_month=ym)
        resp = client.head(url)
        ok = resp.status_code == 200
        if not ok:
            probe = client.get(url, headers={"Range": "bytes=0-0"})
            ok = probe.status_code in (200, 206)
        if ok:
            found.append(ym)
            log.info("Available month: %s", ym)
            if len(found) >= n:
                break
        cursor = cursor - relativedelta(months=1)
    if len(found) < n:
        raise RuntimeError(f"Only found {len(found)} TLC months, need {n}")
    return sorted(found)


def download_zone_lookup(client: httpx.Client) -> Path:
    last_error: Exception | None = None
    for url in ZONE_LOOKUP_URLS:
        try:
            return download_file(url, ZONE_LOOKUP_PATH, client=client)
        except httpx.HTTPError as exc:
            last_error = exc
            log.warning("Zone lookup failed from %s: %s", url, exc)
    raise RuntimeError("Could not download taxi zone lookup") from last_error


def _transform_coords(geom: dict, transformer) -> dict:
    gtype = geom["type"]
    if gtype == "Polygon":
        geom["coordinates"] = [
            [list(transformer.transform(x, y)) for x, y in ring] for ring in geom["coordinates"]
        ]
    elif gtype == "MultiPolygon":
        geom["coordinates"] = [
            [[list(transformer.transform(x, y)) for x, y in ring] for ring in poly]
            for poly in geom["coordinates"]
        ]
    elif gtype == "Point":
        x, y = geom["coordinates"]
        geom["coordinates"] = list(transformer.transform(x, y))
    return geom


def shapefile_zip_to_geojson(zip_path: Path, out_path: Path) -> Path:
    """Convert TLC taxi_zones.zip (NAD83 / NY Long Island ft) to WGS84 GeoJSON."""
    import json
    import tempfile

    import shapefile
    from pyproj import Transformer

    transformer = Transformer.from_crs("EPSG:2263", "EPSG:4326", always_xy=True)
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp)
        shp = next(Path(tmp).rglob("*.shp"))
        reader = shapefile.Reader(str(shp))
        field_names = [f[0] for f in reader.fields[1:]]
        features = []
        for sr in reader.iterShapeRecords():
            props_raw = dict(zip(field_names, sr.record, strict=False))
            loc = props_raw.get("LocationID") or props_raw.get("locationid") or props_raw.get("OBJECTID")
            props = {
                "location_id": int(loc),
                "zone": str(props_raw.get("zone") or props_raw.get("Zone") or ""),
                "borough": str(props_raw.get("borough") or props_raw.get("Borough") or ""),
            }
            geom = _transform_coords(sr.shape.__geo_interface__, transformer)
            features.append({"type": "Feature", "geometry": geom, "properties": props})
        out_path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    log.info("Wrote %s (%s zones)", out_path, len(features))
    return out_path


def download_taxi_zones(client: httpx.Client) -> Path:
    if TAXI_ZONES_GEOJSON_PATH.exists() and TAXI_ZONES_GEOJSON_PATH.stat().st_size > 1000:
        log.info("Cached %s", TAXI_ZONES_GEOJSON_PATH.name)
        return TAXI_ZONES_GEOJSON_PATH
    download_file(TAXI_ZONES_ZIP_URL, TAXI_ZONES_ZIP_PATH, client=client)
    try:
        return shapefile_zip_to_geojson(TAXI_ZONES_ZIP_PATH, TAXI_ZONES_GEOJSON_PATH)
    except Exception as exc:
        log.warning("Could not convert taxi zone shapefile to GeoJSON: %s", exc)
        return TAXI_ZONES_ZIP_PATH


def download_reference() -> None:
    ensure_dirs()
    with _http_client() as client:
        download_zone_lookup(client)
        download_taxi_zones(client)


def download_month(year_month: str, *, client: httpx.Client | None = None) -> Path:
    ensure_dirs()
    url = TLC_TRIP_URL.format(year_month=year_month)
    dest = RAW_DIR / f"fhvhv_tripdata_{year_month}.parquet"
    close = False
    if client is None:
        client = _http_client()
        close = True
    try:
        return download_file(url, dest, client=client)
    finally:
        if close:
            client.close()


def ingest() -> dict:
    """Download TLC reference data and the latest N monthly trip parquets."""
    cfg = load_config()
    n = int(cfg["months"])
    download_reference()
    with _http_client() as client:
        months = discover_months(n, client=client)
        paths = [download_month(ym, client=client) for ym in months]
    log.info("Ingest complete: months=%s", months)
    return {"months": months, "parquet_paths": [str(p) for p in paths]}
