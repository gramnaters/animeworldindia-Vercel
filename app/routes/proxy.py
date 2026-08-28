import base64
import re
import requests
from flask import Blueprint, Response, request, abort
from urllib.parse import urljoin
from cachetools import TTLCache
from config import Config
from .utils import get_random_agent

proxy_bp = Blueprint('proxy', __name__)

# Store subtitle mappings with TTL (1 hour expiration, max 500 entries)
subtitle_mappings = TTLCache(maxsize=500, ttl=3600)

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
    'Access-Control-Allow-Headers': '*',
}


def _b64e(url: str) -> str:
    """URL-safe base64 without padding (safe inside a path segment)."""
    return base64.urlsafe_b64encode(url.encode()).decode().rstrip('=')


def _b64d(b64: str) -> str:
    return base64.urlsafe_b64decode(b64 + '=' * (-len(b64) % 4)).decode()


def proxify(url: str) -> str:
    """Wrap an absolute URL so it is fetched through this addon's passthrough route."""
    return f"/cdn/p/{_b64e(url)}"


def rewrite_m3u8(content: str, base_url: str) -> str:
    """
    Rewrite EVERY URL in an m3u8 to route through our proxy:
    - non-comment lines (segment/variant URIs): absolute or relative -> proxied absolute
    - URI="..." attributes (audio groups, keys, maps) -> proxied absolute
    Relative references are resolved against base_url first, otherwise players
    would resolve them against our proxy path and break.
    """
    def wrap(url: str) -> str:
        url = url.strip()
        if not url or url.startswith('#'):
            return url
        return proxify(urljoin(base_url, url))

    out = []
    for line in content.splitlines():
        if line.startswith('#'):
            line = re.sub(r'URI="([^"]+)"',
                          lambda m: f'URI="{wrap(m.group(1))}"', line)
            out.append(line)
        else:
            out.append(wrap(line))
    return '\n'.join(out)


def reorder_audio_tracks(m3u8_content: str, preferred_lang: str) -> str:
    """
    Reorder audio tracks in m3u8 to set preferred language as DEFAULT=YES and first
    """
    lines = m3u8_content.split('\n')
    audio_tracks = []
    other_lines = []
    preferred_track = None

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('#EXT-X-MEDIA:TYPE=AUDIO'):
            # Extract language from track
            lang_match = re.search(r'LANGUAGE="([^"]+)"', line)
            if lang_match:
                track_lang = lang_match.group(1)
                if track_lang == preferred_lang:
                    # Set as DEFAULT=YES
                    line = re.sub(r'DEFAULT=(YES|NO)', 'DEFAULT=YES', line)
                    preferred_track = line
                else:
                    # Set as DEFAULT=NO
                    line = re.sub(r'DEFAULT=(YES|NO)', 'DEFAULT=NO', line)
                    audio_tracks.append(line)
            else:
                audio_tracks.append(line)
        else:
            other_lines.append((i, line))
        i += 1

    # Rebuild m3u8 with preferred track first
    result = []
    audio_inserted = False

    for idx, line in other_lines:
        result.append(line)
        # Insert audio tracks after #EXT-X-VERSION line
        if line.startswith('#EXT-X-VERSION') and not audio_inserted:
            if preferred_track:
                result.append(preferred_track)
            result.extend(audio_tracks)
            audio_inserted = True

    return '\n'.join(result)


def _upstream_headers(url: str) -> dict:
    # zephyrix AND its segment CDNs (zn-grid*.top) require the player-page
    # Referer; without it segments return 403.
    return {
        'User-Agent': get_random_agent(),
        'Referer': 'https://play.zephyrix.org/',
    }


def _looks_like_m3u8(content_type: str, url: str, first_bytes: bytes) -> bool:
    if 'mpegurl' in content_type.lower():
        return True
    if url.split('?')[0].endswith(('.m3u8', '.txt')):
        return first_bytes.lstrip()[:7] == b'#EXTM3U'
    return first_bytes.lstrip()[:7] == b'#EXTM3U'


@proxy_bp.route('/cdn/p/<b64url>')
@proxy_bp.route('/<lang>/cdn/p/<b64url>')
def proxy_passthrough(b64url: str, lang: str = None):
    """
    Universal passthrough for playlists AND media segments.
    The player only ever talks to this addon; zephyrix/CDN hosts are reached
    server-side with correct headers. m3u8 bodies get every URL re-proxied.
    """
    try:
        url = _b64d(b64url)
    except Exception:
        abort(400)
    if not url.startswith(('http://', 'https://')):
        abort(400)

    try:
        # NOTE: no stream=True here — partially consuming iter_content discards
        # urllib3's internal buffer and .content would come back empty.
        # HLS segments are small (KBs to ~1MB), a full read is safe.
        resp = requests.get(url, headers=_upstream_headers(url), timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"Error proxying {url[:90]}: {e}")
        abort(502)

    body = resp.content
    content_type = resp.headers.get('Content-Type', 'application/octet-stream')

    if _looks_like_m3u8(content_type, url, body[:8]):
        text = body.decode('utf-8', errors='replace')
        text = rewrite_m3u8(text, url)
        if lang:
            text = reorder_audio_tracks(text, lang)
        return Response(text, mimetype='application/vnd.apple.mpegurl',
                        headers=CORS_HEADERS)

    # Binary segment passthrough
    return Response(body, content_type=content_type or 'application/octet-stream',
                    headers=CORS_HEADERS)


@proxy_bp.route('/cdn/hls/<path:path>')
@proxy_bp.route('/<lang>/cdn/hls/<path:path>')
def proxy_hls(path, lang=None):
    """
    Proxy the master playlist (master.txt / master.m3u8) and rewrite every
    URL inside it (audio groups + quality variants) to the passthrough route.
    """
    query_string = request.query_string.decode('utf-8')
    original_url = f"https://play.zephyrix.org/cdn/hls/{path}"
    if query_string:
        original_url += f"?{query_string}"

    try:
        resp = requests.get(original_url, headers=_upstream_headers(original_url),
                            timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"Error proxying HLS: {e}")
        abort(502)

    content = resp.text
    if lang:
        content = reorder_audio_tracks(content, lang)
    content = rewrite_m3u8(content, original_url)

    response = Response(content, mimetype='application/vnd.apple.mpegurl')
    for k, v in CORS_HEADERS.items():
        response.headers[k] = v
    return response


@proxy_bp.route('/subtitles/<subtitle_id>')
def proxy_subtitle(subtitle_id):
    """
    Proxy subtitle files with correct content-type
    """
    original_url = subtitle_mappings.get(subtitle_id)
    if not original_url:
        abort(404)

    try:
        resp = requests.get(original_url, headers=_upstream_headers(original_url),
                            timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"Error proxying subtitle: {e}")
        abort(502)

    if subtitle_id.endswith('.srt'):
        content_type = 'application/x-subrip'
    else:
        content_type = 'text/vtt'

    response = Response(resp.content, mimetype=content_type)
    for k, v in CORS_HEADERS.items():
        response.headers[k] = v
    return response
