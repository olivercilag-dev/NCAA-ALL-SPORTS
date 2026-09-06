def reconcile(events):
    """Conservative reconciliation: never silently overwrites conflicting source values."""
    grouped={}
    for e in events:
        grouped.setdefault(e["id"],[]).append(e)
    result=[]
    for eid,items in grouped.items():
        base=items[0].copy()
        sources=sorted(set(x["source"] for x in items))
        conflicts={}
        for field in ("start_utc","status","venue","competition"):
            vals=sorted(set(x.get(field,"") for x in items if x.get(field,"")!=""))
            if len(vals)>1: conflicts[field]=vals
        base["sources"]=sources
        base["conflicts"]=conflicts
        base["confidence"]=min(0.99,0.55+0.12*len(sources)-0.10*len(conflicts))
        result.append(base)
    return result
