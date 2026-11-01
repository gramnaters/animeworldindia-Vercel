import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    """
    Configuration class
    """
    FLASK_HOST = os.getenv('FLASK_RUN_HOST', "localhost")
    FLASK_PORT = os.getenv('FLASK_RUN_PORT', "5000")
    CACHE_TYPE = 'SimpleCache'
    CACHE_DEFAULT_TIMEOUT = 600

    DEBUG = os.getenv('FLASK_DEBUG', 'False')
    
    # TMDB API Key
    TMDB_API_KEY = os.getenv('TMDB_API_KEY', '')
    
    # External Cloudflare solver (optional). Supports Trawl /scrape, FlareSolverr
    # /v1, or a plain relay. Leave empty to rely on direct + curl_cffi TLS impersonation.
    SCRAPE_API_URL = os.getenv('SCRAPE_API_URL', '')
    
    # Stream delivery mode.
    #   proxy (default)  -> relay HLS through this addon (required: Stremio does
    #                       NOT apply proxyHeaders to HLS playlist sub-requests,
    #                       so direct CDN segments 403 without the Referer).
    #   direct           -> return the CDN URL + proxyHeaders (works only in
    #                       players that apply headers to sub-requests, not Stremio).
    STREAM_MODE = os.getenv('STREAM_MODE', 'proxy').lower()

    # Leave HLS segment URLs pointing straight at the CDN instead of relaying
    # every 2s chunk through the addon. This is what makes playback instant;
    # the client must send the Referer (we expose it via proxyHeaders).
    DIRECT_SEGMENTS = os.getenv('DIRECT_SEGMENTS', '1') in ('1', 'true', 'True', 'yes')

    # Send variant playlists straight from the CDN (absolute /m3/ URLs) instead
    # of routing them through the addon. Saves one request, BUT the CDN host
    # (play.zephyrix.org) is Cloudflare-protected and returns a non-playlist
    # body to Android's ExoPlayer TLS, so the default is OFF. Segments are
    # always direct regardless of this flag.
    DIRECT_VARIANTS = os.getenv('DIRECT_VARIANTS', '0') in ('1', 'true', 'True', 'yes')

    # MediaFlow Proxy (fallback, for bypassing geo/IP blocks on scraping requests)
    SCRAPER_PROXY_URL = os.getenv('SCRAPER_PROXY_URL', '')
    SCRAPER_PROXY_PASSWORD = os.getenv('SCRAPER_PROXY_PASSWORD', '')
    
    # Database configuration
    DB_TYPE = os.getenv('DB_TYPE', 'sqlite')  # 'sqlite' or 'postgresql'
    DB_PATH = os.getenv('DB_PATH', 'mappings.db')  # For SQLite
    DB_CONNECTION_STRING = os.getenv('DATABASE_URL', '')  # For PostgreSQL

    # Env dependent configs
    if DEBUG in ['1', 'True', 'true']:
        PROTOCOL = "http"
        REDIRECT_URL = f"{FLASK_HOST}:{FLASK_PORT}"
    else:
        PROTOCOL = "https"
        REDIRECT_URL = f"{FLASK_HOST}"
