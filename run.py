import logging

from flask import Flask, render_template, url_for, redirect, make_response, request
from flask_compress import Compress
from app.routes.catalog import catalog_bp
from app.routes.manifest import manifest_blueprint
from app.routes.meta import meta_bp
from app.routes.stream import stream_bp
from app.routes.proxy import proxy_bp
from app.routes.utils import cache
from config import Config
from app.api.watchanimeworld import WatchAnimeWorldAPI

app = Flask(__name__, template_folder='./templates', static_folder='./static')
app.config.from_object('config.Config')
app.register_blueprint(manifest_blueprint)
app.register_blueprint(catalog_bp)
app.register_blueprint(meta_bp)
app.register_blueprint(stream_bp)
app.register_blueprint(proxy_bp)

Compress(app)
cache.init_app(app)

logging.basicConfig(format='%(asctime)s %(message)s')


@app.route('/')
@app.route('/configure')
@app.route('/<lang>/configure')
def index(lang=None):
    from app.routes.manifest import MANIFEST
    import hashlib

    import os
    host = os.getenv('REDIRECT_URL') or request.headers.get('X-Forwarded-Host', request.host)
    if lang:
        manifest_url = f'https://{host}/{lang}/manifest.json'
        manifest_magnet = f'stremio://{host}/{lang}/manifest.json'
    else:
        manifest_url = f'https://{host}/manifest.json'
        manifest_magnet = f'stremio://{host}/manifest.json'

    html = render_template('index.html',
                          manifest_url=manifest_url,
                          manifest_magnet=manifest_magnet,
                          version=MANIFEST['version'],
                          lang=lang)

    response = make_response(html)

    etag = hashlib.md5(MANIFEST['version'].encode()).hexdigest()
    response.set_etag(etag)
    response.cache_control.max_age = 3600
    response.cache_control.public = True

    if request.headers.get('If-None-Match') == etag:
        return make_response('', 304)

    return response


@app.route('/favicon.ico')
def favicon():
    """
    Render the favicon for the app
    """
    return app.send_static_file('favicon.ico')


@app.route('/callback')
def callback():
    """
    Callback URL from MyAnimeList
    :return: A webpage response with the manifest URL and Magnet URL
    """
    return redirect(url_for('index'))



@app.route('/__diag')
def __diag():
    """TEMPORARY diagnostic - remove after verifying."""
    import json as _json
    from flask import request as _rq
    if _rq.args.get('k') != 'awin-diag-9x2':
        return make_response('', 404)
    out = {'scrape_api_url': Config.SCRAPE_API_URL}
    try:
        import curl_cffi as _c
        out['curl_cffi'] = getattr(_c, '__version__', 'unknown')
    except Exception as e:
        out['curl_cffi'] = 'MISSING: ' + repr(e)[:120]
    url = 'https://watchanimeworld.one/episode/arifureta-from-commonplace-to-worlds-strongest-1x1/'
    ua = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    import requests as _rq2
    for name in ('cffi', 'requests'):
        try:
            if name == 'cffi':
                from curl_cffi import requests as _cf
                resp = _cf.get(url, impersonate='chrome', timeout=25, headers=ua, allow_redirects=True)
            else:
                resp = _rq2.get(url, timeout=25, headers=ua)
            body = resp.text
            out[name] = {
                'status': resp.status_code,
                'len': len(body),
                'zephyr': 'zephyr' in body.lower(),
                'blocked': WatchAnimeWorldAPI._is_blocked(resp),
                'head': body[:160],
            }
        except Exception as e:
            out[name] = 'ERR ' + repr(e)[:160]
    return make_response(_json.dumps(out, indent=2), 200, {'Content-Type': 'application/json'})


if __name__ == '__main__':
    # For development only - use gunicorn in production
    app.run(host='0.0.0.0', port=5000, debug=False)
