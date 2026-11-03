// anw-scraper — Phase 1 of the full-Cloudflare port.
// Faithful JS port of app/api/watchanimeworld.py using linkedom (same CSS
// selectors as BeautifulSoup). Debug endpoints so its output can be diffed
// against the Python/Vercel scraper before any cut-over.

import { parseHTML } from 'linkedom';
import { LOGO_B64 } from './logo.js';
import { PAGE_HTML, PAGE_CSS, PAGE_JS } from './page.js';

const BASE = 'https://watchanimeworld.top';
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';
const HEADERS = {
  'User-Agent': UA,
  'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
  'Accept-Language': 'en-US,en;q=0.9',
  'Upgrade-Insecure-Requests': '1',
  'Referer': 'https://www.google.com/',
};
const TTL = 900;

const SECTIONS = {
  newest_drops: 'Newest Drops',
  most_watched_shows: 'Most-Watched Shows',
  new_arrivals: 'New Anime Arrivals',
  most_watched_films: 'Most-Watched Films',
  latest_movies: 'Latest Anime Movies',
};

async function fetchHtml(url) {
  const res = await fetch(url, { headers: HEADERS, redirect: 'follow' });
  if (!res.ok) throw new Error('HTTP ' + res.status + ' for ' + url);
  return res.text();
}

function absSrc(img) {
  if (!img) return null;
  const src = img.getAttribute('src') || '';
  if (!src) return null;
  return src.replace('//', 'https://');
}

function slugFromHref(href) {
  return (href || '').replace(/\/+$/, '').split('/').pop() || '';
}

function parseSection(document, sectionTitle) {
  const wanted = sectionTitle.toLowerCase();
  const results = [];
  const matches = (el, sel) => {
    const h = el.querySelector(sel);
    return !!(h && (h.textContent || '').toLowerCase().includes(wanted));
  };

  for (const section of document.querySelectorAll('section.widget_list_episodes, section.widget_list_movies_series')) {
    if (!matches(section, 'h3.section-title')) continue;
    for (const slide of section.querySelectorAll('.swiper-slide')) {
      const article = slide.querySelector('article');
      if (!article) continue;
      const link = article.querySelector('a.lnk-blk');
      const title = article.querySelector('h2.entry-title');
      if (!link || !title) continue;
      const href = link.getAttribute('href') || '';
      results.push({
        title: title.textContent.trim(),
        slug: slugFromHref(href),
        poster: absSrc(article.querySelector('img')),
        type: href.includes('/movies/') ? 'movie' : 'series',
      });
    }
  }

  for (const section of document.querySelectorAll('section.widget_top')) {
    if (!matches(section, 'h3.widget-title')) continue;
    for (const item of section.querySelectorAll('.top-picks__item')) {
      const link = item.querySelector('a.lnk-blk');
      const img = item.querySelector('img');
      if (!link || !img) continue;
      const href = link.getAttribute('href') || '';
      results.push({
        title: (img.getAttribute('alt') || '').replace('Image ', '').trim(),
        slug: slugFromHref(href),
        poster: absSrc(img),
        type: href.includes('/movies/') ? 'movie' : 'series',
      });
    }
  }
  return results;
}

function episodesFromHtml(document) {
  const episodes = [];
  for (const li of document.querySelectorAll('#episode_by_temp li, li')) {
    const article = li.querySelector('article.episodes');
    if (!article) continue;
    const link = article.querySelector('a.lnk-blk');
    const num = article.querySelector('span.num-epi');
    const title = article.querySelector('h2.entry-title');
    if (!link || !num) continue;
    const m = (num.textContent || '').trim().match(/^(\d+)x(\d+)/);
    if (!m) continue;
    const href = link.getAttribute('href') || '';
    const ep = {
      season: parseInt(m[1], 10),
      episode: parseInt(m[2], 10),
      title: title ? title.textContent.trim() : ('Episode ' + m[2]),
      url: href,
    };
    const img = article.querySelector('img');
    if (img) {
      let th = img.getAttribute('src') || '';
      if (th) {
        if (th.startsWith('//')) th = 'https:' + th;
        else if (!th.startsWith('http')) th = 'https://' + th;
        ep.thumbnail = th;
      }
    }
    episodes.push(ep);
  }
  return episodes;
}

async function getDetails(slug) {
  for (const ct of ['series', 'movies']) {
    const url = BASE + '/' + ct + '/' + slug;
    let html;
    try {
      html = await fetchHtml(url);
    } catch (e) {
      continue;
    }
    const { document } = parseHTML(html);
    const title = document.querySelector('.entry-title') || document.querySelector('h1.entry-title');
    const desc = document.querySelector('.description p');
    const poster = document.querySelector('article.post img');
    const genres = [...document.querySelectorAll('.genres a')].map((g) => g.textContent.trim());
    const yearEl = document.querySelector('.year .overviewCss');
    const durEl = document.querySelector('.duration .overviewCss');

    let episodes = [];
    if (ct === 'series') {
      episodes = episodesFromHtml(document);
      const seasonLinks = [...document.querySelectorAll('.choose-season .sel-temp a')];
      if (seasonLinks.length > 1) {
        const postId = seasonLinks[0].getAttribute('data-post');
        const nS = document.querySelector('.n_s');
        const currentSeason = nS ? parseInt(nS.textContent.trim(), 10) : 1;
        if (postId) {
          for (const link of seasonLinks) {
            const sn = parseInt(link.getAttribute('data-season') || '0', 10);
            if (sn !== currentSeason) {
              try {
                const ajax = await fetchHtml(
                  BASE + '/wp-admin/admin-ajax.php?action=action_select_season&season=' + sn + '&post=' + encodeURIComponent(postId)
                );
                const parsed = parseHTML(ajax);
                episodes.push(...episodesFromHtml(parsed.document));
              } catch (e) {
                // ignore a failed season
              }
            }
          }
        }
      }
      episodes.sort((a, b) => a.season - b.season || a.episode - b.episode);
    } else {
      episodes.push({ season: 1, episode: 1, title: title ? title.textContent.trim() : 'Movie', url });
    }

    return {
      title: title ? title.textContent.trim() : null,
      slug,
      description: desc ? desc.textContent.trim() : null,
      poster: poster ? (poster.getAttribute('src') || '').replace('//', 'https://') : null,
      genres,
      year: yearEl ? yearEl.textContent.trim() : null,
      runtime: durEl ? durEl.textContent.trim() : null,
      episodes,
      type: ct === 'movies' ? 'movie' : 'series',
    };
  }
  return null;
}

async function searchAnime(query) {
  // 1) live-search AJAX (the server-rendered ?s= page is often empty)
  let homeHtml;
  try {
    homeHtml = await fetchHtml(BASE + '/');
  } catch (e) {
    homeHtml = '';
  }
  if (homeHtml) {
    const nonceMatch = homeHtml.match(/"nonce":"([a-f0-9]+)"/);
    if (nonceMatch) {
      try {
        const res = await fetch(BASE + '/wp-admin/admin-ajax.php', {
          method: 'POST',
          headers: {
            ...HEADERS,
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-Requested-With': 'XMLHttpRequest',
          },
          body: new URLSearchParams({ action: 'action_tr_search_suggest', nonce: nonceMatch[1], term: query }).toString(),
        });
        if (res.ok) {
          const text = await res.text();
          const results = [];
          const re = /<a href="([^"]+)\/(?:series|movies)\/([^"]+)\/"><span[^>]*>([^<]+)<\/span>([^<]+)</g;
          let m;
          while ((m = re.exec(text)) !== null) {
            results.push({
              title: m[4].trim(),
              slug: m[2],
              poster: null,
              type: m[3] === 'movies' ? 'movie' : 'series',
            });
          }
          if (results.length) return results;
        }
      } catch (e) {
        // fall through
      }
    }
  }

  // 2) server-rendered search page
  try {
    const html = await fetchHtml(BASE + '/?s=' + encodeURIComponent(query));
    const { document } = parseHTML(html);
    const results = [];
    const section = document.querySelector('#aa-movies');
    if (section) {
      for (const li of section.querySelectorAll('ul.post-lst > li')) {
        const article = li.querySelector('article');
        if (!article) continue;
        const link = article.querySelector('a.lnk-blk');
        const title = article.querySelector('h2.entry-title');
        if (!link || !title) continue;
        const href = link.getAttribute('href') || '';
        results.push({
          title: title.textContent.trim(),
          slug: slugFromHref(href),
          poster: absSrc(article.querySelector('img')),
          type: href.includes('/movies/') ? 'movie' : 'series',
        });
      }
    }
    return results;
  } catch (e) {
    return [];
  }
}

async function getStreams(slug, season, episode) {
  const url = season != null && episode != null
    ? BASE + '/episode/' + slug + '-' + season + 'x' + episode + '/'
    : BASE + '/movies/' + slug;
  const html = await fetchHtml(url);
  const { document } = parseHTML(html);
  const streams = [];
  for (const iframe of document.querySelectorAll('iframe')) {
    const src = iframe.getAttribute('src') || iframe.getAttribute('data-src') || '';
    if (src.toLowerCase().includes('zephyr')) {
      streams.push({ player: 'zephyrflick', url: src.startsWith('http') ? src : new URL(src, BASE).href });
    }
  }
  return { streams };
}

// --- Phase 2: TMDB mapping (port of app/mapper.py) ---

async function searchAnimeHtml(query) {
  const html = await fetchHtml(BASE + '/?s=' + encodeURIComponent(query));
  const { document } = parseHTML(html);
  const results = [];
  const section = document.querySelector('#aa-movies');
  if (section) {
    for (const li of section.querySelectorAll('ul.post-lst > li')) {
      const article = li.querySelector('article');
      if (!article) continue;
      const link = article.querySelector('a.lnk-blk');
      const title = article.querySelector('h2.entry-title');
      if (!link || !title) continue;
      const href = link.getAttribute('href') || '';
      results.push({
        title: title.textContent.trim(),
        slug: slugFromHref(href),
        poster: absSrc(article.querySelector('img')),
        type: href.includes('/movies/') ? 'movie' : 'series',
      });
    }
  }
  return results;
}

async function tmdbFind(imdbId, apiKey) {
  const r = await fetch('https://api.themoviedb.org/3/find/' + encodeURIComponent(imdbId) + '?api_key=' + encodeURIComponent(apiKey) + '&external_source=imdb_id');
  if (!r.ok) return null;
  const d = await r.json();
  if (d.movie_results && d.movie_results.length) return { ...d.movie_results[0], media_type: 'movie' };
  if (d.tv_results && d.tv_results.length) return { ...d.tv_results[0], media_type: 'series' };
  return null;
}

async function tmdbImages(tmdbId, mediaType, apiKey) {
  const mt = mediaType === 'series' ? 'tv' : 'movie';
  const r = await fetch('https://api.themoviedb.org/3/' + mt + '/' + encodeURIComponent(tmdbId) + '/images?api_key=' + encodeURIComponent(apiKey));
  if (!r.ok) return [];
  const d = await r.json();
  return (d.posters || []).map((p) => p.file_path).filter(Boolean);
}

function matchAnyPoster(paths, results) {
  for (const p of paths) {
    if (!p) continue;
    for (const res of results) {
      if ((res.poster || '').includes(p)) return res;
    }
  }
  return null;
}

async function getOrCreateSlugMapping(imdbId, env) {
  // 1) known mapping (works even without a TMDB key)
  const row = await env.DB.prepare('SELECT slug FROM mappings WHERE imdb_id = ?').bind(imdbId).first();
  if (row && row.slug) return { imdb_id: imdbId, slug: row.slug, cached: true };

  // 2) known failure
  const failed = await env.DB.prepare('SELECT 1 AS x FROM failed_mappings WHERE imdb_id = ?').bind(imdbId).first();
  if (failed) return { imdb_id: imdbId, error: 'failed_cached' };

  const apiKey = env.TMDB_API_KEY;
  if (!apiKey) return { error: 'no_tmdb_key' };

  // 3) TMDB details
  const details = await tmdbFind(imdbId, apiKey);
  if (!details) {
    await env.DB.prepare('INSERT OR REPLACE INTO failed_mappings (imdb_id, created_at) VALUES (?, ?)').bind(imdbId, Date.now()).run();
    return { imdb_id: imdbId, error: 'no_tmdb' };
  }
  const title = details.title || details.name;
  if (!title) {
    await env.DB.prepare('INSERT OR REPLACE INTO failed_mappings (imdb_id, created_at) VALUES (?, ?)').bind(imdbId, Date.now()).run();
    return { imdb_id: imdbId, error: 'no_title' };
  }

  // 4) site search (posters required for matching)
  const results = await searchAnimeHtml(title);
  if (!results.length) {
    await env.DB.prepare('INSERT OR REPLACE INTO failed_mappings (imdb_id, created_at) VALUES (?, ?)').bind(imdbId, Date.now()).run();
    return { imdb_id: imdbId, error: 'no_site_results', title };
  }

  // 5) match by poster (main poster first, then all TMDB posters)
  let matched = matchAnyPoster([details.poster_path], results);
  if (!matched) {
    const images = await tmdbImages(String(details.id), details.media_type, apiKey);
    matched = matchAnyPoster(images, results);
  }
  if (!matched || !matched.slug) {
    await env.DB.prepare('INSERT OR REPLACE INTO failed_mappings (imdb_id, created_at) VALUES (?, ?)').bind(imdbId, Date.now()).run();
    return { imdb_id: imdbId, error: 'no_poster_match', title };
  }

  const tmdbId = String(details.id);
  await env.DB.batch([
    env.DB.prepare('INSERT OR REPLACE INTO mappings (imdb_id, tmdb_id, slug, content_type, created_at) VALUES (?, ?, ?, ?, ?)')
      .bind(imdbId, tmdbId, matched.slug, details.media_type, Date.now()),
    env.DB.prepare('INSERT OR REPLACE INTO slug_imdb (slug, tmdb_id, imdb_id, content_type, created_at) VALUES (?, ?, ?, ?, ?)')
      .bind(matched.slug, tmdbId, imdbId, details.media_type, Date.now()),
  ]);

  return { imdb_id: imdbId, slug: matched.slug, tmdb_id: tmdbId, title, cached: false };
}

// --- Phase 3: slug -> IMDb (for catalogs) + player resolution + Stremio routes ---

async function tmdbSearch(title, contentType, posterUrl, year, apiKey) {
  const mediaType = contentType === 'series' ? 'tv' : 'movie';
  const queries = [title];
  // Retry with the trailing qualifier stripped, e.g. "Doraemon (2005)" -> "Doraemon"
  const cleaned = title.replace(/\s*\([^)]*\)\s*$/, '').replace(/\s*\[[^\]]*\]\s*$/, '').trim();
  if (cleaned && cleaned !== title) queries.push(cleaned);

  for (const q of queries) {
    let url = 'https://api.themoviedb.org/3/search/' + mediaType +
      '?api_key=' + encodeURIComponent(apiKey) + '&query=' + encodeURIComponent(q);
    if (year) url += '&' + (mediaType === 'movie' ? 'year' : 'first_air_date_year') + '=' + encodeURIComponent(year);
    const r = await fetch(url);
    if (!r.ok) continue;
    const d = await r.json();
    const results = d.results || [];
    if (!results.length) continue;
    if (results.length === 1) return results[0];
    if (posterUrl) {
      for (const res of results) if (res.poster_path && posterUrl.includes(res.poster_path)) return res;
      for (const res of results) {
        const images = await tmdbImages(String(res.id), contentType, apiKey);
        for (const p of images) if (posterUrl.includes(p)) return res;
      }
    }
    return results[0];
  }
  return null;
}

async function tmdbExternalId(tmdbId, contentType, apiKey) {
  const mediaType = contentType === 'series' ? 'tv' : 'movie';
  const r = await fetch('https://api.themoviedb.org/3/' + mediaType + '/' + encodeURIComponent(tmdbId) +
    '/external_ids?api_key=' + encodeURIComponent(apiKey));
  if (!r.ok) return null;
  const d = await r.json();
  return d.imdb_id || null;
}

async function getOrCreateImdbMapping(slug, title, contentType, posterUrl, env) {
  const row = await env.DB.prepare('SELECT imdb_id FROM slug_imdb WHERE slug = ?').bind(slug).first();
  if (row && row.imdb_id) return row.imdb_id;
  const apiKey = env.TMDB_API_KEY;
  if (!apiKey) return null;
  const res = await tmdbSearch(title, contentType, posterUrl, null, apiKey);
  if (!res) return null;
  const tmdbId = String(res.id);
  const imdbId = await tmdbExternalId(tmdbId, contentType, apiKey);
  if (!imdbId) return null;
  await env.DB.batch([
    env.DB.prepare('INSERT OR REPLACE INTO slug_imdb (slug, tmdb_id, imdb_id, content_type, created_at) VALUES (?, ?, ?, ?, ?)')
      .bind(slug, tmdbId, imdbId, contentType, Date.now()),
    env.DB.prepare('INSERT OR REPLACE INTO mappings (imdb_id, tmdb_id, slug, content_type, created_at) VALUES (?, ?, ?, ?, ?)')
      .bind(imdbId, tmdbId, slug, contentType, Date.now()),
  ]);
  return imdbId;
}

async function mapCatalog(items, env) {
  const mapped = await Promise.all(items.map(async (item) => {
    const imdb = await getOrCreateImdbMapping(item.slug, item.title, item.type || 'series', item.poster, env);
    return imdb ? { id: imdb, name: item.title, type: item.type || 'series', poster: item.poster } : null;
  }));
  return mapped.filter(Boolean);
}

async function getHomeSections() {
  const cache = caches.default;
  const key = new Request('https://nuvio.gramnaters.workers.dev/__sections?cv=7');
  const hit = await cache.match(key);
  if (hit) return hit.json();
  const html = await fetchHtml(BASE + '/');
  const { document } = parseHTML(html);
  const out = {};
  for (const [k, title] of Object.entries(SECTIONS)) out[k] = parseSection(document, title);
  const res = new Response(JSON.stringify(out), {
    headers: { 'Content-Type': 'application/json', 'Cache-Control': 'public, max-age=900' },
  });
  await cache.put(key, res.clone());
  return out;
}

function b64urlEncode(s) {
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function b64urlDecode(s) {
  const p = s.replace(/-/g, '+').replace(/_/g, '/');
  const pad = p.length % 4 ? '='.repeat(4 - (p.length % 4)) : '';
  return atob(p + pad);
}

async function getVideoSource(playerUrl) {
  const m = playerUrl.match(/\/video\/([a-f0-9]+)/);
  if (!m) return null;
  const r = await fetch('https://play.zephyrix.org/player/index.php?data=' + m[1] + '&do=getVideo', {
    method: 'POST',
    headers: { 'User-Agent': UA, 'X-Requested-With': 'XMLHttpRequest', 'Referer': playerUrl },
  });
  if (!r.ok) return null;
  try {
    const d = await r.json();
    return d.videoSource || null;
  } catch (e) {
    return null;
  }
}

const PLAYER_REFERER = 'https://play.zephyrix.org/';
const HLS_BASE = 'https://anw.gramnaters.workers.dev';

const MANIFEST = {
  id: 'com.skoruppa.watchanimeworld-stremio-addon',
  version: '0.3.0',
  name: 'Anime World India Addon',
  logo: 'https://nuvio.gramnaters.workers.dev/static/logo.png',
  description: 'Watch anime in Hindi, Tamil, Telugu & English from WatchAnimeWorld.top',
  types: ['anime', 'series', 'movie'],
  idPrefixes: ['tt'],
  catalogs: [
    { type: 'anime', id: 'newest_drops', name: 'Newest Drops' },
    { type: 'anime', id: 'most_watched_shows', name: 'Most-Watched Shows' },
    { type: 'anime', id: 'new_arrivals', name: 'New Anime Arrivals' },
    { type: 'anime', id: 'most_watched_films', name: 'Most-Watched Films' },
    { type: 'anime', id: 'latest_movies', name: 'Latest Anime Movies' },
    { type: 'anime', id: 'search', name: 'Search', extra: [{ name: 'search', isRequired: true }] },
  ],
  behaviorHints: { configurable: true, configurationRequired: false },
  resources: ['catalog', 'meta', 'stream'],
  stremioAddonsConfig: {
    issuer: 'https://stremio-addons.net',
    signature: 'eyJhbGciOiJkaXIiLCJlbmMiOiJBMTI4Q0JDLUhTMjU2In0..7gV3q1MNizIqKIMz8e4qvw.DSKuF6iQaPJp9VOPWuafWVaMhN6a32S8fGxUXYcNqS7yaqP48Ys2__2p5On7XU14e6IOE5qy56xaZCqDi61J-hEThy76L6YtS0F6tyc140pdd65-7Mw_uiXin2gq9NV4.hjecT9eBaBcBrEy5MdVnCQ',
  },
};

const LANGS = ['hin', 'tam', 'tel', 'jpn', 'eng'];

function json(data, status = 200, maxAge = 300, swr = 0) {
  let cc = 'public, max-age=' + maxAge;
  if (swr) cc += ', stale-while-revalidate=' + swr;
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', 'Cache-Control': cc, 'Access-Control-Allow-Origin': '*' },
  });
}

// --- AnimeSalt provider (ravok.buzz player) ---
const AS_BASE = 'https://animesalt.cx';
const RAVOK = 'https://ravok.buzz';
const RAVOK_REF = 'https://ravok.buzz/';

function normTitle(s) {
  return (s || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}

async function asSearch(title) {
  const queries = [];
  const add = (t) => {
    t = (t || '').replace(/\s+/g, ' ').trim();
    if (t && !queries.includes(t)) queries.push(t);
  };
  add(title);
  add(title.replace(/[^\p{L}\p{N}\s]/gu, ' '));
  add(title.split(/[:–—]/)[0]);

  let first = [];
  for (const q of queries) {
    let out = [];
    try {
      const html = await fetchHtml(AS_BASE + '/?s=' + encodeURIComponent(q));
      const { document } = parseHTML(html);
      const section = document.querySelector('#aa-movies');
      if (section) {
        for (const li of section.querySelectorAll('ul.post-lst > li')) {
          const a = li.querySelector('article');
          if (!a) continue;
          const link = a.querySelector('a.lnk-blk');
          const t = a.querySelector('h2.entry-title');
          if (!link || !t) continue;
          const href = link.getAttribute('href') || '';
          out.push({
            title: t.textContent.trim(),
            slug: href.replace(/\/+$/, '').split('/').pop(),
            type: href.includes('/movies/') ? 'movie' : 'series',
          });
        }
      }
    } catch (e) {
      out = [];
    }
    if (!first.length) first = out;
    if (out.length) return out;
  }
  return first;
}

function pickAsResult(results, title, wantType) {
  if (!results.length) return null;
  const wantTokens = new Set(normTitle(title).split(' ').filter(Boolean));
  const want = normTitle(title);
  let best = null;
  let bestScore = -1;
  for (const r of results) {
    const cand = new Set(normTitle(r.title).split(' ').filter(Boolean));
    let overlap = 0;
    for (const t of wantTokens) if (cand.has(t)) overlap++;
    let score = overlap / Math.max(wantTokens.size, cand.size, 1);
    if (normTitle(r.title) === want) score += 1;
    if (wantType && r.type === wantType) score += 0.3;
    if (score > bestScore) {
      bestScore = score;
      best = r;
    }
  }
  return best;
}

async function asRavokId(pageUrl) {
  const html = await fetchHtml(pageUrl);
  const { document } = parseHTML(html);
  for (const iframe of document.querySelectorAll('iframe')) {
    const src = iframe.getAttribute('src') || iframe.getAttribute('data-src') || '';
    if (src.includes('ravok.buzz/video/')) {
      const m = src.match(/\/video\/([a-f0-9]+)/);
      if (m) return { id: m[1], src };
    }
  }
  return null;
}

async function asMaster(ravokId, src) {
  for (let attempt = 0; attempt < 4; attempt++) {
    try {
      const r = await fetch(RAVOK + '/player/index.php?data=' + ravokId + '&do=getVideo', {
        method: 'POST',
        headers: { 'User-Agent': UA, 'X-Requested-With': 'XMLHttpRequest', Referer: src || (RAVOK + '/video/' + ravokId) },
      });
      if (r.ok) {
        const text = await r.text();
        if (text.trim().startsWith('{')) {
          const d = JSON.parse(text);
          if (d.videoSource) return d.videoSource;
        }
      }
    } catch (e) {
      // retry
    }
    if (attempt < 3) await new Promise((res) => setTimeout(res, 300));
  }
  return null;
}

async function asResolve(imdb, title, env, wantType) {
  const row = await asMapRow(imdb, env, wantType);
  if (row) return row;
  const results = await asSearch(title);
  if (!results.length) return null;
  const best = pickAsResult(results, title, wantType);
  if (!best) return null;
  await asSaveMap(imdb, best.slug, best.type, env);
  return { slug: best.slug, type: best.type };
}

function asPageUrl(slug, type, season, episode) {
  if (type === 'movie') return AS_BASE + '/movies/' + slug + '/';
  if (season != null && episode != null) return AS_BASE + '/episode/' + slug + '-' + season + 'x' + episode + '/';
  return AS_BASE + '/series/' + slug + '/';
}

async function asMapRow(imdb, env, wantType) {
  try {
    const row = await env.DB.prepare('SELECT slug, type FROM as_map WHERE imdb_id = ?').bind(imdb).first();
    if (!row || !row.slug) return null;
    if (wantType && row.type && row.type !== wantType) return null;
    return { slug: row.slug, type: row.type || wantType };
  } catch (e) {
    return null;
  }
}

async function asSaveMap(imdb, slug, type, env) {
  try {
    await env.DB.prepare('INSERT OR REPLACE INTO as_map (imdb_id, slug, type, title, created_at) VALUES (?, ?, ?, ?, ?)')
      .bind(imdb, slug, type, '', Date.now()).run();
  } catch (e) {
    // best effort
  }
}

// Episode list for an AnimeSalt series, cached for an hour. Shared by /meta
// (to build the episode list) and /stream (to decide whether AnimeSalt is
// worth querying for this episode at all).
async function asSeriesEpisodes(slug) {
  const cache = caches.default;
  const key = new Request('https://nuvio.gramnaters.workers.dev/__aseps?slug=' + encodeURIComponent(slug) + '&cv=1');
  const hit = await cache.match(key);
  if (hit) {
    try {
      const d = await hit.json();
      if (Array.isArray(d.eps)) return d.eps;
    } catch (e) {
      // fall through to a fresh scrape
    }
  }
  const html = await fetchHtml(AS_BASE + '/series/' + slug + '/');
  const { document } = parseHTML(html);
  const out = [];
  for (const a of document.querySelectorAll('article.episodes a.lnk-blk')) {
    const href = a.getAttribute('href') || '';
    const m = href.match(/-(\d+)x(\d+)\/?$/);
    if (!m) continue;
    const season = parseInt(m[1], 10);
    const episode = parseInt(m[2], 10);
    if (out.some((x) => x[0] === season && x[1] === episode)) continue;
    out.push([season, episode]);
  }
  out.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  await cache.put(key, json({ eps: out }, 200, 3600));
  return out;
}

async function asEpisodeList(imdb, primarySlug, env) {
  let asSlug = null;
  const row = await asMapRow(imdb, env, 'series');
  if (row) asSlug = row.slug;

  if (asSlug) {
    try {
      const eps = await asSeriesEpisodes(asSlug);
      if (eps.length) return eps.map(([season, episode]) => ({ season, episode }));
    } catch (e) {
      // fall through
    }
  }

  // Same CMS family: the slug is usually identical on both sites.
  if (primarySlug && primarySlug !== asSlug) {
    try {
      const eps = await asSeriesEpisodes(primarySlug);
      if (eps.length) {
        await asSaveMap(imdb, primarySlug, 'series', env);
        return eps.map(([season, episode]) => ({ season, episode }));
      }
    } catch (e) {
      // fall through
    }
  }

  const apiKey = env.TMDB_API_KEY;
  if (!apiKey) return [];
  const details = await tmdbFind(imdb, apiKey);
  if (!details) return [];
  const title = details.title || details.name;
  if (!title) return [];
  const results = await asSearch(title);
  const best = pickAsResult(results, title, 'series');
  if (!best || best.type !== 'series') return [];
  try {
    const eps = await asSeriesEpisodes(best.slug);
    if (eps.length) await asSaveMap(imdb, best.slug, 'series', env);
    return eps.map(([season, episode]) => ({ season, episode }));
  } catch (e) {
    return [];
  }
}

// ---------- stream providers ----------
// Each provider resolves independently and returns raw entries:
//   { player, url, referer }
// Callers label them and run them in parallel (see /stream).

const PROVIDERS = {
  animeworld: { key: 'animeworld', label: 'ANIME WORLD', site: 'watchanimeworld', timeout: 9000 },
  animesalt: { key: 'animesalt', label: 'ANIME SALT', site: 'animesalt', timeout: 20000 },
};

async function provWatchAnimeWorld(slug, season, episode) {
  const data = await getStreams(slug, season, episode);
  const out = [];
  for (const s of data.streams || []) {
    if (s.player !== 'zephyrflick') continue;
    const videoSource = await getVideoSource(s.url);
    if (!videoSource) continue;
    out.push({
      player: 'zephyrflick',
      url: HLS_BASE + '/hls/' + b64urlEncode(videoSource) + '.m3u8',
      referer: PLAYER_REFERER,
    });
  }
  return out;
}

async function provAnimeSalt(imdb, season, episode, env, origin, primarySlug) {
  const wantType = (season != null && episode != null) ? 'series' : 'movie';

  const candidates = [];
  const row = await asMapRow(imdb, env, wantType);
  if (row) candidates.push(row);
  if (primarySlug && !candidates.some((c) => c.slug === primarySlug)) {
    candidates.push({ slug: primarySlug, type: wantType });
  }

  let ravok = null;
  let used = null;
  for (const cand of candidates) {
    try {
      ravok = await asRavokId(asPageUrl(cand.slug, cand.type, season, episode));
    } catch (e) {
      ravok = null;
    }
    if (ravok) {
      used = cand;
      break;
    }
  }

  // Last resort: site search by title.
  if (!ravok) {
    const apiKey = env.TMDB_API_KEY;
    if (!apiKey) return [];
    const details = await tmdbFind(imdb, apiKey);
    const title = details && (details.title || details.name);
    if (!title) return [];
    const results = await asSearch(title);
    const best = pickAsResult(results, title, wantType);
    if (best) {
      try {
        ravok = await asRavokId(asPageUrl(best.slug, best.type, season, episode));
      } catch (e) {
        ravok = null;
      }
      if (ravok) used = best;
    }
  }
  if (!ravok) return [];

  if (used && (!row || row.slug !== used.slug)) await asSaveMap(imdb, used.slug, used.type, env);

  const master = await asMaster(ravok.id, ravok.src);
  if (!master) return [];

  return [{ player: 'ravok', url: origin + '/as/hls/' + b64urlEncode(master), referer: null }];
}

// Cheap pre-check: does AnimeSalt even list this episode? Avoids paying for a
// doomed scrape on the ~2.5k episodes only the primary site carries.
async function asCanServe(imdb, season, episode, env) {
  let row = null;
  try {
    row = await env.DB.prepare('SELECT slug, type FROM as_map WHERE imdb_id = ?').bind(imdb).first();
  } catch (e) {
    return true;
  }
  if (!row || !row.slug) return true;
  if (row.type === 'movie' || season == null || episode == null) return true;
  try {
    const eps = await asSeriesEpisodes(row.slug);
    if (!eps.length) return true;
    return eps.some((x) => x[0] === season && x[1] === episode);
  } catch (e) {
    return true;
  }
}

function withTimeout(promise, ms) {
  return Promise.race([
    promise,
    new Promise((_, reject) => setTimeout(() => reject(new Error('timeout after ' + ms + 'ms')), ms)),
  ]);
}

function labelStreams(provider, entries, ctx) {
  return entries.map((e, i) => {
    const hint = {
      bingeGroup: provider.key + '|' + e.player,
      notWebReady: true,
    };
    if (ctx.filename) hint.filename = ctx.filename + '.' + provider.key + '.mkv';
    if (e.referer) hint.proxyHeaders = { request: { Referer: e.referer, 'User-Agent': UA } };
    const desc = entries.length > 1
      ? provider.site + ' #' + (i + 1) + '\n' + e.player
      : provider.site + '\n' + e.player;
    return { name: provider.label, description: desc, url: e.url, behaviorHints: hint };
  });
}

async function warmCatalogs(env) {
  const sections = await getHomeSections();
  for (const id of Object.keys(SECTIONS)) {
    const items = sections[id] || [];
    const metas = await mapCatalog(items, env);
    const key = new Request('https://nuvio.gramnaters.workers.dev/catalog/anime/' + id + '.json?cv=7');
    await caches.default.put(key, json({ metas }, 200, 3600));
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const cache = caches.default;
    let p = url.pathname;

    // strip an optional /<lang>/ prefix (hin|tam|tel|jpn|eng)
    const segs = p.split('/');
    if (segs.length > 1 && LANGS.includes(segs[1])) {
      p = '/' + segs.slice(2).join('/');
    }

    if (p === '/health') return new Response('nuvio addon ok', { status: 200 });

    // ---------- config page ----------
    if (p === '/' || p === '/configure') {
      const html = PAGE_HTML.split('__HOST__').join(url.host);
      return new Response(html, {
        headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'public, max-age=300' },
      });
    }
    if (p === '/static/css/style.css') {
      return new Response(PAGE_CSS, {
        headers: { 'Content-Type': 'text/css; charset=utf-8', 'Cache-Control': 'public, max-age=3600' },
      });
    }
    if (p === '/static/js/index.js') {
      return new Response(PAGE_JS, {
        headers: { 'Content-Type': 'application/javascript; charset=utf-8', 'Cache-Control': 'public, max-age=3600' },
      });
    }

    if (p === '/static/logo.png' || p === '/logo.png' || p === '/favicon.ico') {
      const bin = Uint8Array.from(atob(LOGO_B64), (c) => c.charCodeAt(0));
      return new Response(bin, {
        headers: { 'Content-Type': 'image/png', 'Cache-Control': 'public, max-age=31536000, immutable' },
      });
    }

    try {
      // ---------- Stremio: manifest ----------
      if (p === '/manifest.json') {
        const value = (url.searchParams.get('catalogs') || '1').trim().toLowerCase();
        const manifest = { ...MANIFEST, logo: url.origin + '/static/logo.png' };
        if (['0', 'false', 'off', 'no'].includes(value)) {
          manifest.catalogs = [];
          manifest.resources = ['meta', 'stream'];
        }
        return json(manifest, 200, 7200);
      }

      // ---------- Stremio: catalog ----------
      let m = p.match(/^\/catalog\/([^/]+)\/([^/]+?)(?:\/search=(.+?))?\.json$/);
      if (m) {
        const catalogId = decodeURIComponent(m[2]);
        const searchTerm = m[3] ? decodeURIComponent(m[3]) : '';
        const key = new Request(url.toString() + '?cv=7');
        const hit = await cache.match(key);
        if (hit) return hit;
        let items;
        try {
          if (catalogId === 'search') {
            items = await searchAnimeHtml(searchTerm);
          } else {
            const sections = await getHomeSections();
            items = sections[catalogId] || [];
          }
        } catch (e) {
          return json({ metas: [] }, 200, 60);
        }
        let metas = [];
        try {
          metas = await mapCatalog(items, env);
        } catch (e) {
          metas = [];
        }
        const res = json({ metas }, 200, 3600);
        await cache.put(key, res.clone());
        return res;
      }

      // ---------- Stremio: meta ----------
      m = p.match(/^\/meta\/([^/]+)\/(.+)\.json$/);
      if (m) {
        const metaType = m[1];
        const imdb = decodeURIComponent(m[2]);
        if (!imdb.startsWith('tt')) return json({ meta: {} });
        const key = new Request(url.toString() + '?cv=7');
        const hit = await cache.match(key);
        if (hit) return hit;
        const mapping = await getOrCreateSlugMapping(imdb, env);
        if (!mapping || !mapping.slug) return json({ meta: {} });
        const details = await getDetails(mapping.slug);
        if (!details) return json({ meta: {} });
        const meta = {
          id: imdb,
          type: metaType,
          name: details.title,
          description: details.description,
          poster: details.poster,
          genres: details.genres || [],
          releaseInfo: details.year,
          runtime: details.runtime,
        };
        if (details.type === 'series') {
          let eps = (details.episodes || []).slice();
          // Episode list = primary list, topped up from AnimeSalt when it
          // carries more episodes (weekly shows the primary hasn't caught up
          // with, or titles the primary lists as empty). Only top up when the
          // AnimeSalt list is the longer one: its episodes are always numbered
          // from season 1, so merging a shorter list would invent episodes.
          try {
            const asEps = await asEpisodeList(imdb, mapping.slug, env);
            if (asEps.length >= eps.length) {
              for (const e of asEps) {
                if (!eps.some((x) => x.season === e.season && x.episode === e.episode)) {
                  eps.push({ season: e.season, episode: e.episode });
                }
              }
            }
          } catch (e) {
            // keep the primary list
          }
          eps.sort((a, b) => (a.season || 0) - (b.season || 0) || (a.episode || 0) - (b.episode || 0));
          meta.videos = eps.map((ep) => ({
            id: imdb + ':' + ep.season + ':' + ep.episode,
            title: ep.title || ('Episode ' + ep.episode),
            episode: ep.episode,
            season: ep.season,
            thumbnail: ep.thumbnail,
          }));
        }
        const res = json({ meta }, 200, meta.name ? 86400 : 60);
        // Don't cache very large metas (hundreds of episodes) - the cache write
        // itself can blow the free-plan subrequest budget.
        if ((meta.videos || []).length <= 200) {
          await cache.put(key, res.clone());
        }
        return res;
      }

      // ---------- Stremio: stream ----------
      m = p.match(/^\/stream\/([^/]+)\/(.+)\.json$/);
      if (m) {
        const raw = decodeURIComponent(m[2]);
        const parts = raw.split(':');
        if (!parts[0] || !parts[0].startsWith('tt')) return json({ streams: [] });
        const imdb = parts[0];
        const season = parts.length === 3 ? parseInt(parts[1], 10) : null;
        const episode = parts.length === 3 ? parseInt(parts[2], 10) : null;

        const key = new Request(url.toString() + '?cv=7');
        const hit = await cache.match(key);
        if (hit) return hit;

        const mapping = await getOrCreateSlugMapping(imdb, env);
        const base = (mapping && mapping.slug) ? mapping.slug : imdb;
        const ctx = {
          filename: season != null && episode != null
            ? base + '.S' + String(season).padStart(2, '0') + 'E' + String(episode).padStart(2, '0')
            : base,
        };

        // Both providers resolve in parallel; each success becomes its own
        // labelled stream so the viewer picks the site.
        const primaryJob = (mapping && mapping.slug)
          ? withTimeout(provWatchAnimeWorld(mapping.slug, season, episode), PROVIDERS.animeworld.timeout)
          : Promise.resolve([]);
        const saltJob = (async () => {
          if (!(await asCanServe(imdb, season, episode, env))) return [];
          return withTimeout(provAnimeSalt(imdb, season, episode, env, url.origin, mapping && mapping.slug), PROVIDERS.animesalt.timeout);
        })();
        const [primaryRes, saltRes] = await Promise.allSettled([primaryJob, saltJob]);

        const streams = [];
        for (const [provider, res] of [[PROVIDERS.animeworld, primaryRes], [PROVIDERS.animesalt, saltRes]]) {
          if (res.status === 'fulfilled' && res.value.length) {
            streams.push(...labelStreams(provider, res.value, ctx));
          }
        }

        // Shorter cache when a provider failed, so a bad scrape doesn't stick.
        const anyFailed = primaryRes.status === 'rejected' || saltRes.status === 'rejected';
        const res = anyFailed
          ? json({ streams }, 200, 120, 300)
          : json({ streams }, 200, 900, 1800);
        await cache.put(key, res.clone());
        return res;
      }

      // ---------- debug endpoints (Phase 1/2) ----------
      if (p === '/home') return json(await getHomeSections());

      m = p.match(/^\/catalog\/([a-z_]+)$/);
      if (m) {
        const sections = await getHomeSections();
        return json(sections[m[1]] || []);
      }

      if (p === '/search') {
        return json(await searchAnime(url.searchParams.get('q') || ''));
      }

      m = p.match(/^\/meta\/(.+)$/);
      if (m) return json(await getDetails(decodeURIComponent(m[1])));

      if (p === '/streams') {
        const slug = url.searchParams.get('slug') || '';
        const season = url.searchParams.get('season');
        const episode = url.searchParams.get('episode');
        return json(await getStreams(slug, season != null ? parseInt(season, 10) : null, episode != null ? parseInt(episode, 10) : null));
      }

      if (p === '/map') {
        const imdb = url.searchParams.get('imdb') || '';
        if (!/^tt\d+$/.test(imdb)) return json({ error: 'bad imdb' }, 400);
        return json(await getOrCreateSlugMapping(imdb, env));
      }

      // ---------- AnimeSalt playlist proxy ----------
      let asMatch = p.match(/^\/as\/(hls|v)\/(.+)$/);
      if (asMatch) {
        let target;
        try {
          target = b64urlDecode(asMatch[2]);
        } catch (e) {
          return json({ error: 'bad token' }, 400);
        }
        if (!target.startsWith('https://ravok.buzz/')) return json({ error: 'bad target' }, 400);
        const key = new Request(url.toString());
        const hit = await cache.match(key);
        if (hit) return hit;
        const res = await fetch(target, { headers: { 'User-Agent': UA, Referer: RAVOK_REF } });
        if (!res.ok) return json({ error: 'upstream ' + res.status }, 502);
        let text = await res.text();
        text = text.replace(/URI="(\/hls\/[^"]+)"/g, (_, v) => 'URI="' + url.origin + '/as/v/' + b64urlEncode(RAVOK + v) + '"');
        text = text.replace(/^(\/hls\/\S+)$/gm, (_, v) => url.origin + '/as/v/' + b64urlEncode(RAVOK + v));
        const out = new Response(text, {
          headers: {
            'Content-Type': 'application/vnd.apple.mpegurl',
            'Cache-Control': 'public, max-age=600',
            'Access-Control-Allow-Origin': '*',
          },
        });
        await cache.put(key, out.clone());
        return out;
      }

      return json({ error: 'not found' }, 404);
    } catch (e) {
      return json({ error: String(e) }, 502);
    }
  },

  async scheduled(event, env, ctx) {
    ctx.waitUntil(warmCatalogs(env));
  },
};
