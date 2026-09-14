"""Interview HTTP/WS entry points: thin handlers over process/realtime services.

Handlers own transport concerns (auth cookies, rate limits, error mapping)
only; business rules live in ``process`` / ``realtime``. The WS entry
(``ws/``) is the single wire into the realtime handler.
"""
