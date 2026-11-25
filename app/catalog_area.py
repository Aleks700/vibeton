# -*- coding: utf-8 -*-
"""POST /catalog/area - KazEOSat scenes that intersect an area of interest (GeoJSON), via PostGIS.

The area (from a KML/KMZ file or drawn by hand) is repaired with shapely (rings closed, Z dropped,
self-intersections fixed) and intersected with scene footprints in PostGIS (ST_Intersects on a GiST index).
Cloud cover per scene comes from the U-Net model results stored in the database.

Read-only by default. With CATALOG_REFRESH=1 (and a writable DB role) the most recent days are first
re-fetched from the public catalog so brand-new scenes are found too.
"""
import datetime as dt
import json
import os
import time
import urllib.parse
from typing import Any, Dict, Optional

import shapely
from shapely.geometry import shape
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from catalog_sync import catalog as ccat, config as ccfg, db as cdb

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "catalog_area.log")

# MATERIALIZED is required: otherwise PostgreSQL 12+ inlines the CTE into EXISTS and re-parses/repairs
# the area (thousands of points) for every scene of the period - 35 s instead of 0.5 s on a region.
SQL = """
WITH area AS MATERIALIZED (
    SELECT (ST_Dump(ST_MakeValid(ST_GeomFromText(g, 4326)))).geom AS geom
    FROM unnest(%s::text[]) AS g
)
SELECT s.raw, s.cloud_percentage
FROM scenes s
WHERE s.meta_date BETWEEN %s AND %s
  AND EXISTS (SELECT 1 FROM area a WHERE s.geom && a.geom AND ST_Intersects(s.geom, a.geom))
ORDER BY s.code DESC
"""

REFRESH_TIMEOUT = 20      # seconds per catalog day when refreshing recent days

# Catalog fields returned for each scene (compact - enough to choose and order a scene)
KEEP = ["Code", "Satellite", "Meta_Date", "IncidenceAngle", "SunElevationAngle", "Quicklook", "Coordinates"]


class AreaQuery(BaseModel):
    DateFr: str = Field(..., description="Start date, inclusive (YYYY-MM-DD)")
    DateTo: str = Field(..., description="End date, inclusive (YYYY-MM-DD)")
    Cloud: Optional[float] = Field(100, description="Maximum cloud cover, percent (0-100)")
    only_known: bool = Field(False, description="Return only scenes whose cloud cover is already computed")
    max_incidence: Optional[float] = Field(None, description="Maximum incidence (off-nadir) angle, degrees")
    limit: int = Field(100, ge=1, le=500, description="Max scenes to return (newest first)")
    geojson: Dict[str, Any] = Field(..., description="Area of interest: GeoJSON FeatureCollection, Feature or Geometry (lon/lat, WGS84)")


def _geometries(gj):
    """All geometries of a FeatureCollection / Feature / Geometry (GeoJSON dicts)."""
    if not isinstance(gj, dict):
        return
    t = gj.get("type")
    if t == "FeatureCollection":
        for f in gj.get("features") or []:
            yield from _geometries(f)
    elif t == "Feature":
        yield from _geometries(gj.get("geometry"))
    elif t:
        yield gj


def _to_wkt(geoms):
    """GeoJSON -> WKT via shapely: rings closed, Z dropped, invalid geometry repaired.
    Parts that cannot be parsed (e.g. a 2-point ring) are skipped and reported in errors."""
    out, errors = [], []
    for g in geoms:
        try:
            s = shapely.force_2d(shape(g))
            if not s.is_valid:
                s = shapely.make_valid(s)
            if not s.is_empty:
                out.append(s.wkt)
        except Exception as e:
            errors.append("%s: %s" % (g.get("type"), e))
    return out, errors


def _log(msg):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("%s  %s\n" % (dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


def _fetch_day(day):
    params = {"DateFr": day.isoformat(), "DateTo": (day + dt.timedelta(days=1)).isoformat()}
    params.update(ccfg.CATALOG_BOX)
    data = json.loads(ccat.http_get(ccfg.CATALOG_URL + "?" + urllib.parse.urlencode(params),
                                    timeout=REFRESH_TIMEOUT).decode("utf-8"))
    items = data.get("data", []) if isinstance(data, dict) else data
    seen, out = set(), []
    for it in items or []:
        if isinstance(it, dict) and it.get("Code") and it["Code"] not in seen:
            seen.add(it["Code"])
            out.append(it)
    return out


def _refresh_recent(conn, d0, d1):
    today = dt.datetime.now(dt.timezone.utc).date()
    last = cdb.last_synced_day(conn) or today
    d = max(d0, last - dt.timedelta(days=ccfg.LOOKBACK_DAYS))
    end = min(d1, today)
    while d <= end:
        try:
            cdb.upsert_scenes(conn, [ccat.parse_scene(it) for it in _fetch_day(d)], True)
        except Exception as e:
            conn.rollback()
            _log("catalog day %s not refreshed (%s) - searching the database only" % (d, e))
            return
        d += dt.timedelta(days=1)


def _num(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


router = APIRouter(tags=["catalog"])


@router.post("/catalog/area")
def search_scenes_in_area(q: AreaQuery):
    """Find KazEOSat scenes acquired between DateFr and DateTo whose footprint intersects the given area
    (GeoJSON), keeping only scenes with cloud cover <= Cloud percent.

    Each scene has Code, Satellite, Meta_Date, IncidenceAngle, SunElevationAngle, Quicklook (image URL),
    Coordinates, Cloud_Coverage (percent, null if not computed yet) and Cloud_Known.
    Returns {total_intersecting, returned, scenes[]}; scenes are newest first.
    """
    t0 = time.time()
    head = "%s..%s Cloud=%s" % (q.DateFr, q.DateTo, q.Cloud)

    def fail(code, msg):
        _log("%s  ERROR %d: %s" % (head, code, msg))
        raise HTTPException(code, msg)

    geoms = list(_geometries(q.geojson))
    if not geoms:
        fail(400, "the area has no geometry (polygons)")
    wkts, bad = _to_wkt(geoms)
    if not wkts:
        fail(400, "could not parse the area geometry: " + "; ".join(bad[:3]))
    try:
        d0 = dt.date.fromisoformat(q.DateFr[:10])
        d1 = dt.date.fromisoformat(q.DateTo[:10])
    except ValueError:
        fail(400, "dates must be YYYY-MM-DD (got %r, %r)" % (q.DateFr, q.DateTo))
    limit = 100.0 if q.Cloud is None else q.Cloud
    try:
        conn = cdb.connect()
    except Exception as e:
        fail(503, "database unavailable: %s" % e)
    try:
        if ccfg.CATALOG_REFRESH:
            _refresh_recent(conn, d0, d1)
        try:
            rows = conn.execute(SQL, (wkts, d0, d1)).fetchall()
        except Exception as e:
            conn.rollback()
            fail(400, "PostGIS rejected the area: %s" % str(e).splitlines()[0])
    finally:
        conn.close()

    out = []
    for raw, cloud in rows:
        if cloud is None and q.only_known:
            continue
        if cloud is not None and cloud > limit:
            continue
        inc = _num(raw.get("IncidenceAngle"))
        if q.max_incidence is not None and inc is not None and inc > q.max_incidence:
            continue
        item = {k: raw.get(k) for k in KEEP}
        item["IncidenceAngle"] = inc
        item["SunElevationAngle"] = _num(raw.get("SunElevationAngle"))
        item["Cloud_Coverage"] = None if cloud is None else round(float(cloud), 1)
        item["Cloud_Known"] = cloud is not None
        out.append(item)
    _log("%s  geometries %d (skipped %d), intersecting %d, returned %d, %.1f s" % (
        head, len(wkts), len(bad), len(rows), min(len(out), q.limit), time.time() - t0))
    return {"total_intersecting": len(rows), "matching": len(out), "returned": min(len(out), q.limit),
            "skipped_geometry_parts": bad[:3], "scenes": out[:q.limit]}
