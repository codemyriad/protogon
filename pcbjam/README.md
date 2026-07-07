# Protogon in the browser (pcbjam)

Open the Protogon board in [pcbjam](https://github.com/emergence-engineering/pcbjam)
— KiCad's PCB editor compiled to WebAssembly — straight in a browser, with the 3D
component models. No KiCad install, no backend, no account.

```sh
./pcbjam/run.sh
```

Pulls a prebuilt image from GHCR (or builds it locally), serves it, and opens
`http://localhost:8080/`, which lands directly in the PCB editor with the board
loaded. `Ctrl-C` stops it.

## What this is

A build that bakes three things into one **self-contained static site**:

- the **pcbjam standalone** web app (the React/Vite shell + KiCad-WASM),
- the **Protogon project** (`codemyriad-protogon.kicad_pcb` + its custom 3D models),
- every **3D model** the board references — the stock parts (resistors, cap, LED,
  pin header) and the custom ones (Qwiic connector, EEPROM, jumper).

Everything is served **same-origin**, so once built there is **no runtime
dependency** on pcbjam's servers — it drops onto any static host, including a
BunnyCDN bucket.

Nothing here compiles KiCad. The ~200 MB of prebuilt WASM and the ~1 MB of 3D
models are **downloaded** from pcbjam's public CDN *at build time* and copied into
the bundle; only the small web shell is built from source. Pinned to pcbjam
`v0.1.6.2` / WASM `v0.1.5` / kicad-models `10.0.3`.

## Layout

| Path | What |
|---|---|
| `run.sh` | pull-or-build the GHCR image and open the board locally |
| `deploy-pgs.sh` | build + deploy to a pico.sh **pgs.sh** project (default under `/board-editor`) |
| `deploy-bunny.sh` | push the built site to a BunnyCDN Storage Zone |
| `Dockerfile` | 2-stage: build the static site → serve it with nginx |
| `Dockerfile.dockerignore` | keeps the Docker context tiny |
| `build/build-dist.sh` | the actual recipe (runs in Docker or on a dev box) |
| `build/gallery.json` | the Protogon gallery entry (the one board) |
| `build/nginx.conf` | COOP/COEP + wasm/tar.gz mime + SPA fallback |
| `../.github/workflows/pcbjam-image.yml` | CI: build the image and push to GHCR |

The image is `ghcr.io/codemyriad/protogon-pcbjam`. The repo stays light — no WASM,
no vendored pcbjam source, no `node_modules` in git; the heavy artifact lives in
GHCR, and the board + 3D models it uses are already in this repo.

## Build the site without Docker

```sh
BOARD_SRC="$(git rev-parse --show-toplevel)" OUT_DIR=./dist ./pcbjam/build/build-dist.sh
```

Needs `node >=20`, `corepack`, `git`, `curl`, `jq`. Serve `./dist` with any host
that sends `Cross-Origin-Opener-Policy: same-origin` +
`Cross-Origin-Embedder-Policy: require-corp` (see `build/nginx.conf`).

## Deploy to pgs.sh

Live at **https://silvio-protogon-kicad.pgs.sh/board-editor/**.

```sh
./pcbjam/deploy-pgs.sh                       # -> https://<user>-protogon-kicad.pgs.sh/board-editor/
PROJECT=foo SITE_BASE=/ ./pcbjam/deploy-pgs.sh   # different project / serve at the root
```

Builds under the subpath (`SITE_BASE`, default `/board-editor/`) and rsyncs to the
[pico.sh pgs.sh](https://pico.sh/pgs) project (needs your SSH key registered with
pico.sh). Three pgs.sh quirks it handles for you:

- **100 MB per-file cap.** The ~130 MB `kicad_editor.wasm` is split into `<name>.partN.wasm`
  pieces that a patched loader (`build-dist.sh` patches `boot.ts`) reassembles in the
  browser — the site stays fully self-contained.
- **`_headers` rules do NOT accumulate** (most-specific path wins and *replaces*).
  So the COOP/COEP/CORP isolation headers are repeated in every rule; without CORP on
  `/…/wasm/*`, KiCad's pthread worker scripts stall under COEP and the editor never boots.
- **Immutable assets are edge-cached with their headers**, so `deploy-pgs.sh` purges the
  zone cache (`ssh pgs.sh cache <project> --write`) after every deploy — otherwise a
  header change keeps serving the old (broken) headers.

## Deploy to BunnyCDN

```sh
BUNNY_STORAGE_ZONE=my-zone BUNNY_STORAGE_PASSWORD=xxxxx ./pcbjam/deploy-bunny.sh
```

Uploads the image's `dist/` to the Storage Zone, then prints the Pull Zone
settings BunnyCDN needs (it does not read `nginx.conf`): the COOP/COEP headers,
the `.wasm` / `images.tar.gz` content rules, the SPA fallback, and the `/` → board
redirect.

## How it works (the moving parts)

- **WASM** (`dist/wasm/<ver>/`, immutable + cache-forever): `kicad_editor.*` (the PCB
  editor) + `occ_service.*` (STEP tessellation — needed for the board's STEP models) +
  `wx.js`, `wx-dom.js`, `images.tar.gz`. The version segment is a semantic,
  content-changing URL (bump `WASM_VER` → new URL), so the big assets cache forever.
  `images.tar.gz` is **raw gzip** KiCad unpacks itself, so it is served
  `application/octet-stream` with **no** `Content-Encoding`.
- **Gallery** (`dist/content/protogon/`): the board bytes + a manifest. The app is
  built with `VITE_PROJECT_SOURCE=static` pointing at it, so the site needs no
  backend.
- **3D models** (`dist/libs/kicad-models/`): only the four stock bodies the board
  uses, mirrored from the CDN's sparse model set. The three custom models ship as
  project files (`packages3d/*.step`) so KiCad resolves them by relative path.
- **Auto-open**: the app's `/` route redirects (client-side, `App.tsx` `<Navigate>`)
  to `…/demo/projects/codemyriad-protogon/codemyriad-protogon.kicad_pcb`, so opening
  the site root drops straight into the board — the same at the domain root or under a
  subpath, with no server redirect needed.
- **Subpath** (`SITE_BASE`): Vite `base` + a React Router `basename` patch + prefixed
  asset URLs let the whole site live under e.g. `/board-editor/`.

## Notes

- **Cross-origin isolation is mandatory.** The editor needs `SharedArrayBuffer`,
  so the page must be served with COOP `same-origin` + COEP `require-corp` over a
  secure context (HTTPS, or `http://localhost`). A plain-HTTP LAN IP will not boot.
- The site is **read-only**: edits stay in the browser and "Save" downloads a file;
  the original board is never touched.
- Bumping the pcbjam/WASM/models versions is `--build-arg` (Dockerfile) or the env
  knobs documented at the top of `build/build-dist.sh`.
