import json, os, sqlite3, threading, time
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ROOT=os.path.dirname(os.path.dirname(__file__))
DB_PATH=os.getenv("DB_PATH", os.path.join(ROOT,"data","ncaa.db"))
HOST=os.getenv("HOST","0.0.0.0")
PORT=int(os.getenv("PORT","10000"))

SPORTS = {
 "Football":"#f1c40f","Soccer":"#2ecc71","Basketball":"#e67e22",
 "Volleyball":"#8e44ad","Baseball":"#e74c3c","Softball":"#ff69b4",
 "Ice Hockey":"#3498db","Field Hockey":"#8b5a2b",
 "Track & Field":"#5dade2","Swimming & Diving":"#17c0d4"
}

def db():
    c=sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory=sqlite3.Row
    return c

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c=db()
    c.execute("""CREATE TABLE IF NOT EXISTS events(
      id TEXT PRIMARY KEY, sport TEXT, gender TEXT, competition TEXT,
      home TEXT, away TEXT, start_utc TEXT, status TEXT, venue TEXT,
      source_json TEXT, confidence REAL, updated_at TEXT)""")
    c.commit()
    c.close()
    seed_if_empty()

def seed_if_empty():
    c=db()
    if c.execute("SELECT COUNT(*) FROM events").fetchone()[0]==0:
        now=datetime.now(timezone.utc).replace(hour=18,minute=0,second=0,microsecond=0)
        seed=[]
        examples=[
          ("Football","NCAA Football","State University","Central College"),
          ("Soccer","NCAA Women's Soccer","Western University","Eastern College"),
          ("Basketball","NCAA Men's Basketball","North State","South State"),
          ("Volleyball","NCAA Volleyball","Metro University","Coastal College"),
          ("Baseball","NCAA Baseball","Lakeside","River State"),
          ("Softball","NCAA Softball","Pine University","Valley State"),
          ("Ice Hockey","NCAA Ice Hockey","Northern College","Atlantic University"),
          ("Field Hockey","NCAA Field Hockey","Capital College","Harbor State"),
        ]
        for i,(sport,comp,h,a) in enumerate(examples):
            dt=now+timedelta(days=i%5)
            seed.append((f"seed-{i}",sport,"",comp,h,a,dt.isoformat().replace("+00:00","Z"),
                         "Scheduled","TBD",json.dumps(["SEED"]),0.2,datetime.now(timezone.utc).isoformat()))
        c.executemany("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",seed)
        c.commit()
    c.close()

def events_between(start,end, sport=None, q=None):
    c=db()
    rows=c.execute("SELECT * FROM events WHERE start_utc>=? AND start_utc<? ORDER BY start_utc",
                   (start.isoformat().replace("+00:00","Z"),end.isoformat().replace("+00:00","Z"))).fetchall()
    out=[]
    for r in rows:
        if sport and r["sport"]!=sport: continue
        if q:
            hay=" ".join(str(r[k] or "") for k in ["sport","competition","home","away","venue"]).lower()
            if q.lower() not in hay: continue
        d=dict(r); d["sources"]=json.loads(d.pop("source_json") or "[]"); out.append(d)
    c.close()
    return out

class Handler(BaseHTTPRequestHandler):
    def send_json(self,obj,status=200):
        raw=json.dumps(obj,ensure_ascii=False).encode()
        self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        p=urlparse(self.path)
        if p.path=="/api/health":
            self.send_json({"ok":True,"service":"NCAA All Sports","time_utc":datetime.now(timezone.utc).isoformat()}); return
        if p.path=="/api/sports":
            self.send_json(SPORTS); return
        if p.path=="/api/events":
            qs=parse_qs(p.query); days=int(qs.get("days",["9"])[0]); q=qs.get("q",[None])[0]; sport=qs.get("sport",[None])[0]
            now=datetime.now(timezone.utc)
            start=(now-timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
            end=(now+timedelta(days=days+1)).replace(hour=0,minute=0,second=0,microsecond=0)
            self.send_json({"timezone":"UTC","events":events_between(start,end,sport,q)}); return
        if p.path=="/":
            return self.serve("web/index.html","text/html; charset=utf-8")
        if p.path.startswith("/"):
            rel=p.path.lstrip("/")
            if rel.startswith("api/"): return self.send_json({"error":"not_found"},404)
            path=os.path.join(ROOT,rel)
            if os.path.isfile(path):
                typ="text/plain; charset=utf-8"
                if path.endswith(".css"): typ="text/css; charset=utf-8"
                if path.endswith(".js"): typ="application/javascript; charset=utf-8"
                return self.serve(rel,typ)
        self.send_json({"error":"not_found"},404)
    def serve(self,rel,typ):
        path=os.path.join(ROOT,rel)
        try:
            data=open(path,"rb").read()
            self.send_response(200); self.send_header("Content-Type",typ); self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)
        except: self.send_json({"error":"not_found"},404)
    def log_message(self,*args): pass

def run():
    init_db()
    print(f"NCAA server listening on {HOST}:{PORT}")
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()

if __name__=="__main__": run()
