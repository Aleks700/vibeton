# -*- coding: utf-8 -*-
"""Read-only endpoints over the scenes database (KazEOSat catalog + U-Net cloud cover)."""
import datetime as dt
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from . import config, db

# Full paths in the decorators (no router prefix) so code scanners such as Synapse see the real URLs.
router = APIRouter(tags=["scenes database"])

# Columns returned to clients. Local file paths (quicklook_file, mask_file) are intentionally not exposed.
FIELDS = ["code", "satellite", "acquired_at", "meta_date", "quicklook_url", "west", "east", "south", "north",
          "coordinates", "footprint_wkt", "incidence_angle", "sun_elevation", "sun_azimuth",
          "cloud_percentage", "cloud_percentage_all", "valid_percentage", "cloud_model", "cloud_computed_at", "cloud_error"]


def _rows(cur):
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def cloud_map(codes):
    """{code: cloud %} from the database for a list of scene codes; empty if the database is unavailable."""
    if not codes:
        return {}
    try:
        with db.connect() as conn:
            cur = conn.execute("SELECT code, cloud_percentage FROM scenes WHERE code = ANY(%s) AND cloud_percentage IS NOT NULL",
                               (list(codes),))
            return dict(cur.fetchall())
    except Exception:
        return {}


@router.get("/db/scenes")
def list_scenes(
    DateFr: Optional[dt.date] = Query(None, description="Acquisition date from, UTC (YYYY-MM-DD)"),
    DateTo: Optional[dt.date] = Query(None, description="Acquisition date to, inclusive (YYYY-MM-DD)"),
    West: Optional[float] = Query(None, description="Bounding box: west longitude"),
    East: Optional[float] = Query(None, description="Bounding box: east longitude"),
    South: Optional[float] = Query(None, description="Bounding box: south latitude"),
    North: Optional[float] = Query(None, description="Bounding box: north latitude"),
    Cloud: Optional[float] = Query(None, description="Maximum cloud cover, percent (0-100)"),
    only_computed: bool = Query(False, description="Only scenes whose cloud cover is already computed"),
    limit: int = Query(100, ge=1, le=1000, description="Max scenes to return"),
    offset: int = Query(0, ge=0),
):
    """List KazEOSat-1 scenes stored in the database with U-Net cloud cover.

    Filters by acquisition date, bounding box (scene bbox intersects the box) and maximum cloud cover.
    Newest scenes first. Returns {total, count, data[]}.
    """
    w, p = [], []
    if DateFr:
        w.append("acquired_at >= %s"); p.append(dt.datetime.combine(DateFr, dt.time.min, dt.timezone.utc))
    if DateTo:
        w.append("acquired_at < %s"); p.append(dt.datetime.combine(DateTo + dt.timedelta(days=1), dt.time.min, dt.timezone.utc))
    if None not in (West, East, South, North):
        w.append("east >= %s AND west <= %s AND north >= %s AND south <= %s")
        p += [min(West, East), max(West, East), min(South, North), max(South, North)]
    if Cloud is not None:
        w.append("cloud_percentage <= %s" if only_computed else "(cloud_percentage <= %s OR cloud_percentage IS NULL)")
        p.append(Cloud)
    elif only_computed:
        w.append("cloud_percentage IS NOT NULL")
    where = (" WHERE " + " AND ".join(w)) if w else ""
    sql = "SELECT %s FROM scenes%s ORDER BY acquired_at DESC NULLS LAST LIMIT %%s OFFSET %%s" % (", ".join(FIELDS), where)
    try:
        with db.connect() as conn:
            cnt = conn.execute("SELECT count(*) FROM scenes" + where, p).fetchone()[0]
            data = _rows(conn.execute(sql, p + [limit, offset]))
    except Exception as e:
        raise HTTPException(503, "database unavailable: %s" % e)
    return {"total": cnt, "count": len(data), "data": data}


@router.get("/db/scenes/{code}")
def get_scene(code: str):
    """Full record of one scene by its code (e.g. DS_DZHR1_202606120614060_KZ1_E070N43_014523),
    including the original catalog entry and U-Net cloud cover."""
    try:
        with db.connect() as conn:
            r = _rows(conn.execute("SELECT %s, raw FROM scenes WHERE code = %%s" % ", ".join(FIELDS), (code,)))
    except Exception as e:
        raise HTTPException(503, "database unavailable: %s" % e)
    if not r:
        raise HTTPException(404, "scene not found")
    return r[0]


@router.get("/db/status")
def database_status():
    """Database freshness: number of scenes, how many have cloud cover, acquisition date range,
    cloud model name and the last catalog synchronisation runs."""
    try:
        with db.connect() as conn:
            tot, comp, err, first, last = conn.execute(
                "SELECT count(*), count(cloud_percentage), count(cloud_error), min(acquired_at), max(acquired_at) FROM scenes").fetchone()
            runs = _rows(conn.execute(
                "SELECT id, started_at, finished_at, date_from, date_to, scenes_seen, scenes_new, clouds_computed, errors, status "
                "FROM sync_runs ORDER BY id DESC LIMIT 5"))
    except Exception as e:
        raise HTTPException(503, "database unavailable: %s" % e)
    return {"scenes": tot, "with_clouds": comp, "cloud_errors": err, "first": first, "last": last,
            "model": config.MODEL_NAME, "last_sync_runs": runs}
