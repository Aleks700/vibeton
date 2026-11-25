# -*- coding: utf-8 -*-
"""Запросы к каталогу снимков (CatalogService) и разбор записей."""
import datetime as dt
import json
import re
import ssl
import time
import urllib.parse
import urllib.request
from . import config

UA = {"User-Agent": "Mozilla/5.0 (catalog_sync)"}
_ctx = ssl.create_default_context()


def http_get(url, timeout=None):
    last = None
    for i in range(config.HTTP_RETRIES):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout or config.HTTP_TIMEOUT, context=_ctx) as r:
                return r.read()
        except Exception as e:
            last = e
            time.sleep(5 * (i + 1))
    raise last


def fetch_day(day):
    """Все снимки каталога за сутки day (date). Возвращает список записей каталога (dict)."""
    params = {"DateFr": day.isoformat(), "DateTo": (day + dt.timedelta(days=1)).isoformat()}
    params.update(config.CATALOG_BOX)
    url = config.CATALOG_URL + "?" + urllib.parse.urlencode(params)
    body = http_get(url)
    data = json.loads(body.decode("utf-8"))
    if isinstance(data, dict) and "error" in data:
        raise RuntimeError("каталог: %s" % json.dumps(data, ensure_ascii=False)[:200])
    items = data.get("data", []) if isinstance(data, dict) else data
    out, seen = [], set()
    for it in items or []:
        if not isinstance(it, dict) or not it.get("Code") or it["Code"] in seen:
            continue
        seen.add(it["Code"])
        out.append(it)
    return out


_CODE = re.compile(r"^DS_DZHR1_(\d{14})(\d)")


def _f(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _d(v):
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def parse_scene(it):
    """Запись каталога → строка таблицы scenes."""
    code = it["Code"]
    acquired = None
    m = _CODE.match(code)
    if m:
        acquired = dt.datetime.strptime(m.group(1), "%Y%m%d%H%M%S").replace(tzinfo=dt.timezone.utc) + dt.timedelta(milliseconds=100 * int(m.group(2)))
    wkt = None
    try:
        v = [float(x) for x in str(it.get("Coordinates", "")).split()]
        pts = [(v[i + 1], v[i]) for i in range(0, len(v) - 1, 2)]      # lat lon → (lon, lat)
        if len(pts) >= 3:
            if pts[0] != pts[-1]:
                pts.append(pts[0])
            wkt = "POLYGON((%s))" % ", ".join("%.6f %.6f" % p for p in pts)
    except ValueError:
        pass
    return {
        "code": code, "satellite": it.get("Satellite"), "acquired_at": acquired,
        "meta_date": _d(it.get("Meta_Date") or it.get("Metadata_Date")),
        "quicklook_url": it.get("Quicklook"),
        "west": _f(it.get("West")), "east": _f(it.get("East")), "south": _f(it.get("South")), "north": _f(it.get("North")),
        "coordinates": it.get("Coordinates"), "footprint_wkt": wkt,
        "pitch": _f(it.get("Pitch")), "roll": _f(it.get("Roll")), "yaw": _f(it.get("Yaw")),
        "across_track_incidence": _f(it.get("AcrossTrackIncidenceAngle")), "along_track_incidence": _f(it.get("AlongTrackIncidence")),
        "incidence_angle": _f(it.get("IncidenceAngle")), "sun_elevation": _f(it.get("SunElevationAngle")), "sun_azimuth": _f(it.get("SunAzimuthAngle")),
        "raw": it,
    }
