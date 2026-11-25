# -*- coding: utf-8 -*-
"""GeoVision Catalog API - safe, read-only build for the 2nd Brain Labs x Geek Room Vibe-a-thon.

Satellite scene catalog of KazEOSat with cloud cover estimated by a U-Net model.
Endpoints (all read-only):
    GET  /catalog          live catalog search by dates + bounding box, with U-Net cloud cover
    POST /catalog/area     scenes intersecting an area of interest (GeoJSON), via PostGIS
    GET  /db/scenes        scenes stored in the database (dates, bbox, cloud filter)
    GET  /db/scenes/{code} one scene by code
    GET  /db/status        database freshness and last synchronisation runs

Not included on purpose (exist in the internal app): quicklook download to disk, legacy KML upload,
forecast-file upload/delete, GPU cloud detection. See README.md -> "Endpoint selection".
"""
import asyncio
import datetime as dt
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from catalog_sync import config
from catalog_sync.api import cloud_map, router as db_router
from catalog_area import router as area_router

app = FastAPI(
    title="GeoVision Catalog API",
    description="KazEOSat satellite scene catalog with U-Net cloud cover. Read-only.",
    version="1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5500", "http://127.0.0.1:5500"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(area_router)
app.include_router(db_router)

MAX_DAYS = 31          # live catalog search window limit
KEEP = ["Code", "Satellite", "Meta_Date", "IncidenceAngle", "SunElevationAngle", "Quicklook", "Coordinates"]
_client: Optional[httpx.AsyncClient] = None


def _catalog_client() -> httpx.AsyncClient:
    """One shared HTTPS connection to the catalog service (keep-alive)."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=config.HTTP_TIMEOUT)
    return _client


def _num(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _scene_bbox(coords: str):
    """'lat lon lat lon ...' -> (west, east, south, north) or None."""
    try:
        v = [float(x) for x in str(coords).split()]
        lats, lons = v[0::2], v[1::2]
        return min(lons), max(lons), min(lats), max(lats)
    except (ValueError, TypeError):
        return None


@app.get("/catalog")
async def search_live_catalog(
    DateFr: dt.date = Query(..., description="Start date, inclusive (YYYY-MM-DD)"),
    DateTo: dt.date = Query(..., description="End date, inclusive (YYYY-MM-DD); at most 31 days after DateFr"),
    West: float = Query(..., ge=-180, le=180, description="Bounding box: west longitude"),
    East: float = Query(..., ge=-180, le=180, description="Bounding box: east longitude"),
    South: float = Query(..., ge=-90, le=90, description="Bounding box: south latitude"),
    North: float = Query(..., ge=-90, le=90, description="Bounding box: north latitude"),
    Cloud: float = Query(100, ge=0, le=100, description="Maximum cloud cover, percent"),
    only_known: bool = Query(False, description="Return only scenes whose cloud cover is already computed"),
    limit: int = Query(100, ge=1, le=500, description="Max scenes to return"),
):
    """Search the live KazEOSat catalog (includes scenes from the last hours) for scenes whose footprint
    intersects the bounding box, and add U-Net cloud cover from the database.

    Each scene has Code, Satellite, Meta_Date, IncidenceAngle, SunElevationAngle, Quicklook (image URL),
    Coordinates, Cloud_Coverage (percent, null if not computed yet) and Cloud_Known.
    """
    if DateTo < DateFr:
        raise HTTPException(400, "DateTo is before DateFr")
    if (DateTo - DateFr).days > MAX_DAYS:
        raise HTTPException(400, "date range is longer than %d days - use POST /catalog/area or GET /db/scenes" % MAX_DAYS)
    w, e, s, n = min(West, East), max(West, East), min(South, North), max(South, North)
    params = {"DateFr": DateFr.isoformat(), "DateTo": DateTo.isoformat(), **config.CATALOG_BOX}
    try:
        r = await _catalog_client().get(config.CATALOG_URL, params=params)
        items = r.json().get("data", [])
    except Exception as ex:
        raise HTTPException(502, "catalog service unavailable: %s" % ex)

    hits = []
    for it in items:
        bb = _scene_bbox(it.get("Coordinates"))
        if bb and bb[1] >= w and bb[0] <= e and bb[3] >= s and bb[2] <= n:
            hits.append(it)
    clouds = await asyncio.to_thread(cloud_map, [it.get("Code") for it in hits])

    out = []
    for it in hits:
        c = clouds.get(it.get("Code"))
        if c is None and only_known:
            continue
        if c is not None and c > Cloud:
            continue
        item = {k: it.get(k) for k in KEEP}
        item["IncidenceAngle"] = _num(it.get("IncidenceAngle"))
        item["SunElevationAngle"] = _num(it.get("SunElevationAngle"))
        item["Cloud_Coverage"] = None if c is None else round(float(c), 1)
        item["Cloud_Known"] = c is not None
        out.append(item)
    out.sort(key=lambda x: x.get("Code") or "", reverse=True)
    return {"total_intersecting": len(hits), "matching": len(out), "returned": min(len(out), limit), "scenes": out[:limit]}
