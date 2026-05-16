# Code guide for beginners

This project has three main layers.

## Library

`src/kraddr/geo` contains the Python package.

- `data.py`: road-name address archive download and parsing.
- `legal_dong.py`: legal-dong code API parsing.
- `reverse.py`: navigation TXT parsing and simple reverse-geocoder helpers.
- `spatialite.py`: SQLite/SpatiaLite schema, loaders, geocoding, reverse geocoding, postal-code lookup.
- `dto.py`: Pydantic request/response DTOs for VWorld-like calls.

Start with `spatialite.py` if you want to understand the current GIS behavior.

## Backend

`backend/kraddr_geo_api` exposes the store through FastAPI.

- `config.py`: environment variables.
- `database.py`: shared `SpatialiteAddressStore` instance and query helpers.
- `ingest.py`: manual upload load jobs, file classification, progress snapshots.
- `main.py`: HTTP routes.

## Web

`web/` is a Next.js address browser. It keeps the existing user-facing flow: sample search, full address list, paging, map preview, layer toggles, and manual file upload loading.

## Typical development loop

```powershell
python -m pytest -q
python -m ruff check .
cd web
npm run lint
npm run test
npm run build
```

For real-data validation, load `data/juso` into a local SQLite file first, then run direct `SpatialiteAddressStore` function calls for geocoding, reverse geocoding, postal-code lookup, and index-plan checks.
