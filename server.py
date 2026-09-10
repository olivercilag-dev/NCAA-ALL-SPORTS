import json, os, threading, time, hashlib
from datetime import datetime, timezone, timedelta
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data.json'
META = ROOT / 'data_meta.json'
PORT = int(os.environ.get('PORT', '10000'))
REFRESH_MINUTES = max(5, int(os.environ.get('REFRESH_MINUTES', '15')))
LOOKAHEAD_DAYS = max(1, int(os.environ.get('LOOKAHEAD_DAYS', '7')))
USER_AGENT = 'NCAA-All-Sports/1.0 (public-data-cache; contact=site-owner)'

# Official NCAA public scoreboard JSON endpoints. No API key is used.
# Tennis is intentionally excluded per the project requirement.
NCAA_SOURCES = [
    ('football', 'fbs', 'Football', 'football'),
    ('basketball-men', 'd1', "Men's Basketball", 'basketball'),
    ('basketball-women', 'd1', "Women's Basketball", 'basketball'),
    ('baseball', 'd1', 'Baseball', 'baseball'),
    ('softball', 'd1', 'Softball', 'softball'),
    ('volleyball-women', 'd1', "Women's Volleyball", 'volleyball'),
    ('soccer-men', 'd1', "Men's Soccer", 'soccer'),
    ('soccer-women', 'd1', "Women's Soccer", 'soccer'),
    ('ice-hockey-men', 'd1', "Men's Ice Hockey", 'ice_hockey'),
    ('ice-hockey-women', 'd1', "Women's Ice Hockey", 'ice_hockey'),
    ('lacrosse-men', 'd1', "Men's Lacrosse", 'lacrosse'),
    ('lacrosse-women', 'd1', "Women's Lacrosse", 'lacrosse'),
    ('field-hockey', 'd1', 'Field Hockey', 'field_hockey'),
    ('wrestling', 'd1', 'Wrestling', 'wrestling'),
    ('gymnastics-women', 'd1', "Women's Gymnastics", 'gymnastics'),
    ('swimming-and-diving', 'd1', 'Swimming & Diving', 'swimming'),
    ('water-polo-men', 'd1', "Men's Water Polo", 'water_polo'),
    ('water-polo-women', 'd1', "Women's Water Polo", 'water_polo'),
    ('golf-men', 'd1', "Men's Golf", 'golf'),
    ('golf-women', 'd1', "Women's Golf", 'golf'),
    ('rowing-women', 'd1', "Women's Rowing", 'rowing'),
    ('fencing', 'd1', 'Fencing', 'fencing'),
    ('cross-country-men', 'd1', "Men's Cross Country", 'cross_country'),
    ('cross-country-women', 'd1', "Women's Cross Country", 'cross_country'),
    ('track-field-indoor-men', 'd1', "Men's Indoor Track & Field", 'track_field'),
    ('track-field-indoor-women', 'd1', "Women's Indoor Track & Field", 'track_field'),
    ('track-field-outdoor-men', 'd1', "Men's Outdoor Track & Field", 'track_field'),
    ('track-field-outdoor-women', 'd1', "Women's Outdoor Track & Field", 'track_field'),
]
BASE = 'https://data.ncaa.com/casablanca/scoreboard/{sport}/{division}/{date}/scoreboard.json'

_lock = threading.Lock()
_last_refresh = {'status': 'bundled', 'started_at': None, 'finished_at': None, 'events': 0, 'error': '', 'source': 'bundled snapshot'}


def read_data():
    try:
        obj = json.loads(DATA.read_text(encoding='utf-8'))
        return obj if isinstance(obj, list) else []
    except Exception:
        return []


def write_data(events, source='Official NCAA public scoreboard JSON'):
    tmp = DATA.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(events, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    tmp.replace(DATA)
    meta = {
        'updated_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'events': len(events),
        'source': source,
        'refresh_minutes': REFRESH_MINUTES,
    }
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')


def iso_from_value(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        # Handle seconds or milliseconds since epoch.
        if v > 10_000_000_000:
            v = v / 1000
        try:
            return datetime.fromtimestamp(v, tz=timezone.utc).isoformat().replace('+00:00', 'Z')
        except Exception:
            return None
    s = str(v).strip()
    if not s:
        return None
    if s.endswith('Z'):
        return s
    try:
        dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    except Exception:
        return None


def pick(d, *keys):
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ''):
            return d[k]
    return None


def team_info(x):
    if not isinstance(x, dict):
        return {'name': str(x or 'TBD')}
    return {
        'name': pick(x, 'name', 'teamName', 'displayName', 'shortName', 'nickname') or 'TBD',
        'logo': pick(x, 'logo', 'logoUrl', 'logoURL', 'image', 'imageUrl') or '',
        'rank': pick(x, 'rank', 'ranking'),
        'id': pick(x, 'id', 'teamId', 'teamID')
    }


def extract_games(obj):
    """Tolerant parser for NCAA scoreboard JSON variants."""
    found = []
    seen = set()

    def walk(node):
        if isinstance(node, dict):
            # Common shapes: {game:{...}}, {home:{...},away:{...}}, or teams under a game object.
            candidate = node.get('game') if isinstance(node.get('game'), dict) else node
            home = pick(candidate, 'home', 'homeTeam', 'home_team')
            away = pick(candidate, 'away', 'awayTeam', 'away_team')
            if home is not None and away is not None:
                sid = pick(candidate, 'gameID', 'gameId', 'id', 'contestId', 'contestID')
                key = str(sid or hashlib.sha1(json.dumps(candidate, sort_keys=True, default=str).encode()).hexdigest())
                if key not in seen:
                    seen.add(key)
                    found.append(candidate)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(obj)
    return found


def normalize_game(g, sport_name, endpoint, sport_key):
    home = team_info(pick(g, 'home', 'homeTeam', 'home_team'))
    away = team_info(pick(g, 'away', 'awayTeam', 'away_team'))
    start = pick(g, 'startDate', 'start_date', 'startTime', 'startTimeUtc', 'startUTC', 'scheduledStart', 'date')
    if isinstance(start, dict):
        start = pick(start, 'date', 'datetime', 'utc', 'value')
    start = iso_from_value(start)
    if not start:
        return None
    status = pick(g, 'status', 'gameStatus', 'statusText', 'state', 'description') or 'Scheduled'
    if isinstance(status, dict):
        status = pick(status, 'displayName', 'name', 'description', 'type') or 'Scheduled'
    scores = g.get('score') if isinstance(g.get('score'), dict) else {}
    hs = pick(g, 'homeScore', 'home_score')
    as_ = pick(g, 'awayScore', 'away_score')
    if hs is None: hs = pick(scores, 'home', 'homeScore')
    if as_ is None: as_ = pick(scores, 'away', 'awayScore')
    conference = pick(g, 'conference', 'conferenceName', 'league', 'association') or ''
    venue = pick(g, 'venue', 'venueName', 'location') or ''
    if isinstance(venue, dict): venue = pick(venue, 'name', 'displayName', 'fullName') or ''
    game_id = str(pick(g, 'gameID', 'gameId', 'id', 'contestId', 'contestID') or hashlib.sha1((home['name']+'|'+away['name']+'|'+start).encode()).hexdigest()[:24])
    raw = home['name'] + '|' + away['name'] + '|' + start + '|' + sport_name
    return {
        'id': hashlib.sha1(raw.encode()).hexdigest()[:24],
        'sport': sport_key,
        'start_utc': start,
        'home': home['name'], 'away': away['name'],
        'competition': 'NCAA ' + sport_name,
        'conference': conference,
        'venue': venue,
        'status': str(status),
        'source': 'NCAA',
        'source_url': endpoint,
        'confidence': 0.98,
        'updated_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'upstream_id': game_id,
        'links_json': '{}',
        'home_score': '' if hs is None else str(hs),
        'away_score': '' if as_ is None else str(as_),
        'home_rank': home['rank'], 'away_rank': away['rank'],
        'broadcasts_json': '[]', 'notes_json': '[]',
        'home_logo': home['logo'], 'away_logo': away['logo'],
        'color': '#18bfff'
    }


def fetch_json(url):
    req = Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
    with urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode('utf-8'))


def refresh_once():
    global _last_refresh
    if not _lock.acquire(blocking=False):
        return False
    started = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    errors = []
    all_events = {}
    try:
        for sport, division, label, sport_key in NCAA_SOURCES:
            for offset in range(0, LOOKAHEAD_DAYS + 1):
                day = (datetime.now(timezone.utc).date() + timedelta(days=offset)).isoformat()
                endpoint = BASE.format(sport=sport, division=division, date=day)
                try:
                    obj = fetch_json(endpoint)
                    for g in extract_games(obj):
                        e = normalize_game(g, label, endpoint, sport_key)
                        if e:
                            all_events[e['id']] = e
                except HTTPError as ex:
                    if ex.code not in (404, 204): errors.append(f'{sport}/{day}: HTTP {ex.code}')
                except Exception as ex:
                    errors.append(f'{sport}/{day}: {type(ex).__name__}')
        events = sorted(all_events.values(), key=lambda x: x['start_utc'])
        if events:
            write_data(events)
            _last_refresh = {'status':'ready','started_at':started,'finished_at':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),'events':len(events),'error':' | '.join(errors[:8]),'source':'Official NCAA public scoreboard JSON'}
        else:
            _last_refresh = {'status':'kept_bundled','started_at':started,'finished_at':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),'events':len(read_data()),'error':'No events returned from NCAA public endpoints; bundled cache kept.','source':'bundled snapshot'}
        return bool(events)
    finally:
        _lock.release()


def refresh_loop():
    # Refresh immediately, then every configured interval while the free web instance is awake.
    while True:
        try:
            refresh_once()
        except Exception as e:
            print('refresh error:', repr(e), flush=True)
        time.sleep(REFRESH_MINUTES * 60)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def json_response(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store, max-age=0')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split('?')[0]
        if path in ('/api/events', '/api/events/'):
            # If the cache is older than the interval, attempt a synchronous refresh once.
            try:
                mtime = DATA.stat().st_mtime
                if time.time() - mtime > REFRESH_MINUTES * 60:
                    refresh_once()
            except Exception:
                pass
            self.json_response(read_data())
            return
        if path in ('/api/health', '/health'):
            d = read_data()
            self.json_response({
                'ok': True,
                'service': 'NCAA All Sports',
                'time_utc': datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
                'events': len(d),
                'refresh_minutes': REFRESH_MINUTES,
                'lookahead_days': LOOKAHEAD_DAYS,
                'refresh': _last_refresh,
            })
            return
        if path in ('/api/refresh', '/api/refresh/'):
            threading.Thread(target=refresh_once, daemon=True).start()
            self.json_response({'ok': True, 'message': 'Refresh started', 'refresh_minutes': REFRESH_MINUTES})
            return
        super().do_GET()


if __name__ == '__main__':
    print(f'NCAA All Sports listening on {PORT}', flush=True)
    print(f'Official NCAA JSON refresh every {REFRESH_MINUTES} minutes; lookahead={LOOKAHEAD_DAYS+1} days; tennis excluded.', flush=True)
    threading.Thread(target=refresh_loop, daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
