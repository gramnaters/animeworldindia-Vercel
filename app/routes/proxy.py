import base64
import re
import requests
from requests.adapters import HTTPAdapter
from flask import Blueprint, Response, request, abort
from urllib.parse import unquote
from cachetools import TTLCache
from config import Config
from .utils import get_random_agent
from app.resolver import get_zephyrix_base_url, invalidate_domain

proxy_bp = Blueprint('proxy', __name__)

subtitle_mappings = TTLCache(maxsize=500, ttl=3600)

# Reused CDN session with connection pooling. Without this every HLS segment
# pays a fresh DNS + TCP + TLS handshake to the CDN (~1.3s/segment -> stutter).
_cdn_session = requests.Session()
_cdn_adapter = HTTPAdapter(pool_connections=32, pool_maxsize=64, max_retries=1)
_cdn_session.mount('https://', _cdn_adapter)
_cdn_session.mount('http://', _cdn_adapter)

# Playlists are small and static per episode -> cache the raw upstream text so
# repeat playback / seeking doesn't refetch master+variant from the CDN.
playlist_cache = TTLCache(maxsize=256, ttl=600)

def reorder_audio_tracks(m3u8_content: str, preferred_lang: str) -> str:
    lines = m3u8_content.split('\n')
    audio_tracks = []
    other_lines = []
    preferred_track = None

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('#EXT-X-MEDIA:TYPE=AUDIO'):
            lang_match = re.search(r'LANGUAGE="([^"]+)"', line)
            if lang_match:
                track_lang = lang_match.group(1)
                if track_lang == preferred_lang:
                    line = re.sub(r'DEFAULT=(YES|NO)', 'DEFAULT=YES', line)
                    preferred_track = line
                else:
                    line = re.sub(r'DEFAULT=(YES|NO)', 'DEFAULT=NO', line)
                    audio_tracks.append(line)
            else:
                audio_tracks.append(line)
        else:
            other_lines.append((i, line))
        i += 1

    result = []
    audio_inserted = False

    for idx, line in other_lines:
        result.append(line)
        if line.startswith('#EXT-X-VERSION') and not audio_inserted:
            if preferred_track:
                result.append(preferred_track)
            result.extend(audio_tracks)
            audio_inserted = True

    return '\n'.join(result)

@proxy_bp.route('/cdn/hls/<path:path>')
@proxy_bp.route('/<lang>/cdn/hls/<path:path>')
def proxy_hls(path, lang=None):
    for attempt in range(2):
        base_url = get_zephyrix_base_url() if attempt == 0 else get_zephyrix_base_url(force=True)
        query_string = request.query_string.decode('utf-8')
        original_url = f"{base_url}/cdn/hls/{path}"
        if query_string:
            original_url += f"?{query_string}"

        try:
            headers = {
                'User-Agent': get_random_agent(),
                'Referer': f'{base_url}/'
            }

            raw = playlist_cache.get(original_url)
            if raw is None:
                resp = _cdn_session.get(original_url, headers=headers, timeout=30)
                if resp.status_code in (403, 429, 502, 503) and attempt == 0:
                    invalidate_domain('zephyrix')
                    continue
                resp.raise_for_status()
                raw = resp.text
                playlist_cache[original_url] = raw

            content = raw

            if lang:
                content = reorder_audio_tracks(content, lang)

            content = _rewrite_m3u8_paths(content, base_url)

            response = Response(content, mimetype='application/vnd.apple.mpegurl')
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = '*'
            return response
        except Exception as e:
            if attempt == 0:
                invalidate_domain('zephyrix')
                continue
            print(f"Error proxying HLS: {e}")
            abort(502)

    abort(502)


@proxy_bp.route('/hls/<token>.m3u8')
@proxy_bp.route('/<lang>/hls/<token>.m3u8')
def proxy_master_m3u8(token, lang=None):
    """Serve the upstream master playlist at a URL ending in .m3u8.

    mpv/ffmpeg will not reliably auto-detect HLS from the upstream
    ``.../master.txt`` (text/plain, and its probe window is full of long
    #EXT-X-MEDIA URIs). The source URL is passed as a base64url path token so
    the request path literally ends in ".m3u8" (a query string would break
    ffmpeg's extension detection). Variants are proxied back through here;
    segments stay absolute (direct from the CDN).
    """
    try:
        padded = token + '=' * (-len(token) % 4)
        original_url = base64.urlsafe_b64decode(padded).decode('utf-8')
    except Exception:
        abort(400)
    if not original_url.startswith('http'):
        abort(400)

    base_url = get_zephyrix_base_url()
    try:
        raw = playlist_cache.get(original_url)
        if raw is None:
            resp = _cdn_session.get(
                original_url,
                headers={'User-Agent': get_random_agent(), 'Referer': f'{base_url}/'},
                timeout=30,
            )
            resp.raise_for_status()
            raw = resp.text
            playlist_cache[original_url] = raw

        if lang:
            raw = reorder_audio_tracks(raw, lang)

        content = _rewrite_m3u8_paths(raw, base_url)
        response = Response(content, mimetype='application/vnd.apple.mpegurl')
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = '*'
        return response
    except Exception as e:
        print(f"Error proxying master m3u8: {e}")
        abort(502)


@proxy_bp.route('/m3/<path:path>')
@proxy_bp.route('/<lang>/m3/<path:path>')
def proxy_m3(path, lang=None):
    for attempt in range(2):
        base_url = get_zephyrix_base_url() if attempt == 0 else get_zephyrix_base_url(force=True)
        query_string = request.query_string.decode('utf-8')
        original_url = f"{base_url}/m3/{path}"
        if query_string:
            original_url += f"?{query_string}"

        try:
            headers = {
                'User-Agent': get_random_agent(),
                'Referer': f'{base_url}/'
            }

            raw = playlist_cache.get(original_url)
            if raw is None:
                resp = _cdn_session.get(original_url, headers=headers, timeout=30)
                if resp.status_code in (403, 429, 502, 503) and attempt == 0:
                    invalidate_domain('zephyrix')
                    continue
                resp.raise_for_status()
                raw = resp.text
                playlist_cache[original_url] = raw

            content = _rewrite_m3u8_paths(raw, base_url)

            response = Response(content, mimetype='application/vnd.apple.mpegurl')
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = '*'
            return response
        except Exception as e:
            if attempt == 0:
                invalidate_domain('zephyrix')
                continue
            print(f"Error proxying M3: {e}")
            abort(502)

    abort(502)


def _rewrite_m3u8_paths(content, base_url):
    """Rewrite paths in an m3u8.

    Playlists (master/variant) always come back through this addon so they are
    served with a proper ``application/vnd.apple.mpegurl`` content-type (mpv/
    ffmpeg refuses to parse the CDN's ``text/plain`` playlists).

    Segment URLs, however, are left ABSOLUTE by default so the player fetches
    the actual video bytes straight from the CDN (instant, zero addon
    bandwidth). The player sends the ``Referer`` via behaviorHints.proxyHeaders,
    which the CDN requires. Set DIRECT_SEGMENTS=0 to relay segments too.
    """
    host = Config.PROTOCOL + '://' + request.host

    def rewrite_url(url):
        if url.startswith('http'):
            if Config.DIRECT_SEGMENTS:
                return url
            encoded = base64.urlsafe_b64encode(url.encode()).decode().rstrip('=')
            return f'{host}/proxy/segment/{encoded}'
        if url.startswith('/m3/'):
            return f'{host}{url}'
        if url.startswith('/hls/'):
            return f'{host}/cdn/hls{url[len("/hls"):]}'
        return f'{host}{url}'

    def replace_uri(match):
        prefix = match.group(1)
        path = match.group(2)
        return f'{prefix}{rewrite_url(path)}"'

    content = re.sub(r'(URI=")([^"]+)"', replace_uri, content)

    def replace_line(match):
        path = match.group(1)
        return rewrite_url(path)

    content = re.sub(r'^([^#\s][^\s]*)$', replace_line, content, flags=re.MULTILINE)

    return content


@proxy_bp.route('/proxy/segment/<path:encoded>')
@proxy_bp.route('/<lang>/proxy/segment/<path:encoded>')
def proxy_segment(encoded):
    try:
        padded = encoded + '=' * (-len(encoded) % 4)
        original_url = base64.urlsafe_b64decode(padded).decode('utf-8')
    except Exception:
        abort(400)

    base_url = get_zephyrix_base_url()
    headers = {
        'User-Agent': get_random_agent(),
        'Referer': f'{base_url}/'
    }

    try:
        resp = _cdn_session.get(original_url, headers=headers, timeout=30, stream=True)
        resp.raise_for_status()

        ct = resp.headers.get('Content-Type', 'application/octet-stream')
        cl = resp.headers.get('Content-Length')

        def generate():
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    yield chunk

        response = Response(generate(), status=resp.status_code, mimetype=ct)
        if cl:
            response.headers['Content-Length'] = cl
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = '*'
        return response
    except Exception as e:
        print(f"Error proxying segment: {e}")
        abort(502)

@proxy_bp.route('/subtitles/<subtitle_id>')
def proxy_subtitle(subtitle_id):
    original_url = subtitle_mappings.get(subtitle_id)
    if not original_url:
        encoded_url = request.args.get('u', '')
        if encoded_url:
            try:
                encoded_url += '=' * (-len(encoded_url) % 4)
                original_url = base64.urlsafe_b64decode(encoded_url).decode('utf-8')
            except Exception:
                pass
    if not original_url:
        abort(404)

    base_url = get_zephyrix_base_url()
    try:
        headers = {
            'User-Agent': get_random_agent(),
            'Referer': f'{base_url}/'
        }

        resp = requests.get(original_url, headers=headers, timeout=30)
        resp.raise_for_status()

        if subtitle_id.endswith('.srt'):
            content_type = 'application/x-subrip'
        else:
            content_type = 'text/vtt'

        response = Response(resp.content, mimetype=content_type)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = '*'
        return response
    except Exception as e:
        print(f"Error proxying subtitle: {e}")
        abort(502)
