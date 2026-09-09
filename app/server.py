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
        ("ESPN Men's Soccer", "soccer", "mens-college-soccer"),
        ("ESPN Women's Soccer", "soccer", "womens-college-soccer")],
    "volleyball": [("ESPN Women's Volleyball", "volleyball", "womens-college-volleyball")],
    "ice_hockey": [
        ("ESPN Men's Hockey", "hockey", "mens-college-hockey"),
        ("ESPN Women's Hockey", "hockey", "womens-college-hockey")],
    "field_hockey": [("ESPN Field Hockey", "field-hockey", "college-field-hockey")],
    "lacrosse": [
        ("ESPN Men's Lacrosse", "lacrosse", "college-mens-lacrosse"),
        ("ESPN Women's Lacrosse", "lacrosse", "college-womens-lacrosse")],
    "wrestling": [("ESPN Wrestling", "wrestling", "college-wrestling")],
    "gymnastics": [("ESPN Gymnastics", "gymnastics", "womens-college-gymnastics")]
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
        updated_at TEXT NOT NULL, raw_hash TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS source_status(
        source TEXT PRIMARY KEY, ok INTEGER, message TEXT, checked_at TEXT
    )""")
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


def event_id(e):
    # Prefer upstream ID where available, but keep deterministic IDs for custom feeds.
    upstream = e.get("upstream_id")
    if upstream:
        return hashlib.sha256((e["source"] + "|" + str(upstream)).encode()).hexdigest()[:24]
    key = "|".join([e["sport"], e.get("start_utc", "")[:16], (e.get("home") or "").lower().strip(), (e.get("away") or "").lower().strip()])
    return hashlib.sha256(key.encode()).hexdigest()[:24]


def upsert_event(e, confidence=0.55):
    now = iso_now()
    with DB_LOCK:
        DB.execute("""INSERT INTO events
          (id,sport,start_utc,home,away,competition,conference,venue,status,source,source_url,confidence,updated_at,raw_hash)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(id) DO UPDATE SET
          start_utc=excluded.start_utc,home=excluded.home,away=excluded.away,
          competition=excluded.competition,conference=excluded.conference,venue=excluded.venue,
          status=excluded.status,source=excluded.source,source_url=excluded.source_url,
          confidence=MAX(events.confidence,excluded.confidence), updated_at=excluded.updated_at,
          raw_hash=excluded.raw_hash""",
          (e["id"], e["sport"], e["start_utc"], e.get("home"), e.get("away"), e.get("competition"),
           e.get("conference"), e.get("venue"), e.get("status"), e.get("source"), e.get("source_url"),
           confidence, now, e.get("raw_hash", "")))


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


def parse_espn(payload, sport, source_name):
    rows = []
    if not isinstance(payload, dict): return rows
    for ev in payload.get("events", []) or []:
        competitions = ev.get("competitions") or []
        comp = competitions[0] if competitions else {}
        start = parse_time(ev.get("date") or comp.get("date"))
        if not start: continue
        competitors = comp.get("competitors") or []
        home = away = None
        for c in competitors:
            team = c.get("team") or {}
            name = team.get("displayName") or team.get("shortDisplayName") or team.get("name")
            if c.get("homeAway") == "home": home = name
            elif c.get("homeAway") == "away": away = name
        if not home and competitors:
            home = ((competitors[0].get("team") or {}).get("displayName"))
        if not away and len(competitors) > 1:
            away = ((competitors[1].get("team") or {}).get("displayName"))
        venue_obj = comp.get("venue") or {}
        venue = venue_obj.get("fullName") or ((venue_obj.get("address") or {}).get("city") or "")
        status_obj = comp.get("status") or ev.get("status") or {}
        status_type = status_obj.get("type") or {}
        status = status_type.get("detail") or status_type.get("description") or "Scheduled"
        league = ((ev.get("season") or {}).get("displayName") or ((payload.get("leagues") or [{}])[0].get("name") if payload.get("leagues") else None) or "NCAA")
        links = ev.get("links") or []
        source_url = next((x.get("href") for x in links if x.get("href")), "")
        e = {
            "sport": sport, "start_utc": start, "home": home or "TBD", "away": away or "TBD",
            "competition": league, "conference": "", "venue": venue, "status": status,
            "source": source_name, "source_url": source_url, "upstream_id": ev.get("id")
        }
        e["id"] = event_id(e)
        e["raw_hash"] = hashlib.sha256(json.dumps(ev, sort_keys=True).encode()).hexdigest()
        rows.append(e)
    return rows


def fetch_espn_feed(source_name, path_sport, league, date):
    url = f"https://site.api.espn.com/apis/site/v2/sports/{quote(path_sport)}/{quote(league)}/scoreboard?dates={date.strftime('%Y%m%d')}&limit=1000"
    payload = fetch_json(url)
    return source_name, parse_espn(payload, normalize_sport(league), source_name), True


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
                     "upstream_id":item.get("id") or item.get("event_id")}
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
        rows = DB.execute("""SELECT sport,start_utc,lower(trim(home)) h,lower(trim(away)) a,COUNT(DISTINCT source) n
                             FROM events GROUP BY sport,start_utc,h,a""").fetchall()
        for r in rows:
            conf = min(0.99, 0.55 + 0.20 * max(0, r["n"] - 1))
            DB.execute("""UPDATE events SET confidence=? WHERE sport=? AND start_utc=? AND lower(trim(home))=? AND lower(trim(away))=?""", (conf,r["sport"],r["start_utc"],r["h"],r["a"]))
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
