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
    #   direct (default) -> return the upstream CDN master URL + proxyHeaders so
    #                       Stremio fetches variants/segments straight from the
    #                       CDN (instant seeking, zero addon bandwidth).
    #   proxy            -> relay all HLS through this addon (legacy/slow).
    STREAM_MODE = os.getenv('STREAM_MODE', 'direct').lower()

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
