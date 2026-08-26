import socket
import time
import requests
from cachetools import TTLCache

_domain_cache = TTLCache(maxsize=16, ttl=3600)

_KNOWN_DOMAINS = {
    'watchanimeworld': [
        'https://watchanimeworld.one',
        'https://watchanimeworld.net',
        'https://watchanimeworld.com',
        'https://animeworldindia.net',
    ],
    'zephyrix': [
        'https://play.zephyrix.org',
        'https://play.zephyrix.top',
        'https://zephyrix.org',
        'https://zephyrix.top',
    ],
}


def _check_domain(url, timeout=3):
    try:
        r = requests.head(url, timeout=timeout, allow_redirects=True)
        if r.status_code < 500:
            return r.url.rstrip('/')
    except Exception:
        pass
    return None


def _dns_resolve(hostname):
    try:
        socket.getaddrinfo(hostname, 443, socket.AF_INET)
        return True
    except socket.gaierror:
        return False


def resolve_domain(provider, force=False):
    cache_key = f'domain_{provider}'
    if not force and cache_key in _domain_cache:
        return _domain_cache[cache_key]

    candidates = _KNOWN_DOMAINS.get(provider, [])
    for url in candidates:
        hostname = url.split('//')[1].split('/')[0]
        if not _dns_resolve(hostname):
            continue
        result = _check_domain(url)
        if result:
            _domain_cache[cache_key] = result
            return result

    fallback = candidates[0] if candidates else None
    if fallback:
        _domain_cache[cache_key] = fallback
    return fallback


def get_watchanimeworld_base_url(force=False):
    return resolve_domain('watchanimeworld', force=force) or 'https://watchanimeworld.one'


def get_zephyrix_base_url(force=False):
    return resolve_domain('zephyrix', force=force) or 'https://play.zephyrix.org'


def invalidate_domain(provider):
    cache_key = f'domain_{provider}'
    _domain_cache.pop(cache_key, None)
