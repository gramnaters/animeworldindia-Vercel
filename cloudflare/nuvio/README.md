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
| `schema.sql` | D1 tables (`mappings`, `failed_mappings`, `slug_imdb`) |
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
anw    → HLS playlists (master/variant)                         (separate worker)
s11.*  → video segments, fetched directly by the player
```

Only playlists touch a worker; video bytes go CDN → client.

## Known data limitations (source-side, not addon bugs)

- Some series have non-standard season/episode numbering on the site (e.g. *Farming Life in Another World* starts at S1E11). Episode URLs that 404 now return an empty stream list (200), never a 5xx.
- Movies using the site's `player1.php` player (e.g. *Pokémon Heroes*) expose no zephyrix source; that player is currently returning 522. No streams are available for those titles.
