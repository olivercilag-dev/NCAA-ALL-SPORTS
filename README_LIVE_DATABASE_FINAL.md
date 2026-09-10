# NCAA ALL SPORTS — LIVE DATABASE FINAL

This build is intended as the stable presentation/deployment package.

## Live database behavior
- Ships with a verified 626-event snapshot so a fresh deployment is not an empty screen.
- The snapshot is only a bootstrap cache; the live refresh engine remains authoritative.
- On startup, if the SQLite database has no events, `data/events_snapshot.json` is loaded automatically.
- Every refresh cycle updates the event cache and promotes teams seen in verified events into the school/team master registry.
- The ESPN team-directory layer refreshes configured public team directories and preserves team IDs, names, logos, provider links and conference values when supplied by the provider.
- The scheduler refreshes every 15 minutes by default.
- The frontend renders `/api/events` immediately and loads `/api/directory` in the background, so a slow directory request cannot block the schedule.
- Existing events are updated rather than duplicated through canonical IDs.

## Important scope
The current verified live adapters cover the configured ESPN feeds in `app/server.py`. The UI contains additional NCAA sports, but the site does not fabricate events for sports for which a verified source is not configured.

## Render
Start command must remain:

`python app/server.py`

`DATABASE_PATH` can point to a persistent mounted path if one is available. If the service is restarted without persistent storage, the included snapshot will repopulate the initial cache and the live refresh engine will update it again.
