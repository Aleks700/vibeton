# GeoVision Catalog API - an agent-ready satellite catalog

**Vibe-a-thon (2nd Brain Labs x Geek Room) - Track 1: Make a legacy app agent-ready (Synapse Auto mode).**

## The problem

Operators of the KazEOSat Earth-observation satellites search the scene catalog every day:
"what did we shoot over this region last month, and which scenes are actually usable?"
Half of the scenes can be useless because of clouds. Answering that today means opening a web map,
drawing an area, scrolling a table and looking at quicklooks one by one.

## The app (unchanged by the agent work)

GeoVision Catalog API is a FastAPI service over the KazEOSat catalog:

- every scene's footprint is stored in **PostgreSQL + PostGIS** (135 584 scenes, 2020-2026);
- cloud cover is estimated by a **U-Net model** on the scene quicklook (35 969 KazEOSat-1 scenes scored);
- an area of interest (from a KML/KMZ file) is intersected with footprints in PostGIS in about 0.5 s,
  even for a region polygon with 12 000+ points.

This repository is a **safe, read-only build** of the internal app: no credentials, no internal data
files, no model weights, no endpoints that write to disk or to the database.

## Endpoint selection - what the agent gets, and why

| Exposed endpoint | Tool purpose | Why it is exposed |
|---|---|---|
| `POST /catalog/area` | scenes over an area (GeoJSON) with cloud / incidence filters | the core question: "usable scenes over my area" |
| `GET /catalog` | live catalog by dates + bounding box (<= 31 days) | finds scenes from the last hours that are not in the database yet |
| `GET /db/scenes` | stored scenes by dates, bbox, cloud | long periods and statistics |
| `GET /db/scenes/{code}` | one scene by code | details and the original catalog record |
| `GET /db/status` | database freshness, last sync runs | lets the agent say how up to date its answer is |

| Not exposed (exists in the internal app) | Why not |
|---|---|
| quicklook download to the server disk | writes files; not needed to answer questions |
| legacy KML upload endpoint | duplicate of `/catalog/area`, slower |
| forecast-file upload / delete | changes data |
| GPU cloud detection on demand | heavy, minutes per batch; results are already in the database |

Fewer, well-described tools make the agent more reliable: every exposed endpoint has typed parameters,
an English description and compact responses (`limit`, `Cloud_Coverage: null` when unknown instead of a fake 0).

## Safety

- **Read-only database role** (`geovision_ro`, `default_transaction_read_only = on`): even a wrong call cannot
  modify data. `CATALOG_REFRESH=0` by default, so the API never writes.
- **No secrets in code**: connection string only in `app/.env` (git-ignored); `app/.env.example` has placeholders.
- **No local paths** in responses (mask / quicklook file paths are not returned).
- **Local Synapse build** (`synapse build --local`) keeps the code on our machine; hosted builds only send
  route names and docstrings (and handler code with `--smart-names`).
- Output size limits (`limit` <= 500, live catalog window <= 31 days) protect the agent's context.

## Run

Requirements: Python 3.11+, PostgreSQL 16 + PostGIS with the `scenes` table, Node.js 20+ for Synapse.

```bat
cd app
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env        & rem then set DATABASE_URL (read-only role)
.venv\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 9100
```

Open `http://127.0.0.1:9100/docs`. On the author's machine: `Запустить_API.bat`.

## Make it agent-ready with Synapse

Scripts in `synapse/` (one per step, run from `app/`):

| Step | Script | Command |
|---|---|---|
| install | `1_install_synapse.bat` | `npm install -g @2ndbrainlabs-ai/synapse-cli` |
| init (hosted only) | `2_init_project.bat` | `synapse init` |
| build, hosted | `3_build_auto_hosted.bat` | `synapse build --auto --endpoints "GET /catalog,POST /catalog/area,GET /db/scenes,GET /db/scenes/{code},GET /db/status"` |
| build, hosted + names | `3b_build_auto_smart_names.bat` | same + `--smart-names` |
| build, local (recommended) | `4_build_local.bat` | `synapse model set anthropic` + `synapse build --local --auto --endpoints "..."` |
| rebuild after changes | `5_rebuild_discover.bat` | `synapse build --discover` |
| state / quota / key | `6_info.bat` | `synapse info`, `synapse config`, `synapse model` |

Then paste the JSON snippet printed by Synapse into the MCP client config
(Claude Desktop: Settings -> Developer -> Edit Config; Cursor: Settings -> MCP) and restart the client.

### Generated MCP setup (what we actually built)

Hosted Auto build, Synapse CLI 0.1.9, 5 endpoints selected -> 5 MCP tools, verified with a live `tools/call`:

| MCP tool (named by Synapse) | Endpoint |
|---|---|
| `search_scenes_in_area` | `POST /catalog/area` |
| `search_live_catalog` | `GET /catalog` |
| `list_scenes` | `GET /db/scenes` |
| `get_scene` | `GET /db/scenes/{code}` |
| `database_status` | `GET /db/status` |

- Client config (key removed): [`synapse/mcp_client_config.example.json`](synapse/mcp_client_config.example.json)
  (`npx -y @2ndbrainlabs-ai/synapse-mcp`, `SYNAPSE_SERVER_ID`, `ENDPOINT_BASE_URL=http://127.0.0.1:9100`).
- Synapse scan output: `app/.synapse/surface_cache.json` and `app/.synapse/discover/*.jsonl` (build sessions).
  `app/.synapse/config.json` holds the encrypted API key and is git-ignored.

Two things we hit while building, kept here for anyone repeating it:
- Synapse reads route paths from the decorators and ignores `APIRouter(prefix=...)`, so the first scan found
  `/scenes` instead of `/db/scenes`. Fix: full paths in the decorators (`catalog_sync/api.py`); URLs unchanged.
- Behind a TLS-inspecting corporate proxy Node.js rejects the certificate. Export the proxy root CA to PEM and set
  `NODE_EXTRA_CA_CERTS` (the scripts in `synapse/` do this if `%USERPROFILE%\.certs\sts_root.pem` exists; add it to
  the MCP client `env` as well).

## Demo

Three real tasks the agent completes with no change to the app code: see [`demo/tasks.md`](demo/tasks.md).

1. Clear scenes over the Zhambyl region in June 2026 (cloud < 20 %, incidence < 30°) - one tool call.
2. Data freshness + new scenes over Almaty from the live catalog - the agent reports unknown cloud cover honestly.
3. Week-by-week cloudiness over the West Kazakhstan region in October 2026 and a re-acquisition suggestion.

## Repository layout

```
app/                 the application (FastAPI)
  main.py            GET /catalog
  catalog_area.py    POST /catalog/area (PostGIS)
  catalog_sync/      config, DB access, catalog parsing, /db/* endpoints
  requirements.txt, .env.example
synapse/             Synapse CLI steps as scripts
demo/                demo tasks and areas of interest (GeoJSON)
```
