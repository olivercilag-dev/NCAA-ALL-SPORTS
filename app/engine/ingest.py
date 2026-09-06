import json, os, sqlite3
from datetime import datetime, timezone
from providers.generic_json import GenericJSONProvider
from engine.normalizer import normalize
from engine.reconcile import reconcile

ROOT=os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DB=os.getenv("DB_PATH",os.path.join(ROOT,"data","ncaa.db"))

def ingest():
    providers=[]
    configs=[("NCAA_SCHEDULE_URL","NCAA"),("ESPN_SCHEDULE_URL","ESPN"),("OFFICIAL_SCHEDULE_URL","OFFICIAL")]
    for env,name in configs:
        url=os.getenv(env,"").strip()
        if url: providers.append(GenericJSONProvider(name,url,os.getenv(env.replace("_URL","_API_KEY"),"")))
    raw=[]
    for p in providers:
        try:
            for x in p.fetch_events():
                e=normalize(x,p.name)
                if e: raw.append(e)
        except Exception as exc:
            print(f"{p.name} ingest failed: {exc}")
    merged=reconcile(raw)
    if not merged: return 0
    c=sqlite3.connect(DB)
    for e in merged:
        c.execute("""INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(id) DO UPDATE SET sport=excluded.sport,gender=excluded.gender,
          competition=excluded.competition,home=excluded.home,away=excluded.away,
          start_utc=excluded.start_utc,status=excluded.status,venue=excluded.venue,
          source_json=excluded.source_json,confidence=excluded.confidence,updated_at=excluded.updated_at""",
          (e["id"],e["sport"],e["gender"],e["competition"],e["home"],e["away"],e["start_utc"],
           e["status"],e["venue"],json.dumps(e["sources"]),e["confidence"],datetime.now(timezone.utc).isoformat()))
    c.commit(); c.close()
    return len(merged)

if __name__=="__main__": print("Ingested:",ingest())
