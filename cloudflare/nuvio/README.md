# nuvio — Cloudflare Worker addon

Full-Cloudflare deployment of the Anime World India addon.

- **Live:** https://nuvio.gramnaters.workers.dev
- **Config page:** https://nuvio.gramnaters.workers.dev/configure
- **Install:** `stremio://nuvio.gramnaters.workers.dev/manifest.json`

## Files

| File | Purpose |
|---|---|
| `worker.js` | Scraper (linkedom), TMDB→IMDb mapping, D1 cache, Stremio routes (`/manifest`, `/catalog`, `/meta`, `/stream`), config page, HLS playlist handoff |
| `logo.js` | Base64-embedded addon logo (auto-generated) |
| `page.js` | Embedded config page HTML/CSS/JS (auto-generated from the Vercel template) |
| `wrangler.toml` | Worker name, D1 binding, hourly cron |
| `schema.sql` | D1 tables (`mappings`, `failed_mappings`, `slug_imdb`, `as_map`) |
| `package.json` | `linkedom` dependency |

## Deploy

```bash
npm install
npx wrangler d1 execute anw-mappings --remote --file=schema.sql   # first time
npx wrangler secret put TMDB_API_KEY
npx wrangler deploy
```

## Architecture

```
nuvio  → manifest, catalogs, meta, stream, config page, logo   (this worker)
anw    → HLS playlists for zephyrix (master/variant)           (separate worker)
nuvio  → HLS playlists for animesalt/ravok (/as/hls, /as/v)    (this worker)
s11.*  → zephyrix video segments, fetched directly by the player
as-cdn*.top → animesalt video segments, fetched directly by the player
```

Only playlists touch a worker; video bytes go CDN → client.

## Providers

1. **watchanimeworld** (primary) — `zephyrix` player. Segments need
   `Referer: https://play.zephyrix.org/`, so the addon hands the client
   `proxyHeaders`.
2. **animesalt.cx** (fallback) — used only when the primary returns no streams:
   - search `/?s=<title>` → `/series/<slug>/` or `/movies/<slug>/`
   - episode page iframe → `ravok.buzz/video/<id>`
   - `POST ravok.buzz/player/index.php?data=<id>&do=getVideo` → tokenized master
   - the worker proxies the master (`/as/hls/<b64>`) and rewrites its variant
     URIs through `/as/v/<b64>`; **segments need no headers**, so the client
     fetches them straight from `as-cdn*.top`
   - if the primary site lists no episodes for a series, the episode list is
     borrowed from animesalt (meta fallback)
   - IMDb→slug is cached in D1 table `as_map`

## Known data limitations (source-side, not addon bugs)

- Some series have non-standard season/episode numbering on the site (e.g. *Farming Life in Another World* starts at S1E11). Episode URLs that 404 now return an empty stream list (200), never a 5xx.
- *BLACK TORCH* and *Skeleton Knight in Another World* have no episodes on the primary site; animesalt lists them, but every `ravok` embed for *BLACK TORCH* answers `Video not found`, so it still plays nothing. *Skeleton Knight* plays through the fallback.
- *Pokémon Heroes* only has the ad-gated `abyssplayer` iframe on both sites (no `zephyrix`/`ravok` source), so no stream is available.
