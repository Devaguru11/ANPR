from __future__ import annotations
from prometheus_client import Counter, Histogram
REQUESTS = Counter('assistant_ai_requests_total', 'Total requests', ['endpoint'])
LATENCY = Histogram('assistant_ai_request_latency_seconds', 'Request latency', ['endpoint'])