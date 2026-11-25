# -*- coding: utf-8 -*-
"""Settings for the GeoVision Catalog API (read from app/.env or environment variables).

Safe hackathon build: no default credentials, no local file paths, read-only by default.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the app/ folder


def _load_env():
    p = os.path.join(ROOT, ".env")
    if not os.path.exists(p):
        return
    with open(p, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

# PostgreSQL/PostGIS connection. Use a READ-ONLY role (see README). No default: must be set in .env.
DATABASE_URL = os.environ.get("DATABASE_URL", "")
# Public KazEOSat catalog service
CATALOG_URL = os.environ.get("CATALOG_URL", "https://old-eo.gharysh.kz/CatalogService")
# "Whole catalog" box: the catalog service expects this exact box (normal boxes return "Invalid coordinates")
CATALOG_BOX = {"West": "179.356737", "East": "79.563306", "South": "-37.146315", "North": "-179.766815"}
# How many recent days /catalog/area may re-fetch from the catalog before searching
LOOKBACK_DAYS = int(os.environ.get("LOOKBACK_DAYS", "3"))
# 1 = /catalog/area writes fresh catalog days into the DB before searching (needs a writable role).
# 0 (default) = strictly read-only: search only what the database already has.
CATALOG_REFRESH = os.environ.get("CATALOG_REFRESH", "0") == "1"
# Name of the cloud model whose results are stored in scenes.cloud_percentage (informational)
MODEL_NAME = os.environ.get("MODEL_NAME", "unet_kazeosat_finetuned_v4")
# Network
HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "60"))
HTTP_RETRIES = int(os.environ.get("HTTP_RETRIES", "2"))
