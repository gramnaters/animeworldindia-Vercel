import re
import base64
import requests
from app.routes.utils import get_random_agent
from config import Config
from app.resolver import get_zephyrix_base_url, invalidate_domain

async def get_video_from_zephyrflick_player(player_url: str, preferred_lang: str = None, host: str = 'localhost'):
    """
    Extract video URL and subtitles from Zephyrflick player
    :param player_url: Zephyrflick player URL
    :param preferred_lang: Preferred audio language (e.g. 'hin', 'eng', 'jpn')
    :return: tuple (video_url, quality, headers, subtitles)
    """
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
            video_url = data.get('videoSource')

            if not video_url:
                return None, None, None, []

            proto = Config.PROTOCOL
            if preferred_lang:
                video_url = video_url.replace(base_url, f'{proto}://{host}/{preferred_lang}')
            else:
                video_url = video_url.replace(base_url, f'{proto}://{host}')

            stream_headers = {
                'request': {
                    'Referer': f'{base_url}/'
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

            return video_url, 'auto', stream_headers, subtitles

        except Exception as e:
            if attempt == 0:
                invalidate_domain('zephyrix')
                continue
            print(f"Error extracting Zephyrflick video: {e}")
            return None, None, None, []

    return None, None, None, []
