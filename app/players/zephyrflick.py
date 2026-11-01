import re
import base64
import requests
from cachetools import TTLCache
from app.routes.utils import get_random_agent
from config import Config
from app.resolver import get_zephyrix_base_url, invalidate_domain

# Resolving the player URL (POST to play.zephyrix.org) costs a few hundred ms on
# every /stream request. The result (CDN master URL + headers) is stable, so
# cache it briefly to make repeat plays open instantly.
_resolve_cache = TTLCache(maxsize=256, ttl=900)

async def get_video_from_zephyrflick_player(player_url: str, preferred_lang: str = None, host: str = 'localhost', mode: str = None):
    """
    Extract video URL and subtitles from Zephyrflick player
    :param player_url: Zephyrflick player URL
    :param preferred_lang: Preferred audio language (e.g. 'hin', 'eng', 'jpn')
    :param mode: 'direct' (CDN URL + proxyHeaders) or 'proxy' (relay through addon)
    :return: tuple (video_url, quality, headers, subtitles)
    """
    stream_mode = (mode or Config.STREAM_MODE or 'proxy').lower()
    cache_key = f'{player_url}|{preferred_lang}|{host}|{stream_mode}'
    cached = _resolve_cache.get(cache_key)
    if cached is not None:
        return cached

    for attempt in range(2):
        try:
            base_url = get_zephyrix_base_url()

            match = re.search(r'/video/([a-f0-9]+)', player_url)
            if not match:
                return None, None, None, []

            video_id = match.group(1)

            api_headers = {
                'User-Agent': get_random_agent(),
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': player_url
            }

            api_url = f"{base_url}/player/index.php"
            params = {
                'data': video_id,
                'do': 'getVideo'
            }

            resp = requests.post(api_url, params=params, headers=api_headers, timeout=30)

            if resp.status_code in (403, 429, 502, 503) and attempt == 0:
                invalidate_domain('zephyrix')
                continue

            resp.raise_for_status()

            data = resp.json()
            video_source = data.get('videoSource')
            secured_link = data.get('securedLink')

            if not video_source and not secured_link:
                return None, None, None, []

            # Delivery:
            #   proxy  -> serve the master as /hls/<token>.m3u8 via this addon
            #             (variants also via addon; segments direct from CDN).
            #   direct -> hand the player the CDN's tokenized master.m3u8 URL and
            #             let it fetch everything itself (no addon in the video
            #             path at all). The .m3u8 URL is required: the plain
            #             master.txt is text/plain and mpv/ffmpeg detect it as tty.
            if stream_mode == 'proxy':
                proto = Config.PROTOCOL
                prefix = f'{proto}://{host}' + (f'/{preferred_lang}' if preferred_lang else '')
                token = base64.urlsafe_b64encode(video_source.encode()).decode().rstrip('=')
                video_url = f'{prefix}/hls/{token}.m3u8'
            else:
                # direct: hand the player the plain CDN master. Works on
                # ExoPlayer (we declare type=hls) but NOT on mpv/ffmpeg, which
                # classify the text/plain master.txt as "tty".
                # Note: the *_securedLink* variant cannot be used here - its md5
                # token is bound to the IP that generated it (this server), so
                # clients always get 403.
                video_url = video_source

            # The CDN (s11.zn-grid*.top) and the master/variant playlists require
            # the player Referer (and a browser UA), otherwise segments return 403.
            stream_headers = {
                'request': {
                    'Referer': f'{base_url}/',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                }
            }

            subtitles = []
            try:
                page_resp = requests.get(player_url, headers=api_headers, timeout=30)
                page_resp.raise_for_status()

                subtitle_match = re.search(r'var playerjsSubtitle = "([^"]+)"', page_resp.text)
                if subtitle_match:
                    subtitle_data = subtitle_match.group(1)
                    for line in subtitle_data.split('\n'):
                        line = line.strip()
                        if not line:
                            continue

                        sub_match = re.match(r'\[([^\]]+)\](.+)', line)
                        if sub_match:
                            lang_name = sub_match.group(1)
                            sub_url = sub_match.group(2)

                            lang_code = 'eng' if 'english' in lang_name.lower() else lang_name.lower()[:3]
                            file_ext = '.srt' if sub_url.endswith('.srt') else '.vtt'

                            encoded_url = base64.urlsafe_b64encode(sub_url.encode()).decode().rstrip('=')
                            subtitle_id = f"{video_id}_{lang_code}{file_ext}"
                            proxied_sub_url = f"{Config.PROTOCOL}://{host}/subtitles/{subtitle_id}?u={encoded_url}"

                            subtitles.append({
                                'id': f"{video_id}_{lang_code}",
                                'url': proxied_sub_url,
                                'lang': lang_code
                            })
            except:
                pass

            result = (video_url, 'auto', stream_headers, subtitles)
            _resolve_cache[cache_key] = result
            return result

        except Exception as e:
            if attempt == 0:
                invalidate_domain('zephyrix')
                continue
            print(f"Error extracting Zephyrflick video: {e}")
            return None, None, None, []

    return None, None, None, []
