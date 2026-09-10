# NCAA ALL SPORTS — FINAL WORKING PRESENTATION BUILD

This build is the functional presentation baseline. It preserves the full navigation, schedule feed, Game Center, team/school directory, conference filters, searchable time zones, languages and live ESPN refresh adapter.

## Verified locally
- Bundled verified events: 626
- Bundled schools/teams: 418
- Sports with verified bundled events: Football (32), Volleyball (594)
- `/api/events`: returns 626 events on a fresh database
- `/api/directory`: returns 418 schools/teams
- `/api/event/<id>`: opens event detail and preserves team logos
- Fresh deployment bootstraps from `data/events_snapshot.json`
- Frontend also falls back to `web/events_snapshot.json` if live API is temporarily unavailable

## Render
Build command:
`pip install -r requirements.txt`

Start command:
`python app/server.py`

Do not change the start command.

## Important
The bundled data is a verified presentation snapshot. Live refresh continues to use the configured public provider adapter. Sports without a verified adapter are shown in the UI but are not populated with invented events.
