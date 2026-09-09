# Data / Compliance Rules

1. Use only public, licensed, or otherwise authorized data feeds.
2. Respect each provider's Terms of Service, API limits, robots rules and redistribution rights.
3. Never bypass authentication, CAPTCHA, paywalls, anti-bot systems or technical access controls.
4. Store only fields permitted by the source license/terms.
5. If a provider does not permit caching or redistribution, do not ingest it into this public site.
6. Prefer official NCAA/conference/college feeds where public and permitted; use secondary providers only when their terms permit the intended use.
7. The application does not claim NCAA, ESPN, a conference, or a college endorsement.
8. Source attribution should be displayed where required.
9. Conflicting reports are treated as discrepancies rather than silently fabricated values.
10. Tennis is intentionally excluded.
11. The application deletes legacy `SEED` events at startup so placeholder data cannot be served as live data.

## Official school link policy
The application may display official URLs supplied by a verified public/authorized source. If no verified URL is available, the UI may offer a normal user-clicked web search for the school's official athletics site or schedule. It does not scrape search-engine result pages, bypass robots/access controls, or fabricate a school URL. Any future source added to `data/official_sources.json` must be public/authorized and permitted for this use.

## Time zones
UTC is the default/primary display. Users may select an IANA time zone supported by their browser. Source timestamps remain normalized to UTC; time-zone conversion is performed in the browser for display only.
