# NCAA All Sports — V5 Render Build

Responsive NCAA all-sports dashboard with one chronological UTC feed.

Included sports:
Football, Soccer, Basketball, Volleyball, Baseball, Softball, Ice Hockey, Field Hockey, Track & Field, Swimming & Diving.

Tennis is intentionally excluded.

## Run locally
Python 3.11+:
```bash
python app/main.py
```
Open http://localhost:10000

## Render
This repository includes `render.yaml`. Create a Render Web Service from the repository and deploy.

Important: the included seed data is only a UI/demo fallback. It is NOT live NCAA data.

## Live data
The provider adapters accept JSON feeds through environment variables. Do not bypass login, CAPTCHA, robots restrictions, rate limits, paywalls, or technical access controls. Only connect sources whose terms/license/permissions allow the intended access and use.

For a real launch, configure authorized/licensed sources and map their fields to:
sport, gender, competition, home, away, start_utc, status, venue.

## Database note
The starter deployment uses SQLite for simplicity. For production durability on Render, use a managed PostgreSQL database and adapt the persistence layer before relying on the service for long-term data retention.

## Launch checklist
1. Push this project to GitHub.
2. Create Render Web Service from the repo.
3. Set environment variables for permitted data providers.
4. Connect persistent PostgreSQL storage for production.
5. Test source terms/permissions, rate limits, attribution and redistribution rights.
6. Run reconciliation tests against overlapping providers.
7. Add a custom domain.
8. Only then switch from seed/demo data to production data.

No provider is claimed to be connected until its credentials/feed are actually configured and tested.
