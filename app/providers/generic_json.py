import json, os, urllib.request
from .base import Provider

class GenericJSONProvider(Provider):
    """Use only with a source/feed you are authorized to access and redistribute."""
    def __init__(self,name,url,api_key=None):
        self.name=name; self.url=url; self.api_key=api_key
    def fetch_events(self):
        if not self.url: return []
        req=urllib.request.Request(self.url,headers={"User-Agent":"NCAA-All-Sports/1.0"})
        if self.api_key: req.add_header("Authorization",f"Bearer {self.api_key}")
        with urllib.request.urlopen(req,timeout=20) as r:
            data=json.load(r)
        return data if isinstance(data,list) else data.get("events",[])
