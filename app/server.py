import os, json, sqlite3, threading, time, hashlib
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.parse import urlparse, quote
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(ROOT, "data", "ncaa.sqlite3"))
REFRESH_MINUTES = max(10, int(os.environ.get("REFRESH_MINUTES", "15")))
FETCH_DAYS_BEFORE = 1
FETCH_DAYS_AFTER = 7

SPORTS = {
    "football":"#facc15", "soccer":"#22c55e", "basketball":"#f97316",
    "volleyball":"#a855f7", "baseball":"#ef4444", "softball":"#ec4899",
    "ice_hockey":"#3b82f6", "field_hockey":"#a16207", "track_field":"#7dd3fc",
    "swimming_diving":"#06b6d4", "wrestling":"#f59e0b", "gymnastics":"#8b5cf6",
    "lacrosse":"#14b8a6", "cross_country":"#84cc16", "water_polo":"#0ea5e9",
    "rowing":"#64748b", "golf":"#65a30d", "fencing":"#94a3b8"
}
ALLOWED_SPORTS = set(SPORTS)

# These are public ESPN site scoreboard endpoints. They are not presented as
# a redistribution license. Public deployment must comply with provider terms.
ESPN_FEEDS = {
    "football": [("ESPN Football", "football", "college-football")],
    "basketball": [
        ("ESPN Men's Basketball", "basketball", "mens-college-basketball"),
        ("ESPN Women's Basketball", "basketball", "womens-college-basketball")],
    "baseball": [("ESPN Baseball", "baseball", "college-baseball")],
    "softball": [("ESPN Softball", "softball", "college-softball")],
    "soccer": [
        ("ESPN Men's Soccer", "soccer", "usa.ncaa"),
        ("ESPN Women's Soccer", "soccer", "usa.w.ncaa")],
    "volleyball": [("ESPN Women's Volleyball", "volleyball", "womens-college-volleyball")],
    "ice_hockey": [
        ("ESPN Men's Hockey", "hockey", "mens-college-hockey"),
        ("ESPN Women's Hockey", "hockey", "womens-college-hockey")],
}

# These sports do not currently have a verified ESPN scoreboard league in this
# adapter. They remain visible in the UI, but the engine will report them as
# unavailable rather than inventing events.
UNVERIFIED_ESPN = {
    "field_hockey": "No verified ESPN NCAA scoreboard feed configured",
    "lacrosse": "No verified ESPN NCAA scoreboard feed configured",
    "wrestling": "No verified ESPN NCAA scoreboard feed configured",
    "gymnastics": "No verified ESPN NCAA scoreboard feed configured",
    "track_field": "No verified ESPN NCAA scoreboard feed configured",
    "swimming_diving": "No verified ESPN NCAA scoreboard feed configured",
    "cross_country": "No verified ESPN NCAA scoreboard feed configured",
    "water_polo": "No verified ESPN NCAA scoreboard feed configured",
    "rowing": "No verified ESPN NCAA scoreboard feed configured",
    "golf": "No verified ESPN NCAA scoreboard feed configured",
    "fencing": "No verified ESPN NCAA scoreboard feed configured",
}



def db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("""CREATE TABLE IF NOT EXISTS events(
        id TEXT PRIMARY KEY, sport TEXT NOT NULL, start_utc TEXT NOT NULL,
        home TEXT, away TEXT, competition TEXT, conference TEXT, venue TEXT,
        status TEXT, source TEXT, source_url TEXT, confidence REAL DEFAULT 0,
        updated_at TEXT NOT NULL, raw_hash TEXT,
        upstream_id TEXT, links_json TEXT DEFAULT '{}',
        home_score TEXT, away_score TEXT, home_rank TEXT, away_rank TEXT,
        broadcasts_json TEXT DEFAULT '[]', notes_json TEXT DEFAULT '[]' 
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS source_status(
        source TEXT PRIMARY KEY, ok INTEGER, message TEXT, checked_at TEXT
    )""")
    # Non-destructive migration for V1-V4 databases.
    existing_cols = {row[1] for row in c.execute("PRAGMA table_info(events)").fetchall()}
    for col, typ in [
        ("upstream_id","TEXT"),("links_json","TEXT DEFAULT '{}'"),
        ("home_score","TEXT"),("away_score","TEXT"),("home_rank","TEXT"),("away_rank","TEXT"),
        ("broadcasts_json","TEXT DEFAULT '[]'"),("notes_json","TEXT DEFAULT '[]'")
    ]:
        if col not in existing_cols:
            c.execute(f"ALTER TABLE events ADD COLUMN {col} {typ}")

    # Older builds used fake SEED rows. Never expose them on the live site.
    c.execute("DELETE FROM events WHERE UPPER(COALESCE(source,''))='SEED'")
    c.commit()
    return c

DB = db()
DB_LOCK = threading.Lock()


def iso_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_sport(v):
    s = str(v or "").lower().strip().replace("&", "and").replace("-", "_").replace(" ", "_")
    aliases = {
        "football":"football", "american_football":"football", "ncaaf":"football",
        "soccer":"soccer", "mens_soccer":"soccer", "womens_soccer":"soccer",
        "basketball":"basketball", "ncaab":"basketball", "volleyball":"volleyball",
        "baseball":"baseball", "softball":"softball", "ice_hockey":"ice_hockey", "hockey":"ice_hockey",
        "field_hockey":"field_hockey", "track":"track_field", "track_and_field":"track_field",
        "track_field":"track_field", "swimming":"swimming_diving", "swimming_and_diving":"swimming_diving",
        "wrestling":"wrestling", "gymnastics":"gymnastics", "lacrosse":"lacrosse",
        "cross_country":"cross_country", "water_polo":"water_polo", "rowing":"rowing",
        "golf":"golf", "fencing":"fencing"
    }
    return aliases.get(s, s)


def parse_time(v):
    if not v: return None
    s = str(v).strip()
    if s.endswith("Z"): s = s[:-1] + "+00:00"
    try:
        d = datetime.fromisoformat(s)
        if d.tzinfo is None: d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except Exception:
        return None


def clean_team(v):
    return " ".join(str(v or "").lower().strip().split())

def event_id(e):
    # Provider-independent canonical key so the same game from ESPN + an
    # authorized official feed is stored as one event, not duplicates.
    key = "|".join([
        normalize_sport(e.get("sport")),
        e.get("start_utc", "")[:19],
        clean_team(e.get("home")),
        clean_team(e.get("away")),
        clean_team(e.get("competition")),
    ])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


def upsert_event(e, confidence=0.55):
    now = iso_now()
    with DB_LOCK:
        existing = DB.execute(
            "SELECT source,source_url,confidence,upstream_id,links_json,home_score,away_score,home_rank,away_rank,broadcasts_json,notes_json FROM events WHERE id=?",
            (e["id"],)
        ).fetchone()
        source=e.get("source") or ""; source_url=e.get("source_url") or ""; links=e.get("links") or {}; conf=confidence
        if existing:
            old_sources=[x.strip() for x in (existing["source"] or "").split(" + ") if x.strip()]
            if source and source not in old_sources: old_sources.append(source)
            source=" + ".join(old_sources); source_url=source_url or existing["source_url"] or ""
            conf=max(float(existing["confidence"] or 0),confidence)
            try: old_links=json.loads(existing["links_json"] or "{}")
            except Exception: old_links={}
            if not isinstance(old_links,dict): old_links={}
            if isinstance(links,dict):
                for k,v in links.items():
                    if v and k not in old_links: old_links[k]=v
            links=old_links
            for key in ("upstream_id","home_score","away_score","home_rank","away_rank"):
                if not e.get(key) and existing[key]: e[key]=existing[key]
            for key in ("broadcasts","notes"):
                if not e.get(key):
                    try: e[key]=json.loads(existing[f"{key}_json"] or "[]")
                    except Exception: e[key]=[]
        DB.execute("""INSERT INTO events
          (id,sport,start_utc,home,away,competition,conference,venue,status,source,source_url,confidence,updated_at,raw_hash,
           upstream_id,links_json,home_score,away_score,home_rank,away_rank,broadcasts_json,notes_json)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(id) DO UPDATE SET
          sport=excluded.sport,start_utc=excluded.start_utc,home=excluded.home,away=excluded.away,
          competition=excluded.competition,conference=excluded.conference,venue=excluded.venue,
          status=excluded.status,source=excluded.source,source_url=excluded.source_url,
          confidence=MAX(events.confidence,excluded.confidence),updated_at=excluded.updated_at,
          raw_hash=excluded.raw_hash,upstream_id=COALESCE(excluded.upstream_id,events.upstream_id),
          links_json=excluded.links_json,home_score=excluded.home_score,away_score=excluded.away_score,
          home_rank=excluded.home_rank,away_rank=excluded.away_rank,broadcasts_json=excluded.broadcasts_json,
          notes_json=excluded.notes_json""",
          (e["id"],normalize_sport(e["sport"]),e["start_utc"],e.get("home"),e.get("away"),
           e.get("competition"),e.get("conference"),e.get("venue"),e.get("status"),source,source_url,
           conf,now,e.get("raw_hash",""),e.get("upstream_id"),json.dumps(links,ensure_ascii=False),
           e.get("home_score"),e.get("away_score"),e.get("home_rank"),e.get("away_rank"),
           json.dumps(e.get("broadcasts") or [],ensure_ascii=False),
           json.dumps(e.get("notes") or [],ensure_ascii=False)))


def fetch_json(url, api_key=""):
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        raise ValueError("Feed URL must use HTTP(S).")
    headers = {"User-Agent":"NCAA-All-Sports/1.1", "Accept":"application/json"}
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    req = Request(url, headers=headers)
    with urlopen(req, timeout=20) as r:
        raw = r.read()
        if len(raw) > 12_000_000:
            raise ValueError("Feed response is too large")
        return json.loads(raw.decode("utf-8"))


def set_source(name, ok, message):
    with DB_LOCK:
        DB.execute("INSERT OR REPLACE INTO source_status VALUES(?,?,?,?)", (name, 1 if ok else 0, str(message)[:500], iso_now()))
        DB.commit()


def _as_dict(v):
    return v if isinstance(v, dict) else {}


def _first_name(v):
    if isinstance(v, dict):
        return v.get("displayName") or v.get("shortDisplayName") or v.get("name") or v.get("shortName")
    if isinstance(v, str):
        return v
    return None


def parse_espn(payload, sport, source_name):
    """Parse ESPN scoreboard JSON defensively.

    ESPN sometimes returns strings in arrays that historically contained
    objects (notably links/broadcast names/notes). V7 ignores malformed
    optional fields instead of dropping the entire event/feed.
    """
    rows = []
    if not isinstance(payload, dict):
        return rows
    events = payload.get("events") or []
    if not isinstance(events, list):
        return rows
    for ev in events:
        if not isinstance(ev, dict):
            continue
        competitions = ev.get("competitions") or []
        if not isinstance(competitions, list):
            competitions = []
        comp = _as_dict(competitions[0]) if competitions else {}
        start = parse_time(ev.get("date") or comp.get("date"))
        if not start:
            continue

        competitors = comp.get("competitors") or []
        if not isinstance(competitors, list):
            competitors = []
        home = away = None
        for c in competitors:
            if not isinstance(c, dict):
                continue
            name = _first_name(c.get("team")) or _first_name(c.get("athlete")) or _first_name(c.get("name"))
            if c.get("homeAway") == "home":
                home = name
            elif c.get("homeAway") == "away":
                away = name
        if not home and competitors and isinstance(competitors[0], dict):
            home = _first_name(competitors[0].get("team")) or _first_name(competitors[0].get("name"))
        if not away and len(competitors) > 1 and isinstance(competitors[1], dict):
            away = _first_name(competitors[1].get("team")) or _first_name(competitors[1].get("name"))

        venue_obj = _as_dict(comp.get("venue"))
        address = venue_obj.get("address")
        city = address.get("city") if isinstance(address, dict) else (address if isinstance(address, str) else "")
        venue = venue_obj.get("fullName") or city or ""

        status_obj = comp.get("status") or ev.get("status") or {}
        status_obj = _as_dict(status_obj)
        status_type = _as_dict(status_obj.get("type"))
        status = status_type.get("detail") or status_type.get("description") or status_obj.get("detail") or "Scheduled"

        leagues = payload.get("leagues") or []
        league_name = None
        if isinstance(leagues, list) and leagues:
            league_name = _first_name(leagues[0])
        season = _as_dict(ev.get("season"))
        league = season.get("displayName") or league_name or "NCAA"

        links = ev.get("links") or []
        if not isinstance(links, list):
            links = []
        source_url = ""
        link_map = {}
        for link in links:
            if isinstance(link, dict):
                href = link.get("href") or ""
                rels = link.get("rel") or []
                if isinstance(rels, str):
                    rels = [rels]
                if href and not source_url:
                    source_url = href
                if href and isinstance(rels, list):
                    for rel in rels:
                        if rel:
                            link_map[str(rel).lower()] = href
            elif isinstance(link, str) and link and not source_url:
                source_url = link

        home_score = away_score = home_rank = away_rank = None
        for c in competitors:
            if not isinstance(c, dict):
                continue
            score = c.get("score")
            rank = c.get("rank")
            if c.get("homeAway") == "home":
                home_score = str(score) if score is not None else None
                home_rank = str(rank) if rank is not None else None
            elif c.get("homeAway") == "away":
                away_score = str(score) if score is not None else None
                away_rank = str(rank) if rank is not None else None

        broadcasts = []
        raw_broadcasts = comp.get("broadcasts") or []
        if isinstance(raw_broadcasts, list):
            for b in raw_broadcasts:
                if isinstance(b, dict):
                    names = b.get("names") or []
                    if isinstance(names, str):
                        names = [names]
                    if not isinstance(names, list):
                        names = []
                    for n in names:
                        name = _first_name(n)
                        if name and name not in broadcasts:
                            broadcasts.append(name)
                elif isinstance(b, str) and b not in broadcasts:
                    broadcasts.append(b)

        notes = []
        raw_notes = comp.get("notes") or ev.get("notes") or []
        if isinstance(raw_notes, list):
            for n in raw_notes:
                text = n.get("headline") if isinstance(n, dict) else n
                if text and str(text) not in notes:
                    notes.append(str(text))
        elif isinstance(raw_notes, str):
            notes.append(raw_notes)

        e = {
            "sport": sport, "start_utc": start, "home": home or "TBD", "away": away or "TBD",
            "competition": league, "conference": "", "venue": venue, "status": status,
            "source": source_name, "source_url": source_url, "upstream_id": ev.get("id"),
            "links": link_map, "home_score": home_score, "away_score": away_score,
            "home_rank": home_rank, "away_rank": away_rank, "broadcasts": broadcasts, "notes": notes
        }
        e["id"] = event_id(e)
        e["raw_hash"] = hashlib.sha256(json.dumps(ev, sort_keys=True).encode()).hexdigest()
        rows.append(e)
    return rows


def fetch_espn_feed(source_name, path_sport, league, date):
    url = f"https://site.api.espn.com/apis/site/v2/sports/{quote(path_sport)}/{quote(league)}/scoreboard?dates={date.strftime('%Y%m%d')}&limit=1000"
    payload = fetch_json(url)
    return source_name, parse_espn(payload, normalize_sport(path_sport), source_name), True


def refresh_espn():
    jobs = []
    today = datetime.now(timezone.utc).date()
    for sport, feeds in ESPN_FEEDS.items():
        for source_name, path_sport, league in feeds:
            for offset in range(-FETCH_DAYS_BEFORE, FETCH_DAYS_AFTER + 1):
                jobs.append((sport, source_name, path_sport, league, today + timedelta(days=offset)))

    results = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        future_map = {
            pool.submit(fetch_espn_feed, name, ps, league, date): name
            for _, name, ps, league, date in jobs
        }
        for fut in as_completed(future_map):
            name = future_map[fut]
            rec = results.setdefault(name, {"success": 0, "events": 0, "errors": []})
            try:
                _, rows, ok = fut.result()
                rec["success"] += 1 if ok else 0
                rec["events"] += len(rows)
                for e in rows:
                    upsert_event(e, 0.55)
            except Exception as ex:
                rec["errors"].append(str(ex)[:180])

    for sport, feeds in ESPN_FEEDS.items():
        for source_name, _, _ in feeds:
            rec = results.get(source_name, {"success":0,"events":0,"errors":[]})
            if rec["success"]:
                msg = f"Live feed reachable: {rec['events']} events from {rec['success']} date request(s)"
                set_source(source_name, True, msg)
            else:
                msg = "; ".join(rec["errors"][:2]) or "No successful response"
                set_source(source_name, False, msg)

    for sport, message in UNVERIFIED_ESPN.items():
        set_source(f"ESPN {sport.replace('_',' ').title()}", False, message)

    with DB_LOCK:
        DB.commit()
    reconcile()

def refresh_custom_sources():
    configs = [
        ("NCAA", os.environ.get("NCAA_SCHEDULE_URL", ""), os.environ.get("NCAA_API_KEY", "")),
        ("Official", os.environ.get("OFFICIAL_SCHEDULE_URL", ""), os.environ.get("OFFICIAL_API_KEY", ""))
    ]
    for name, url, key in configs:
        if not url:
            continue
        try:
            payload = fetch_json(url, key)
            if isinstance(payload, list): items = payload
            elif isinstance(payload, dict):
                items = next((payload.get(k) for k in ("events","items","games","schedule","data") if isinstance(payload.get(k), list)), [])
            else: items = []
            count = 0
            for item in items:
                if not isinstance(item, dict): continue
                sport = normalize_sport(item.get("sport") or item.get("sport_key") or item.get("category"))
                if sport not in ALLOWED_SPORTS: continue
                start = parse_time(item.get("start_utc") or item.get("startTime") or item.get("date") or item.get("start"))
                if not start: continue
                comp = item.get("competition") or item.get("league") or item.get("tournament") or ""
                if isinstance(comp, dict): comp = comp.get("name", "")
                def tn(x): return (x.get("name") or x.get("displayName")) if isinstance(x, dict) else x
                teams = item.get("teams") if isinstance(item.get("teams"), dict) else {}
                home = tn(item.get("home") or item.get("homeTeam") or teams.get("home")) or "TBD"
                away = tn(item.get("away") or item.get("awayTeam") or teams.get("away")) or "TBD"
                e = {"sport":sport,"start_utc":start,"home":home,"away":away,"competition":comp or "NCAA",
                     "conference":item.get("conference") or "","venue":tn(item.get("venue") or item.get("location")) or "",
                     "status":item.get("status") or "Scheduled","source":name,"source_url":item.get("source_url") or "",
                     "upstream_id":item.get("id") or item.get("event_id"),
                     "links":item.get("links") if isinstance(item.get("links"),dict) else {},
                     "home_score":str(item.get("home_score")) if item.get("home_score") is not None else None,
                     "away_score":str(item.get("away_score")) if item.get("away_score") is not None else None,
                     "home_rank":str(item.get("home_rank")) if item.get("home_rank") is not None else None,
                     "away_rank":str(item.get("away_rank")) if item.get("away_rank") is not None else None,
                     "broadcasts":item.get("broadcasts") if isinstance(item.get("broadcasts"),list) else [],
                     "notes":item.get("notes") if isinstance(item.get("notes"),list) else []}
                e["id"] = event_id(e)
                e["raw_hash"] = hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest()
                upsert_event(e, 0.75)
                count += 1
            set_source(name, True, f"Configured feed returned {count} events")
        except Exception as ex:
            set_source(name, False, str(ex)[:500])
    reconcile()


def reconcile():
    with DB_LOCK:
        rows = DB.execute("""SELECT id,source,confidence FROM events""").fetchall()
        for r in rows:
            n = len([x for x in (r["source"] or "").split(" + ") if x.strip()])
            conf = min(0.99, max(float(r["confidence"] or 0), 0.55 + 0.20 * max(0, n - 1)))
            DB.execute("UPDATE events SET confidence=? WHERE id=?", (conf, r["id"]))
        cutoff = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        future = (datetime.now(timezone.utc) + timedelta(days=8)).isoformat()
        # Keep only the window the public UI/API can use. This prevents stale cache growth.
        DB.execute("DELETE FROM events WHERE start_utc < ? OR start_utc >= ?", (cutoff, future))
        DB.commit()


def refresh_all():
    refresh_espn()
    refresh_custom_sources()


def scheduler():
    while True:
        try:
            refresh_all()
        except Exception as ex:
            set_source("ENGINE", False, str(ex))
        time.sleep(REFRESH_MINUTES * 60)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def send_json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/health":
            row = DB.execute("SELECT COUNT(*) c FROM events").fetchone()
            self.send_json({"ok":True,"service":"NCAA All Sports","time_utc":iso_now(),"events":row["c"],"refresh_minutes":REFRESH_MINUTES})
            return
        if path == "/api/sources":
            rows = DB.execute("SELECT source,ok,message,checked_at FROM source_status ORDER BY source").fetchall()
            self.send_json([dict(r) for r in rows])
            return
        if path.startswith("/api/event/"):
            event_id_req=path.split("/api/event/",1)[1]
            row=DB.execute("SELECT * FROM events WHERE id=?",(event_id_req,)).fetchone()
            if not row:
                self.send_json({"error":"Event not found"},404); return
            out=dict(row)
            try: out["links"]=json.loads(out.get("links_json") or "{}")
            except Exception: out["links"]={}
            for key in ("broadcasts","notes"):
                try: out[key]=json.loads(out.get(f"{key}_json") or "[]")
                except Exception: out[key]=[]
            if out.get("upstream_id") and "ESPN" in (out.get("source") or ""):
                source_names=(out.get("source") or "").split(" + ")
                feed=next((x for feeds in ESPN_FEEDS.values() for x in feeds if x[0] in source_names),None)
                if feed:
                    _,path_sport,league=feed
                    try:
                        summary_url=f"https://site.api.espn.com/apis/site/v2/sports/{quote(path_sport)}/{quote(league)}/summary?event={quote(str(out['upstream_id']))}"
                        summary=fetch_json(summary_url)
                        out["summary_available"]=True
                        # Keep the useful parts of the live response, but only expose
                        # links that ESPN actually returned. Nothing is invented here.
                        summary_competitions = summary.get("header",{}).get("competitions",[]) if isinstance(summary.get("header"),dict) else []
                        summary_comp = summary_competitions[0] if isinstance(summary_competitions,list) and summary_competitions and isinstance(summary_competitions[0],dict) else {}
                        extra_links = {}
                        for container in (summary.get("links"), summary_comp.get("links"), summary.get("header",{}).get("links") if isinstance(summary.get("header"),dict) else None):
                            if isinstance(container,list):
                                for link in container:
                                    if isinstance(link,dict) and link.get("href"):
                                        rel=link.get("rel") or []
                                        if isinstance(rel,str): rel=[rel]
                                        for r in rel if isinstance(rel,list) else []:
                                            extra_links[str(r).lower()]=link["href"]
                        if extra_links:
                            merged=dict(out.get("links") or {})
                            merged.update({k:v for k,v in extra_links.items() if v})
                            out["links"]=merged
                        summary_broadcasts = summary.get("broadcasts") or summary_comp.get("broadcasts") or []
                        if isinstance(summary_broadcasts,list):
                            names=[]
                            for b in summary_broadcasts:
                                if isinstance(b,dict):
                                    ns=b.get("names") or b.get("name") or []
                                    if isinstance(ns,str): ns=[ns]
                                    if isinstance(ns,list): names.extend(str(n.get("name") if isinstance(n,dict) else n) for n in ns if n)
                                elif isinstance(b,str): names.append(b)
                            out["broadcasts"]=list(dict.fromkeys((out.get("broadcasts") or [])+[n for n in names if n]))
                        out["summary"]={"plays":summary.get("plays") or [],"leaders":summary.get("leaders") or [],
                            "situation":summary.get("situation") or {},"odds":summary.get("odds") or [],
                            "pickcenter":summary.get("pickcenter") or [],"winprobability":summary.get("winprobability") or [],
                            "broadcasts":summary.get("broadcasts") or [],"news":summary.get("news") or [],
                            "boxscore":summary.get("boxscore") or {},
                            "header":summary.get("header") or {},
                            "gamepackage":summary.get("gamepackage") or {},
                            "raw":summary}
                        # Build practical team/conference cards from the provider response.
                        # Only provider-supplied values are exposed; no school data is invented.
                        team_profiles = []
                        for tc in (summary_comp.get("competitors") or []):
                            if not isinstance(tc, dict):
                                continue
                            tm = tc.get("team") if isinstance(tc.get("team"), dict) else {}
                            if not isinstance(tm, dict):
                                tm = {}
                            profile = {
                                "id": tm.get("id") or tc.get("id"),
                                "name": tm.get("displayName") or tm.get("name") or _first_name(tm) or "",
                                "short_name": tm.get("shortDisplayName") or tm.get("shortName") or "",
                                "abbreviation": tm.get("abbreviation") or "",
                                "location": tm.get("location") or "",
                                "slug": tm.get("slug") or "",
                                "logo": tm.get("logo") or "",
                                "logos": tm.get("logos") if isinstance(tm.get("logos"), list) else [],
                                "color": tm.get("color") or "",
                                "alternate_color": tm.get("alternateColor") or "",
                                "rank": tc.get("rank"),
                                "score": tc.get("score"),
                                "home_away": tc.get("homeAway") or "",
                                "winner": tc.get("winner"),
                                "records": tc.get("records") if isinstance(tc.get("records"), list) else [],
                                "links": tm.get("links") if isinstance(tm.get("links"), list) else []
                            }
                            team_profiles.append(profile)
                        out["team_profiles"] = team_profiles
                        comp_name = (summary_comp.get("league") or {}).get("name") if isinstance(summary_comp.get("league"), dict) else None
                        if not comp_name:
                            comp_name = out.get("conference") or out.get("competition") or ""
                        league = summary_comp.get("league") if isinstance(summary_comp.get("league"), dict) else {}
                        out["competition_profile"] = {
                            "name": comp_name or out.get("competition") or "NCAA",
                            "conference": out.get("conference") or "",
                            "league": league.get("name") or "",
                            "abbreviation": league.get("abbreviation") or "",
                            "slug": league.get("slug") or "",
                            "links": (summary_comp.get("links") if isinstance(summary_comp.get("links"), list) else [])
                        }
                    except Exception as ex:
                        out["summary_available"]=False; out["summary_error"]=str(ex)[:180]
            self.send_json(out); return

        if path == "/api/events":
            now = datetime.now(timezone.utc)
            lo = (now - timedelta(days=1)).isoformat()
            hi = (now + timedelta(days=8)).isoformat()
            rows = DB.execute("SELECT * FROM events WHERE start_utc>=? AND start_utc<? ORDER BY start_utc", (lo,hi)).fetchall()
            out=[]
            for r in rows:
                d=dict(r); d["color"] = SPORTS.get(d["sport"]); out.append(d)
            self.send_json(out)
            return
        if path == "/api/stats":
            rows = DB.execute("SELECT sport,COUNT(*) c FROM events GROUP BY sport ORDER BY sport").fetchall()
            self.send_json({"events":sum(r["c"] for r in rows),"by_sport":{r["sport"]:r["c"] for r in rows}})
            return
        if path == "/": path = "/index.html"
        safe = os.path.normpath(path.lstrip("/"))
        if safe.startswith(".."): self.send_response(403); self.end_headers(); return
        fp = os.path.join(WEB, safe)
        if not os.path.isfile(fp): self.send_response(404); self.end_headers(); return
        typ = "text/html; charset=utf-8" if fp.endswith(".html") else "text/css; charset=utf-8" if fp.endswith(".css") else "application/javascript; charset=utf-8" if fp.endswith(".js") else "image/svg+xml" if fp.endswith(".svg") else "image/png" if fp.endswith(".png") else "application/octet-stream"
        data=open(fp,"rb").read()
        self.send_response(200); self.send_header("Content-Type",typ); self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    threading.Thread(target=scheduler, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
