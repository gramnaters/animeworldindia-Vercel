from flask import Blueprint, abort

from .utils import respond_with

manifest_blueprint = Blueprint('manifest', __name__)

MANIFEST = {
    'id': 'com.skoruppa.watchanimeworld-stremio-addon',
    'version': '0.2.0',
    'name': 'Anime World India Addon',
    'logo': 'https://animeworld-india.vercel.app/static/logo.png',
    'description': 'Watch anime in Hindi, Tamil, Telugu & English from WatchAnimeWorld.top',
    'types': ['anime', 'series', 'movie'],
    'idPrefixes': ['tt'],
    'catalogs': [
        {'type': 'anime', 'id': 'newest_drops', 'name': 'Newest Drops'},
        {'type': 'anime', 'id': 'most_watched_shows', 'name': 'Most-Watched Shows'},
        {'type': 'anime', 'id': 'new_arrivals', 'name': 'New Anime Arrivals'},
        {'type': 'anime', 'id': 'most_watched_films', 'name': 'Most-Watched Films'},
        {'type': 'anime', 'id': 'latest_movies', 'name': 'Latest Anime Movies'},
        {
            'type': 'anime',
            'id': 'search',
            'name': 'Search',
            'extra': [{'name': 'search', 'isRequired': True}]
        }
    ],
    'behaviorHints': {'configurable': True, 'configurationRequired': False},
    'resources': ['catalog', 'meta', 'stream'],
    'stremioAddonsConfig': {
        'issuer': 'https://stremio-addons.net',
        'signature': 'eyJhbGciOiJkaXIiLCJlbmMiOiJBMTI4Q0JDLUhTMjU2In0..7gV3q1MNizIqKIMz8e4qvw.DSKuF6iQaPJp9VOPWuafWVaMhN6a32S8fGxUXYcNqS7yaqP48Ys2__2p5On7XU14e6IOE5qy56xaZCqDi61J-hEThy76L6YtS0F6tyc140pdd65-7Mw_uiXin2gq9NV4.hjecT9eBaBcBrEy5MdVnCQ'
    }
}


def _manifest_for_request():
    """Return the manifest, honouring the ``?catalogs=0`` toggle.

    The web configuration page lets users disable the catalogs (Discover rows).
    When disabled we return a manifest without the ``catalog`` resource so
    Stremio hides the catalogs entirely; meta/stream keep working.

    The addon logo is served from this deployment's own ``/static/logo.png`` so
    it always resolves (the request host is used, or REDIRECT_URL if set).
    """
    import os
    from flask import request

    host = os.getenv('REDIRECT_URL') or request.headers.get('X-Forwarded-Host') or request.host
    manifest = dict(MANIFEST)
    manifest['logo'] = f'https://{host}/static/logo.png'

    value = (request.args.get('catalogs') or '1').strip().lower()
    if value in ('0', 'false', 'off', 'no'):
        manifest['catalogs'] = []
        manifest['resources'] = [r for r in MANIFEST['resources'] if r != 'catalog']
    return manifest


@manifest_blueprint.route('/manifest.json')
@manifest_blueprint.route('/<lang>/manifest.json')
def addon_manifest(lang=None):
    """
    Provides the manifest for the addon
    :param lang: Optional language prefix for backward compatibility
    :return: JSON response
    """
    return respond_with(_manifest_for_request(), 7200, use_etag=False)
