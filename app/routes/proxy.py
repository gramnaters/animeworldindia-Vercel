import base64
import re
import requests
from flask import Blueprint, Response, request, abort
from urllib.parse import unquote
from cachetools import TTLCache
from config import Config
from .utils import get_random_agent
from app.resolver import get_zephyrix_base_url, invalidate_domain

proxy_bp = Blueprint('proxy', __name__)

subtitle_mappings = TTLCache(maxsize=500, ttl=3600)

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

            resp = requests.get(original_url, headers=headers, timeout=30)

            if resp.status_code in (403, 429, 502, 503) and attempt == 0:
                invalidate_domain('zephyrix')
                continue

            resp.raise_for_status()

            content = resp.text

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

            resp = requests.get(original_url, headers=headers, timeout=30)

            if resp.status_code in (403, 429, 502, 503) and attempt == 0:
                invalidate_domain('zephyrix')
                continue

            resp.raise_for_status()

            content = resp.text
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
            print(f"Error proxying M3: {e}")
            abort(502)

    abort(502)


def _rewrite_m3u8_paths(content, base_url):
    """Rewrite absolute paths in m3u8 to go through the proxy"""
    host = Config.PROTOCOL + '://' + request.host

    def replace_uri(match):
        prefix = match.group(1)
        path = match.group(2)
        if path.startswith('http'):
            return match.group(0)
        if path.startswith('/m3/'):
            return f'{prefix}{host}{path}'
        if path.startswith('/hls/'):
            return f'{prefix}{host}/cdn/hls{path[len("/hls"):]}'
        return f'{prefix}{host}{path}'

    content = re.sub(r'(URI=")(/[^"]+)"', replace_uri, content)

    def replace_line(match):
        path = match.group(1)
        if path.startswith('http'):
            return match.group(0)
        if path.startswith('/m3/'):
            return f'{host}{path}'
        if path.startswith('/hls/'):
            return f'{host}/cdn/hls{path[len("/hls"):]}'
        return f'{host}{path}'

    content = re.sub(r'^(/[^#\s].+)$', replace_line, content, flags=re.MULTILINE)

    return content

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
