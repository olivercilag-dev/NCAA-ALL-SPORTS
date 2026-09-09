# NCAA ALL SPORTS — PRO FINAL

This build is the locked professional UI/data-engine build for the current project.

## UI direction
- Cinematic multi-sport athlete hero with the original NCAA ALL SPORTS site identity.
- Futuristic glowing sport selector.
- Clean schedule rows: time, sport, school logos/names, score, status, Game Center.
- Detailed Game Center is the primary destination for deep match information.
- Readable Game Center typography and proportional score treatment.
- Responsive desktop/tablet/mobile layouts.
- Reduced-motion support.

## Filters and school directory
The schedule supports combined date, sport, conference, time range, timezone and search filtering.
The School Directory is populated from the verified event cache and from the public ESPN team-directory endpoints configured for this project. If a provider supplies a direct team URL, it is used; otherwise the interface provides a clearly labelled public search link.

## Data engine reliability
- SQLite schema is created automatically on startup.
- Initial refresh runs in the background so the web server becomes available immediately.
- `/api/health` exposes refresh state and cached event count.
- `/api/directory` exposes school/team directory data.
- `/api/event/<id>` always returns the cached event when it exists; live ESPN summary enrichment is optional and cannot prevent the Game Center from opening.
- The engine never fabricates scores, statistics, school URLs or play-by-play.
- If a provider is unavailable, the UI reports the limitation instead of showing fake data.

## Render
Keep the existing Render start command exactly:

`python app/server.py`

Build command:

`pip install -r requirements.txt`
