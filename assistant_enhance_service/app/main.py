from __future__ import annotations
from contextlib import asynccontextmanager
from typing import Any
from fastapi import Depends, FastAPI
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response
from app.analytics.engine import AnalyticsEngine
from app.config import settings
from app.db.pool import Database
from app.engines.analytics import router as analytics_router
from app.engines.auth import verify_key
from app.engines.compat import compat_router
from app.engines.analytics import router as analytics_router
from app.engines.compat import compat_router
from app.entity.cache import EntityDiscovery
from app.llm.vllm_client import VLLMClient
from app.logging.logger import TurnLogger
from app.memory.redis_memory import RedisMemory
from app.metrics.collector import MetricsCollector
from app.metrics.http_metrics import LATENCY, REQUESTS
from app.schema.discovery import SchemaDiscovery
from app.planning.business_concept_catalog import BusinessConceptCatalog
from app.planning.semantic_cache import SemanticResolutionCache
from app.schema.semantic_catalog import SchemaSemanticCatalog
from app.sql.validator import SQLValidator
from app.workflow.graph import AnalyticsWorkflow, Services

@asynccontextmanager
async def lifespan(app: FastAPI):
    db = Database()
    discovery = SchemaDiscovery(db)
    schema = discovery.discover(settings.db_name)
    schema_semantic = SchemaSemanticCatalog(schema, db)
    schema_semantic.refresh_samples()
    concept_catalog = BusinessConceptCatalog(schema_semantic)
    semantic_cache = SemanticResolutionCache()
    llm = VLLMClient()
    memory = RedisMemory(namespace=settings.analytics_redis_namespace)
    entities = EntityDiscovery(db, settings.entity_cache_refresh_seconds)
    validator = SQLValidator(schema, settings.sql_max_rows)
    analytics = AnalyticsEngine()
    logger = TurnLogger(engine='analytics', log_dir=settings.analytics_log_dir)
    metrics = MetricsCollector()
    workflow = AnalyticsWorkflow(Services(db, schema, schema_semantic, concept_catalog, semantic_cache, llm, memory, entities, validator, analytics, logger, metrics))
    app.state.workflow = workflow
    app.state.llm = llm
    app.state.db = db
    app.state.memory = memory
    app.state.metrics = metrics
    app.state.schema_tables = len(schema.tables)
    yield
app = FastAPI(title='Unified Assistant Service', lifespan=lifespan)
app.include_router(analytics_router, prefix='/assistant_enhance')
app.include_router(compat_router)

@app.get('/health')
async def health() -> dict[str, Any]:
    llm_ok = await app.state.llm.health()
    redis_ok = True
    try:
        app.state.memory.client.ping()
    except Exception:
        redis_ok = False
    db_ok = True
    try:
        app.state.db.query_all('SELECT 1')
    except Exception:
        db_ok = False
    return {'status': 'ok' if llm_ok and redis_ok and db_ok else 'degraded', 'service': 'assistant_enhance', 'engines': ['analytics'], 'llm': llm_ok, 'redis': redis_ok, 'database': db_ok, 'schema_tables': app.state.schema_tables, 'bind': f'{settings.ai_service_host}:{settings.ai_service_port}', 'analytics_redis_namespace': settings.analytics_redis_namespace}

@app.get('/metrics')
async def metrics() -> Response:
    body = generate_latest()
    custom = app.state.metrics.snapshot()
    body += f'\n# assistant_ai_custom {custom}\n'.encode()
    return Response(content=body, media_type=CONTENT_TYPE_LATEST)