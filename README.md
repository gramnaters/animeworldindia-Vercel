# Anime World India Stremio Addon

![Version](https://img.shields.io/badge/version-0.2.0-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Status](https://img.shields.io/badge/status-Active-brightgreen.svg)

<div align="center">
  <img src="static/logo.png" alt="WatchAnimeWorld Logo" width="300">
</div>

This unofficial Stremio addon allows users to access anime streams from [AnimeWorld India](https://watchanimeworld.top/) - source for anime in Hindi, Tamil, Telugu & English.

## Supported Players

- **Zephyrflick** — primary streaming source with subtitle support

## Features

- Multiple language support: **Hindi, Tamil, Telugu & English**
- Subtitles in VTT/SRT format
- Multiple catalogs (can be disabled in the advanced settings):
  - **Newest Drops** — latest episode releases
  - **Most-Watched Shows** — popular anime series
  - **New Anime Arrivals** — recently added series
  - **Most-Watched Films** — popular anime movies
  - **Latest Anime Movies** — recently added movies
- Search functionality
- Multi-season support
- Instant seeking: playlists are served by the addon, while video segments stream directly from the CDN

## Usage

- Browse through the catalogs (or turn them off in advanced settings)
- Search for your favorite anime
- Watch with subtitles in multiple languages

## Installation

### Quick Install

1. Visit **[https://animeworld-india.vercel.app/](https://animeworld-india.vercel.app/)**
2. Click **"Install in Stremio"**
3. Confirm in Stremio and the addon is ready to use

### Manual Installation

1. Visit [https://animeworld-india.vercel.app/](https://animeworld-india.vercel.app/)
2. Copy the manifest URL
3. Open Stremio and go to the addon search box
4. Paste the manifest URL and press Enter
5. Click install

## Self-Hosting

### Prerequisites

- Python 3.11+
- TMDB API Key (required) — get it from [TMDB](https://www.themoviedb.org/settings/api)
- PostgreSQL or SQLite database

### Installation Steps

1. **Clone the repository**
```bash
git clone https://github.com/gramnaters/animeworldindia-Vercel.git
cd animeworldindia-Vercel
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Configure environment variables**

Create a `.env` file in the root directory:

```env
# Flask Configuration
FLASK_RUN_HOST=localhost
FLASK_RUN_PORT=5000
FLASK_DEBUG=False

# TMDB API Key (REQUIRED)
TMDB_API_KEY=your_tmdb_api_key_here

# Database Configuration
# For SQLite (default):
DB_TYPE=sqlite
DB_PATH=mappings.db

# For PostgreSQL:
# DB_TYPE=postgresql
# DATABASE_URL=postgresql://user:password@localhost:5432/dbname
```

4. **Run the addon**

**Development:**
```bash
python run.py
```

**Production (recommended):**
```bash
gunicorn -c gunicorn_config.py run:app
```

The addon will be available at `http://localhost:5000`.

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TMDB_API_KEY` | **Yes** | - | TMDB API key for IMDb mapping |
| `DB_TYPE` | No | `sqlite` | Database type (`sqlite` or `postgresql`) |
| `DB_PATH` | No | `mappings.db` | SQLite database file path |
| `DATABASE_URL` | No | - | PostgreSQL connection string |
| `FLASK_RUN_HOST` | No | `localhost` | Host to bind the server |
| `FLASK_RUN_PORT` | No | `5000` | Port to bind the server |
| `FLASK_DEBUG` | No | `False` | Enable debug mode |
| `GUNICORN_WORKERS` | No | `3` | Number of gunicorn workers |
| `STREAM_MODE` | No | `proxy` | `proxy` serves playlists via the addon; `direct` returns the CDN URL + proxyHeaders |
| `DIRECT_SEGMENTS` | No | `1` | `1` = video segments stream directly from the CDN |
| `DIRECT_VARIANTS` | No | `0` | `1` = variants direct from the CDN (breaks Android ExoPlayer; leave `0`) |
| `HLS_BASE` | No | - | Edge URL that serves the HLS playlists (e.g. a Cloudflare Worker). Empty = serve from this addon |
| `SCRAPE_API_URL` | No | - | Optional external solver (Trawl / FlareSolverr / relay) if the scraper is Cloudflare-blocked |

## Architecture

```
/stream  -> Vercel addon (scrape + TMDB mapping, edge-cached 10 min)
             returns  https://<HLS_BASE>/hls/<token>.m3u8  + proxyHeaders

hls/<token>.m3u8  -> Cloudflare Worker (UPSTREAM master, rewritten; cached 10 min)
m3/<token>        -> Cloudflare Worker (variant playlist; cached 10 min)
s11.zn-grid*.top  -> CDN directly (video segments, Referer via proxyHeaders)
```

Only two small playlist requests leave the client, and only `/stream` touches
Vercel. Playlists are served from the edge with no cold starts; video bytes go
CDN → client.

> **Vercel note:** the serverless functions must run outside ranges Cloudflare blocks. This project sets `"regions": ["bom1"]` in `vercel.json`; running in `iad1` gets a Cloudflare `403` on the scraper.

## API References

This addon is built with:

- **Stremio Addon SDK**: [official documentation](https://github.com/Stremio/stremio-addon-sdk)
- **WatchAnimeWorld.top**: website providing all the anime
- **TMDB API**: for IMDb ID mapping and metadata

## Help

If you encounter issues or have questions, open an issue at
[https://github.com/gramnaters/animeworldindia-Vercel/issues](https://github.com/gramnaters/animeworldindia-Vercel/issues).

## Credits

Original addon by [skoruppa on GitHub](https://github.com/skoruppa/anime-world-stremio-addon).
