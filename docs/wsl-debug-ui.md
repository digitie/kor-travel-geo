# WSL local server and debug UI

This repository is commonly opened from WSL over a Windows-mounted workspace. In that
environment, bind local servers to `0.0.0.0` and prefer Linux executables inside WSL.
Windows `node.exe`/`npx` may be visible on `PATH`, but it can fail with WSL interop
errors.

## Backend

Use the project virtual environment and bind FastAPI to all WSL interfaces:

```bash
cd /mnt/f/dev/pykraddr
KRADDR_GEO_SPATIALITE_PATH=/mnt/f/dev/pykraddr/.codex_tmp/debug-kraddr.sqlite \
  .venv/bin/python -m uvicorn kraddr_geo_api.main:app \
  --app-dir backend \
  --host 0.0.0.0 \
  --port 3011
```

For a real local dataset, point `KRADDR_GEO_SPATIALITE_PATH` at the prepared
SQLite/SpatiaLite database. The runtime query path uses SQLAlchemy 2 asyncio through
`AsyncSpatialiteAddressStore`; bulk loaders may still use the synchronous store.

Quick checks:

```bash
curl -sS http://127.0.0.1:3011/health
curl -sS 'http://127.0.0.1:3011/addresses?query=Jahamun&scope=all&page_size=10'
curl -sS 'http://127.0.0.1:3011/reverse-geocode?x=953243.0&y=1954023.0&crs=EPSG:5179&max_distance_m=1'
```

On the 2026-05-20 WSL smoke run with a one-row debug DB, warm timings were about
45 ms for `/health`, 29 ms for `/addresses`, and 24 ms for `/reverse-geocode`.

## Web debug UI

Use the Linux Node bundled in this repo when system `node` is missing:

```bash
cd /mnt/f/dev/pykraddr/web
PATH=/mnt/f/dev/pykraddr/.wsl-node/node-v22.21.1-linux-x64/bin:$PATH \
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:3011 \
  npm run dev -- --hostname 0.0.0.0 --port 3010
```

Open `http://127.0.0.1:3010` from WSL. From Windows, `http://localhost:3010` usually
works when WSL localhost forwarding is enabled; otherwise use the WSL address from
`hostname -I`.

The UI uses `Noto Sans KR` through `next/font` so Korean labels render correctly even
when the WSL image lacks Korean system fonts.

## Headless browser smoke

If Playwright's Chromium fails with `libasound.so.2` and sudo is unavailable, cache
the library locally and pass it through `LD_LIBRARY_PATH`:

```bash
mkdir -p /tmp/playwright-libs
cd /tmp/playwright-libs
apt-get download libasound2t64
dpkg-deb -x libasound2t64_*.deb .

LD_LIBRARY_PATH=/tmp/playwright-libs/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH \
  npx -y playwright@1.57.0 screenshot http://127.0.0.1:3010 /tmp/kraddr-ui.png
```

The 2026-05-20 smoke path was: app loads, search `Jahamun`, the seeded
`Seoul Jongno-gu Jahamun-ro 96` row appears, and desktop/mobile screenshots render
without console errors.
