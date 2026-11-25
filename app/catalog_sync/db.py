# -*- coding: utf-8 -*-
"""База данных: таблицы scenes (снимки каталога + облачность U-Net) и sync_runs (журнал запусков)."""
import json
import psycopg
from psycopg.types.json import Jsonb
from . import config

SCENES = """
CREATE TABLE IF NOT EXISTS scenes (
    code                 text PRIMARY KEY,                 -- DS_DZHR1_2026..._KZ1_E073N51_005216
    satellite            text,
    acquired_at          timestamptz,                      -- время съёмки UTC (из кода снимка)
    meta_date            date,                             -- Meta_Date из каталога
    quicklook_url        text,
    quicklook_file       text,                             -- локальный файл квиклука
    west                 double precision,
    east                 double precision,
    south                double precision,
    north                double precision,
    coordinates          text,                             -- исходная строка "lat lon lat lon ..."
    footprint_wkt        text,                             -- контур снимка, WKT POLYGON((lon lat, ...))
    pitch                double precision,
    roll                 double precision,
    yaw                  double precision,
    across_track_incidence double precision,
    along_track_incidence  double precision,
    incidence_angle      double precision,
    sun_elevation        double precision,
    sun_azimuth          double precision,
    raw                  jsonb,                            -- запись каталога целиком
    first_seen           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    -- облачность по модели U-Net
    cloud_percentage     double precision,                 -- % облаков в снимке (без чёрных полей)
    cloud_percentage_all double precision,                 -- % по всем пикселям квиклука
    valid_percentage     double precision,                 -- % пикселей с данными
    cloud_model          text,                             -- имя файла модели
    cloud_computed_at    timestamptz,
    cloud_error          text,                             -- почему не посчитано (нет квиклука и т.п.)
    mask_file            text                              -- уменьшенная маска облаков (png)
);
CREATE INDEX IF NOT EXISTS scenes_acquired_at_idx ON scenes (acquired_at);
CREATE INDEX IF NOT EXISTS scenes_meta_date_idx ON scenes (meta_date);
CREATE INDEX IF NOT EXISTS scenes_cloud_idx ON scenes (cloud_percentage);
CREATE INDEX IF NOT EXISTS scenes_bbox_idx ON scenes (west, east, south, north);
CREATE TABLE IF NOT EXISTS sync_runs (
    id               serial PRIMARY KEY,
    started_at       timestamptz NOT NULL DEFAULT now(),
    finished_at      timestamptz,
    date_from        date,
    date_to          date,
    scenes_seen      integer DEFAULT 0,
    scenes_new       integer DEFAULT 0,
    clouds_computed  integer DEFAULT 0,
    errors           integer DEFAULT 0,
    status           text,                                 -- running / ok / error
    message          text
);
"""

POSTGIS = """
CREATE EXTENSION IF NOT EXISTS postgis;
ALTER TABLE scenes ADD COLUMN IF NOT EXISTS geom geometry(Polygon, 4326);
CREATE INDEX IF NOT EXISTS scenes_geom_idx ON scenes USING gist (geom);
"""

COLS = ["code", "satellite", "acquired_at", "meta_date", "quicklook_url", "west", "east", "south", "north",
        "coordinates", "footprint_wkt", "pitch", "roll", "yaw", "across_track_incidence", "along_track_incidence",
        "incidence_angle", "sun_elevation", "sun_azimuth", "raw"]


def connect():
    if not config.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set (copy .env.example to .env)")
    return psycopg.connect(config.DATABASE_URL, connect_timeout=10)


def init(conn):
    """Создаёт таблицы. PostGIS подключается, если установлен; без него контур хранится только как WKT."""
    with conn.cursor() as cur:
        cur.execute(SCENES)
    conn.commit()
    has_gis = False
    try:
        with conn.cursor() as cur:
            cur.execute(POSTGIS)
        conn.commit()
        has_gis = True
    except Exception:
        conn.rollback()
    return has_gis


def upsert_scenes(conn, scenes, has_gis):
    """Вставляет новые снимки и обновляет поля каталога у существующих. Возвращает число новых."""
    if not scenes:
        return 0
    sets = ", ".join("%s = EXCLUDED.%s" % (c, c) for c in COLS if c != "code")
    sql = "INSERT INTO scenes (%s) VALUES (%s) ON CONFLICT (code) DO UPDATE SET %s, updated_at = now() RETURNING (xmax = 0) AS inserted" % (
        ", ".join(COLS), ", ".join("%%(%s)s" % c for c in COLS), sets)
    new = 0
    with conn.cursor() as cur:
        for s in scenes:
            row = dict(s)
            row["raw"] = Jsonb(row["raw"])
            cur.execute(sql, row)
            if cur.fetchone()[0]:
                new += 1
        if has_gis:
            cur.execute("UPDATE scenes SET geom = ST_GeomFromText(footprint_wkt, 4326) "
                        "WHERE geom IS NULL AND footprint_wkt IS NOT NULL AND code = ANY(%s)", ([s["code"] for s in scenes],))
    conn.commit()
    return new


def scenes_without_clouds(conn, model, limit=None, retry_errors=False):
    """Снимки, для которых ещё нет облачности по текущей модели."""
    q = "SELECT code, quicklook_url, acquired_at FROM scenes WHERE (cloud_model IS DISTINCT FROM %s OR cloud_percentage IS NULL)"
    params = [model]
    if not retry_errors:
        q += " AND (cloud_error IS NULL OR cloud_model IS DISTINCT FROM %s)"
        params.append(model)
    if config.CLOUD_SATELLITES:          # модель обучена на KazEOSat-1; KazEOSat-2 без даты съёмки
        q += " AND satellite = ANY(%s)"
        params.append(config.CLOUD_SATELLITES)
    q += " ORDER BY acquired_at DESC NULLS LAST"
    if limit:
        q += " LIMIT %d" % int(limit)
    with conn.cursor() as cur:
        cur.execute(q, params)
        return cur.fetchall()


def save_clouds(conn, code, res, model):
    with conn.cursor() as cur:
        if res.get("status") == "success":
            cur.execute("UPDATE scenes SET cloud_percentage=%s, cloud_percentage_all=%s, valid_percentage=%s, cloud_model=%s, "
                        "cloud_computed_at=now(), cloud_error=NULL, mask_file=%s, quicklook_file=%s, updated_at=now() WHERE code=%s",
                        (res["cloud_percentage"], res["cloud_percentage_all"], res["valid_percentage"], model,
                         res.get("mask_file"), res.get("quicklook_file"), code))
        else:
            cur.execute("UPDATE scenes SET cloud_model=%s, cloud_computed_at=now(), cloud_error=%s, quicklook_file=%s, updated_at=now() WHERE code=%s",
                        (model, (res.get("error_message") or "ошибка")[:500], res.get("quicklook_file"), code))
    conn.commit()


def last_synced_day(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT max(date_to) FROM sync_runs WHERE status = 'ok'")
        r = cur.fetchone()
        return r[0] if r else None


def run_start(conn, d0, d1):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO sync_runs (date_from, date_to, status) VALUES (%s, %s, 'running') RETURNING id", (d0, d1))
        rid = cur.fetchone()[0]
    conn.commit()
    return rid


def run_finish(conn, rid, **kw):
    sets = ", ".join("%s = %%(%s)s" % (k, k) for k in kw)
    kw["rid"] = rid
    with conn.cursor() as cur:
        cur.execute("UPDATE sync_runs SET finished_at = now(), %s WHERE id = %%(rid)s" % sets, kw)
    conn.commit()
