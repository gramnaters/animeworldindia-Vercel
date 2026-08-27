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
    
    # Trawl scrape API (bypasses Cloudflare from Vercel IPs).
    # Defaults to the project's free Cloudflare Worker relay; override via env if you host your own.
    SCRAPE_API_URL = os.getenv('SCRAPE_API_URL', 'https://awin-trawl-relay.gramnaters.workers.dev')
    
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
