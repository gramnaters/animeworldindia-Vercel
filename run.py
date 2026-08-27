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


@app.route('/__t')
def t():
    from app.routes import wawin_client
    from config import Config
    slug = 'arifureta-from-commonplace-to-worlds-strongest'
    url = f"{wawin_client._base_url()}/episode/{slug}-1x1/"
    out = {'scrape_url': Config.SCRAPE_API_URL, 'ep_url': url}
    try:
        resp = wawin_client._get(url, timeout=40)
        out['status'] = resp.status_code
        out['html_len'] = len(resp.text)
        out['has_zephyrix'] = 'zephyrix' in resp.text.lower() or 'zephyrflick' in resp.text.lower()
        out['cf'] = 'Attention Required' in resp.text or 'Just a moment' in resp.text
    except Exception as e:
        out['error'] = repr(e)
    return out



if __name__ == '__main__':
    # For development only - use gunicorn in production
    app.run(host='0.0.0.0', port=5000, debug=False)
