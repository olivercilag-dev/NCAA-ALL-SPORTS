import os, json, sqlite3, threading, time, hashlib
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.parse import urlparse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

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
    "rowing":"#64748b","golf":"#65a30d","fencing":"#94a3b8","tennis":None
}
# Tennis is deliberately excluded from ingestion and UI.
ALLOWED_SPORTS = {k for k,v in SPORTS.items() if k != "tennis"}

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
        "golf":"golf","fencing":"fencing","tennis":"tennis"
    }
    return aliases.get(s, s)

def parse_time(v):
    if not v: return None
    s = str(v).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        d = datetime.fromisoformat(s)
        if d.tzinfo is None: d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
    except Exception:
        return None

def event_id(e):
    key = "|".join([
        e["sport"], e.get("start_utc","")[:10],
        (e.get("home") or "").lower().strip(),
        (e.get("away") or "").lower().strip()
    ])
    return hashlib.sha256(key.encode()).hexdigest()[:24]

def extract_items(payload):
    if isinstance(payload, list): return payload
    if not isinstance(payload, dict): return []
    for k in ("events","items","games","schedule","data"):
        if isinstance(payload.get(k), list): return payload[k]
    return []

def normalize_item(item, source):
    if not isinstance(item, dict): return None
    comp = item.get("competition") or item.get("league") or item.get("tournament") or {}
    teams = item.get("teams") or {}
    home = item.get("home") or item.get("homeTeam") or teams.get("home") if isinstance(teams,dict) else None
    away = item.get("away") or item.get("awayTeam") or teams.get("away") if isinstance(teams,dict) else None
    def team_name(x):
        if isinstance(x,dict): return x.get("name") or x.get("displayName") or x.get("shortName")
        return x
    sport = normalize_sport(item.get("sport") or item.get("sport_key") or item.get("category"))
    if sport not in ALLOWED_SPORTS: return None
    start = parse_time(item.get("start_utc") or item.get("startTime") or item.get("date") or item.get("start"))
    if not start: return None
    e = {
        "sport":sport, "start_utc":start, "home":team_name(home), "away":team_name(away),
        "competition": (comp.get("name") if isinstance(comp,dict) else comp) or item.get("competitionName"),
        "conference": item.get("conference") or item.get("group") or "",
        "venue": item.get("venue") or item.get("location") or "",
        "status": item.get("status") or "Scheduled",
        "source":source, "source_url":item.get("source_url") or "",
        "confidence":0.0
    }
    e["id"] = event_id(e)
    e["raw_hash"] = hashlib.sha256(json.dumps(item,sort_keys=True).encode()).hexdigest()
    return e

def fetch_json(url, api_key=""):
    p = urlparse(url)
    if p.scheme not in ("http","https"): raise ValueError("Feed URL must use HTTP(S).")
    headers={"User-Agent":"NCAA-All-Sports/1.0"}
    if api_key: headers["Authorization"]="Bearer "+api_key
    req=Request(url, headers=headers)
    with urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))

def ingest_source(name, url, key=""):
    if not url:
        return 0, "Not configured"
    try:
        payload=fetch_json(url,key)
        rows=[]
        for item in extract_items(payload):
            e=normalize_item(item,name)
            if e: rows.append(e)
        now=iso_now()
        for e in rows:
            DB.execute("""INSERT INTO events
            (id,sport,start_utc,home,away,competition,conference,venue,status,source,source_url,confidence,updated_at,raw_hash)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET start_utc=excluded.start_utc,home=excluded.home,away=excluded.away,
            competition=excluded.competition,conference=excluded.conference,venue=excluded.venue,
            status=excluded.status,source=excluded.source,source_url=excluded.source_url,
            updated_at=excluded.updated_at,raw_hash=excluded.raw_hash""",
            (e["id"],e["sport"],e["start_utc"],e["home"],e["away"],e["competition"],e["conference"],
             e["venue"],e["status"],e["source"],e["source_url"],0.5,now,e["raw_hash"]))
        DB.execute("INSERT OR REPLACE INTO source_status VALUES(?,?,?,?)",
                   (name,1,f"Fetched {len(rows)} events",now))
        DB.commit()
        reconcile()
        return len(rows), "OK"
    except Exception as ex:
        DB.execute("INSERT OR REPLACE INTO source_status VALUES(?,?,?,?)",
                   (name,0,str(ex)[:300],iso_now()))
        DB.commit()
        return 0, str(ex)[:300]

def reconcile():
    # Events with the same normalized key are merged conceptually by event_id.
    # Confidence rises when multiple independent configured sources report the same event.
    rows=DB.execute("""SELECT sport,start_utc,lower(trim(home)) h,lower(trim(away)) a,
                       COUNT(DISTINCT source) n
                       FROM events GROUP BY sport,start_utc,h,a""").fetchall()
    for r in rows:
        conf=min(0.99,0.45+0.2*max(0,r["n"]-1))
        DB.execute("""UPDATE events SET confidence=?
                      WHERE sport=? AND start_utc=? AND lower(trim(home))=? AND lower(trim(away))=?""",
                   (conf,r["sport"],r["start_utc"],r["h"],r["a"]))
    DB.commit()

def refresh_all():
    ingest_source("NCAA",os.environ.get("NCAA_SCHEDULE_URL",""),os.environ.get("NCAA_API_KEY",""))
    ingest_source("ESPN",os.environ.get("ESPN_SCHEDULE_URL",""),os.environ.get("ESPN_API_KEY",""))
    ingest_source("Official",os.environ.get("OFFICIAL_SCHEDULE_URL",""),os.environ.get("OFFICIAL_API_KEY",""))

def scheduler():
    while True:
        try: refresh_all()
        except Exception: pass
        time.sleep(REFRESH_MINUTES*60)

class Handler(BaseHTTPRequestHandler):
    def send_json(self,obj,code=200):
        data=json.dumps(obj,ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        if self.path.startswith("/api/health"):
            self.send_json({"ok":True,"utc":iso_now(),"database":os.path.basename(DB_PATH)})
            return
        if self.path.startswith("/api/sources"):
            rows=DB.execute("SELECT source,ok,message,checked_at FROM source_status ORDER BY source").fetchall()
            self.send_json([dict(r) for r in rows]); return
        if self.path.startswith("/api/events"):
            # Keep a practical window around now. UI performs exact date filtering.
            now=datetime.now(timezone.utc); lo=(now-timedelta(days=1)).isoformat(); hi=(now+timedelta(days=10)).isoformat()
            rows=DB.execute("""SELECT * FROM events WHERE start_utc>=? AND start_utc<? ORDER BY start_utc""",(lo,hi)).fetchall()
            out=[]
            for r in rows:
                d=dict(r); d["color"]=SPORTS.get(d["sport"]); out.append(d)
            self.send_json(out); return
        path=self.path.split("?",1)[0]
        if path=="/": path="/index.html"
        safe=os.path.normpath(path.lstrip("/"))
        if safe.startswith(".."): self.send_response(403); self.end_headers(); return
        fp=os.path.join(WEB,safe)
        if not os.path.isfile(fp): self.send_response(404); self.end_headers(); return
        typ="text/html; charset=utf-8" if fp.endswith(".html") else "text/css; charset=utf-8" if fp.endswith(".css") else "application/javascript; charset=utf-8"
        data=open(fp,"rb").read(); self.send_response(200); self.send_header("Content-Type",typ); self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)

if __name__=="__main__":
    # Never bind to a hard-coded or invalid port: Render supplies PORT.
    port=int(os.environ.get("PORT","10000"))
    threading.Thread(target=scheduler,daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0",port),Handler).serve_forever()
