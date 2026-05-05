"""Apify-based Twitter (X) hashtag scraping integration.

Submodules:
- :mod:`app.integrations.apify_twitter.client`        — Async Apify HTTP client.
- :mod:`app.integrations.apify_twitter.extractor`     — Claude-powered tweet → infraction parser.
- :mod:`app.integrations.apify_twitter.report_builder` — Persist extracted tweets as Reports.
- :mod:`app.integrations.apify_twitter.tasks`         — Celery tasks (beat-scheduled scraper).
"""
