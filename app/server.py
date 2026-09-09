import os, json, sqlite3, threading, time, hashlib
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.parse import urlparse, quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(ROOT, "data", "ncaa.sqlite3"))
REFRESH_MINUTES = max(5, int(os.environ.get("REFRESH_MINUTES", "15")))

SPORTS = {
    "football":"#facc15","soccer":"#22c55e","basketball":"#f97316",
    "volleyball":"#a855f7","baseball":"#ef4444","softball":"#ec4899",
    "ice_hockey":"#3b82f6","field_hockey":"#a16207","track_field":"#7dd3fc",
    "swimming_diving":"#06b6d4","wrestling":"#f59e0b","gymnastics":"#8b5cf6",
    "lacrosse":"#14b8a6","cross_country":"#84cc16","water_polo":"#0ea5e9",
    "rowing":"#64748b","golf":"#65a30d","fencing":"#94a3b8"
}
ALLOWED_SPORTS = set(SPORTS)

# ESPN public scoreboard endpoints. These are used only where the endpoint
# returns data; unsupported/empty sports remain empty rather than fabricated.
ESPN_FEEDS = {
    "football": [
        ("ESPN Football", "football", "college-football")
    ],
    "basketball": [
        ("ESPN Men's Basketball", "basketball", "mens-college-basketball"),
        ("ESPN Women's Basketball", "basketball", "womens-college-basketball")
    ],
    "baseball": [
        ("ESPN Baseball", "baseball", "college-baseball")
    ],
    "softball": [
        ("ESPN Softball", "softball", "college-softball")
    ],
    "soccer": [
        ("ESPN Men's Soccer", "soccer", "mens-college-soccer"),
        ("ESPN Women's Soccer", "soccer", "womens-college-soccer")
    ],
    "volleyball": [
        ("ESPN Women's Volleyball", "volleyball", "womens-college-volleyball")
    ],
    "ice_hockey": [
        ("ESPN Men's Hockey", "hockey", "mens-college-hockey"),
        ("ESPN Women's Hockey", "hockey", "womens-college-hockey")
    ],
    "field_hockey": [
        ("ESPN Field Hockey", "field-hockey", "college-field-hockey")
    ],
    "lacrosse": [
        ("ESPN Men's Lacrosse", "lacrosse", "college-mens-lacrosse"),
        ("ESPN Women's Lacrosse", "lacrosse", "college-womens-lacrosse")
    ],
    "wrestling": [
        ("ESPN Wrestling", "wrestling", "college-wrestling")
    ],
    "gymnastics": [
        ("ESPN Gymnastics", "gymnastics", "womens-college-gymnastics")
    ]
}

def db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS events(
        id TEXT PRIMARY KEY, sport TEXT NOT NULL, start_utc TEXT NOT NULL,
        home TEXT, away TEXT, competition TEXT, conference TEXT, venue TEXT,
        status TEXT, source TEXT, source_url TEXT, confidence REAL DEFAULT 0,
        updated_at TEXT NOT NULL, raw_hash TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS source_status(
        source TEXT PRIMARY KEY, ok INTEGER, message TEXT, checked_at TEXT
    )""")
    c.commit()
    return c

DB = db()

def iso_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

def normalize_sport(v):
    s = str(v or "").lower().strip().replace("&","and").replace("-","_").replace(" ","_")
    aliases = {
        "football":"football","american_football":"football","ncaaf":"football",
        "soccer":"soccer","mens_soccer":"soccer","womens_soccer":"soccer",
        "basketball":"basketball","ncaab":"basketball",
        "volleyball":"volleyball","baseball":"baseball","softball":"softball",
        "ice_hockey":"ice_hockey","hockey":"ice_hockey","field_hockey":"field_hockey",
        "track":"track_field","track_and_field":"track_field","track_field":"track_field",
        "swimming":"swimming_diving","swimming_and_diving":"swimming_diving",
        "wrestling":"wrestling","gymnastics":"gymnastics","lacrosse":"lacrosse",
        "cross_country":"cross_country","water_polo":"water_polo","rowing":"rowing",
        "golf":"golf","fencing":"fencing"
    }
    return aliases.get(s, s)

def parse_time(v):
    if not v: return None
    s = str(v).strip()
    if s.endswith("Z"): s = s[:-1] + "+00:00"
    try:
        d = datetime.fromisoformat(s)
        if d.tzinfo is None: d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
    except Exception:
        return None

def event_id(e):
    key = "|".join([
        e["sport"], e.get("start_utc","")[:16],
        (e.get("home") or "").lower().strip(),
        (e.get("away") or "").lower().strip()
    ])
    return hashlib.sha256(key.encode()).hexdigest()[:24]

def upsert_event(e, confidence=0.55):
    now = iso_now()
    DB.execute("""INSERT INTO events
      (id,sport,start_utc,home,away,competition,conference,venue,status,source,source_url,confidence,updated_at,raw_hash)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
      ON CONFLICT(id) DO UPDATE SET
      start_utc=excluded.start_utc,home=excluded.home,away=excluded.away,
      competition=excluded.competition,conference=excluded.conference,venue=excluded.venue,
      status=excluded.status,source=excluded.source,source_url=excluded.source_url,
      confidence=MAX(events.confidence,excluded.confidence),
      updated_at=excluded.updated_at,raw_hash=excluded.raw_hash""",
      (e["id"],e["sport"],e["start_utc"],e["home"],e["away"],e["competition"],
       e["conference"],e["venue"],e["status"],e["source"],e["source_url"],
       confidence,now,e.get("raw_hash","")))

def fetch_json(url, api_key=""):
    p = urlparse(url)
    if p.scheme not in ("http","https"):
        raise ValueError("Feed URL must use HTTP(S).")
    headers = {
        "User-Agent":"NCAA-All-Sports/1.0",
        "Accept":"application/json"
    }
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    req = Request(url, headers=headers)
    with urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))

def set_source(name, ok, message):
    DB.execute("INSERT OR REPLACE INTO source_status VALUES(?,?,?,?)",
               (name,1 if ok else 0,str(message)[:300],iso_now()))

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
        venue = ((comp.get("venue") or {}).get("fullName") or
                 ((comp.get("venue") or {}).get("address") or {}).get("city") or "")
        status_obj = comp.get("status") or ev.get("status") or {}
        status_type = status_obj.get("type") or {}
        status = status_type.get("detail") or status_type.get("description") or "Scheduled"
        league = ((ev.get("season") or {}).get("displayName") or
                  ((payload.get("leagues") or [{}])[0].get("name") if payload.get("leagues") else None) or
                  "NCAA")
        url = ""
        links = ev.get("links") or []
        if links: url = links[0].get("href") or ""
        e = {
            "sport":sport, "start_utc":start, "home":home or "TBD", "away":away or "TBD",
            "competition":league, "conference":"", "venue":venue,
            "status":status, "source":source_name, "source_url":url
        }
        e["id"] = event_id(e)
        e["raw_hash"] = hashlib.sha256(json.dumps(ev,sort_keys=True).encode()).hexdigest()
        rows.append(e)
    return rows

def refresh_espn():
    total = 0
    today = datetime.now(timezone.utc).date()
    # Fetch a 10-day window so the site's Next 7 Days view is populated.
    for sport, feeds in ESPN_FEEDS.items():
        for source_name, path_sport, league in feeds:
            source_total = 0
            errors = []
            for offset in range(-1, 10):
                date = today + timedelta(days=offset)
                url = (
                    f"https://site.api.espn.com/apis/site/v2/sports/"
                    f"{quote(path_sport)}/{quote(league)}/scoreboard"
                    f"?dates={date.strftime('%Y%m%d')}&limit=1000"
                )
                try:
                    payload = fetch_json(url)
                    rows = parse_espn(payload, sport, source_name)
                    for e in rows:
                        upsert_event(e, 0.55)
                    source_total += len(rows)
                except Exception as ex:
                    errors.append(str(ex)[:120])
            if errors and source_total == 0:
                set_source(source_name, False, "; ".join(errors[:2]))
            else:
                set_source(source_name, True, f"Fetched {source_total} events")
            total += source_total
    DB.commit()
    reconcile()
    return total

def refresh_custom_sources():
    configs = [
        ("NCAA", os.environ.get("NCAA_SCHEDULE_URL",""), os.environ.get("NCAA_API_KEY","")),
        ("Official", os.environ.get("OFFICIAL_SCHEDULE_URL",""), os.environ.get("OFFICIAL_API_KEY",""))
    ]
    for name, url, key in configs:
        if not url:
            continue
        try:
            payload = fetch_json(url,key)
            items = payload if isinstance(payload,list) else next(
                (payload.get(k) for k in ("events","items","games","schedule","data")
                 if isinstance(payload,dict) and isinstance(payload.get(k),list)), [])
            count = 0
            for item in items:
                if not isinstance(item,dict): continue
                sport = normalize_sport(item.get("sport") or item.get("sport_key") or item.get("category"))
                if sport not in ALLOWED_SPORTS: continue
                start = parse_time(item.get("start_utc") or item.get("startTime") or item.get("date") or item.get("start"))
                if not start: continue
                comp = item.get("competition") or item.get("league") or item.get("tournament") or ""
                if isinstance(comp,dict): comp = comp.get("name","")
                def tn(x):
                    return x.get("name") or x.get("displayName") if isinstance(x,dict) else x
                teams = item.get("teams") if isinstance(item.get("teams"),dict) else {}
                home = tn(item.get("home") or item.get("homeTeam") or teams.get("home")) or "TBD"
                away = tn(item.get("away") or item.get("awayTeam") or teams.get("away")) or "TBD"
                e={"sport":sport,"start_utc":start,"home":home,"away":away,
                   "competition":comp or "NCAA","conference":item.get("conference") or "",
                   "venue":item.get("venue") or item.get("location") or "",
                   "status":item.get("status") or "Scheduled","source":name,
                   "source_url":item.get("source_url") or ""}
                e["id"]=event_id(e)
                e["raw_hash"]=hashlib.sha256(json.dumps(item,sort_keys=True).encode()).hexdigest()
                upsert_event(e,0.70)
                count += 1
            set_source(name,True,f"Fetched {count} events")
        except Exception as ex:
            set_source(name,False,str(ex)[:300])
    DB.commit()
    reconcile()

def reconcile():
    rows = DB.execute("""SELECT sport,start_utc,lower(trim(home)) h,lower(trim(away)) a,
                         COUNT(DISTINCT source) n
                         FROM events GROUP BY sport,start_utc,h,a""").fetchall()
    for r in rows:
        conf = min(0.99, 0.55 + 0.20*max(0,r["n"]-1))
        DB.execute("""UPDATE events SET confidence=?
                      WHERE sport=? AND start_utc=? AND lower(trim(home))=? AND lower(trim(away))=?""",
                   (conf,r["sport"],r["start_utc"],r["h"],r["a"]))
    # Remove stale events so postponed/cancelled schedules don't live forever.
    cutoff = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    DB.execute("DELETE FROM events WHERE start_utc < ?", (cutoff,))
    DB.commit()

def refresh_all():
    refresh_espn()
    refresh_custom_sources()

def scheduler():
    # First refresh happens immediately on process start.
    while True:
        try:
            refresh_all()
        except Exception as ex:
            set_source("ENGINE",False,str(ex))
            DB.commit()
        time.sleep(REFRESH_MINUTES*60)

class Handler(BaseHTTPRequestHandler):
    def send_json(self,obj,code=200):
        data=json.dumps(obj,ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store")
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Content-Length",str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?",1)[0]

        if path == "/api/health":
            self.send_json({
                "ok":True, "utc":iso_now(),
                "database":os.path.basename(DB_PATH),
                "events": DB.execute("SELECT COUNT(*) c FROM events").fetchone()["c"]
            })
            return

        if path == "/api/sources":
            rows=DB.execute("SELECT source,ok,message,checked_at FROM source_status ORDER BY source").fetchall()
            self.send_json([dict(r) for r in rows])
            return

        if path == "/api/events":
            now=datetime.now(timezone.utc)
            lo=(now-timedelta(days=1)).isoformat()
            hi=(now+timedelta(days=10)).isoformat()
            rows=DB.execute("""SELECT * FROM events
                               WHERE start_utc>=? AND start_utc<?
                               ORDER BY start_utc""",(lo,hi)).fetchall()
            out=[]
            for r in rows:
                d=dict(r)
                d["color"]=SPORTS.get(d["sport"])
                out.append(d)
            self.send_json(out)
            return

        if path == "/":
            path="/index.html"
        safe=os.path.normpath(path.lstrip("/"))
        if safe.startswith(".."):
            self.send_response(403); self.end_headers(); return
        fp=os.path.join(WEB,safe)
        if not os.path.isfile(fp):
            self.send_response(404); self.end_headers(); return
        if fp.endswith(".html"): typ="text/html; charset=utf-8"
        elif fp.endswith(".css"): typ="text/css; charset=utf-8"
        elif fp.endswith(".js"): typ="application/javascript; charset=utf-8"
        elif fp.endswith(".json"): typ="application/json; charset=utf-8"
        else: typ="application/octet-stream"
        data=open(fp,"rb").read()
        self.send_response(200)
        self.send_header("Content-Type",typ)
        self.send_header("Content-Length",str(len(data)))
        self.end_headers()
        self.wfile.write(data)

if __name__=="__main__":
    port=int(os.environ.get("PORT","10000"))
    threading.Thread(target=scheduler,daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0",port),Handler).serve_forever()
