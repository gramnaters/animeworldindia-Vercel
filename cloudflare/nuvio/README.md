# nuvio — Cloudflare Worker addon

Full-Cloudflare deployment of the Anime World India addon.

- **Live:** https://nuvio.gramnaters.workers.dev
- **Config page:** https://nuvio.gramnaters.workers.dev/configure
- **Install:** `stremio://nuvio.gramnaters.workers.dev/manifest.json`

## Files

| File | Purpose |
|---|---|
| `worker.js` | Scraper (linkedom), TMDB→IMDb mapping, D1 cache, Stremio routes (`/manifest`, `/catalog`, `/meta`, `/stream`), provider layer, HLS playlist handoff |
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

Both sites run the **same CMS**, so they carry the same titles but different
episode lists. The addon queries both and emits **one labelled stream per
site**, so the viewer picks:

| Badge | Source | Player | Notes |
|---|---|---|---|
| `ANIME WORLD` | watchanimeworld | zephyrix | segments need `Referer`, sent as `proxyHeaders` |
| `ANIME SALT` | animesalt.cx | ravok | playlists proxied via `/as/hls`, `/as/v`; segments need no headers |

Flow in `/stream`:

1. `provWatchAnimeWorld` and `provAnimeSalt` start **in parallel**, each with
   its own timeout (9 s / 20 s). A failure on one side never hides the other.
2. Each success is formatted by `labelStreams` into a Stremio stream with
   `name` = site badge, `description` = site + player, `behaviorHints.filename`
   and a per-site `bingeGroup` (so binge-watching stays on one provider).
3. The response is cached 900 s when both providers behaved, 120 s when one
   failed, so a bad scrape doesn't stick for long.

AnimeSalt lookup order (cheapest first):

1. D1 `as_map` row (imdb → slug), validated against the expected type.
2. **The primary slug itself** — same CMS, same slugs. One page fetch, no TMDB.
   This is why titles whose TMDB name differs still resolve.
3. Site search by TMDB title, ranked by token overlap + type.

### Episode lists (/meta)

Primary list, topped up from AnimeSalt **only when the AnimeSalt list is the
longer one** (AnimeSalt always numbers from season 1, so merging its shorter
lists would invent episodes). Gained ~116 episodes on 14 series this way
(FMA:B 39→64, Tomb Raider King 4→12, Skeleton Knight 0→12, …) while leaving
multi-season numbering untouched (Wind Breaker stays 25, Re:Zero stays 77).

`asSeriesEpisodes` caches each AnimeSalt episode list for 1 h; the same cache
powers the "does AnimeSalt even have this episode?" pre-check, so the ~2.5k
episodes only the primary carries never pay for a second provider.

## Known data limitations (source-side, not addon bugs)

- *BLACK TORCH*: AnimeSalt lists 10 episodes but every `ravok` embed replies
  `Video not found`; the fallback player on that page is an ad-gated
  `abyssplayer` (JWPlayer + AES-CTR payload), so it plays nothing.
- *Pokémon Heroes*: only the ad-gated `abyssplayer` iframe on both sites, no
  `zephyrix`/`ravok` source — no stream available.
- *Wind Breaker* S1 exists only on AnimeSalt, *Re:Zero*/*Arifureta* carry extra
  seasons only on the primary site; the union covers both where the numbering
  can be trusted.
- Some series use non-standard numbering on the primary site (e.g. *Farming
  Life in Another World* starts at S1E11). Missing episode pages return an empty
  stream list (200), never a 5xx.
