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


@app.route('/debug')
def debug():
    import traceback
    results = {}
    try:
        results['tmdb_key'] = bool(Config.TMDB_API_KEY)
        results['db_type'] = Config.DB_TYPE
        results['protocol'] = Config.PROTOCOL
    except Exception as e:
        results['config_error'] = str(e)

    try:
        from app.resolver import get_watchanimeworld_base_url, get_zephyrix_base_url
        results['ww_url'] = get_watchanimeworld_base_url()
        results['zephyrix_url'] = get_zephyrix_base_url()
    except Exception as e:
        results['resolver_error'] = str(e)

    try:
        from app.routes import wawin_client
        drops = wawin_client.get_newest_drops()
        results['drops_count'] = len(drops)
        if drops:
            results['first_drop'] = drops[0]
    except Exception as e:
        results['wawin_error'] = traceback.format_exc()

    try:
        from app.mapper import get_or_create_imdb_mapping
        slug = 'one-piece' if 'one-piece' in str(results.get('drops_count', '')) else None
        if results.get('drops_count', 0) > 0:
            first = results.get('first_drop', {})
            slug = first.get('slug', '')
            title = first.get('title', '')
            ct = first.get('type', 'series')
            poster = first.get('poster', '')
            imdb = get_or_create_imdb_mapping(slug, title, ct, poster)
            results['mapper_test'] = {'slug': slug, 'title': title, 'imdb': imdb}
    except Exception as e:
        results['mapper_error'] = traceback.format_exc()

    import json
    return json.dumps(results, indent=2, default=str)


if __name__ == '__main__':
    # For development only - use gunicorn in production
    app.run(host='0.0.0.0', port=5000, debug=False)
