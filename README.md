# NCAA ALL SPORTS — FINAL BUILD

This is the single final deployment package. It is designed for the Render Web Service used by the project.

## Included
- Responsive phone + PC web app
- One chronological feed
- UTC display
- Yesterday / Today / Tomorrow / Next 7 Days
- Baseball included
- Tennis completely excluded
- Sport-specific colors
- Search and sport filter
- Event detail modal
- 10 languages: Serbian, English, Spanish, French, German, Italian, Portuguese, Dutch, Turkish, Japanese
- Language preference saved in browser
- SQLite storage
- Automatic refresh scheduler
- Source status endpoint
- Multi-source normalization and confidence scoring
- Render-safe `PORT` handling

## IMPORTANT: real data
The application does NOT invent NCAA games. `data/seed.json` is empty.

Real events appear after you configure permitted public/licensed feeds in Render Environment Variables:
- NCAA_SCHEDULE_URL
- ESPN_SCHEDULE_URL
- OFFICIAL_SCHEDULE_URL
and, if required, their API keys.

The JSON adapter accepts common shapes such as:
`{"events":[...]}`, `{"items":[...]}`, `{"games":[...]}` or a top-level list.

Do not bypass login, CAPTCHA, paywalls, robots restrictions, anti-bot controls, or contractual/API restrictions. Do not redistribute data unless the source terms allow it.

## Render
The included `render.yaml` uses:
`python app/server.py`

Render supplies the PORT environment variable. The server binds to `0.0.0.0:$PORT`, avoiding the invalid-port problem from the earlier deployment.

If the GitHub repository is already connected:
1. Replace the repository contents with this package.
2. Commit the changes to `main`.
3. In Render open the existing service.
4. Trigger **Manual Deploy → Deploy latest commit**.
5. Add allowed feed URLs/API keys under **Environment** when available.

## Final-launch reality
The software can be deployed now, but the public production dataset is only complete after the permitted live data feeds are configured and tested. The app intentionally shows no fabricated games while those feeds are absent.

## API
- `/api/health`
- `/api/events`
- `/api/sources`
