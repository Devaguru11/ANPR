from __future__ import annotations
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
ROOT = Path(__file__).resolve().parents[1]

class Settings(BaseSettings):
    ai_service_host: str = '127.0.0.1'
    ai_service_port: int = 9001
    ai_service_api_key: str = 'change-me-internal-key'
    vllm_base_url: str = 'http://127.0.0.1:8000/v1'
    vllm_model: str = 'Qwen/Qwen2.5-7B-Instruct-AWQ'
    vllm_model_path: str = ''
    vllm_timeout: int = 45
    db_host: str = '127.0.0.1'
    db_port: int = 3306
    db_user: str = 'analytics_ai'
    db_password: str = ''
    db_name: str = 'aiserver'
    redis_url: str = 'redis://127.0.0.1:6379/0'
    redis_memory_ttl: int = 86400
    redis_max_turns: int = 20
    analytics_redis_namespace: str = 'assistant_enhance:session'
    legacy_redis_namespace: str = 'assistant:session'
    legacy_engine_url: str = 'http://127.0.0.1:9002'
    legacy_engine_timeout: int = 60
    sql_max_rows: int = 10000
    sql_timeout_seconds: int = 30
    node_server_url: str = 'http://127.0.0.1:4001'
    internal_api_key: str = 'anpr-internal-service-key'
    entity_cache_refresh_seconds: int = 300
    semantic_context_max_chars: int = 400
    semantic_cache_enabled: bool = True
    log_dir: str = str(ROOT / 'logs' / 'assistant_ai')
    analytics_log_dir: str = str(ROOT / 'logs' / 'assistant_enhance')
    legacy_log_dir: str = str(ROOT / 'logs' / 'assistant')
    model_config = SettingsConfigDict(env_file=str(ROOT / '.env'), extra='ignore')
settings = Settings()
for attr in ('log_dir', 'analytics_log_dir', 'legacy_log_dir'):
    val = getattr(settings, attr)
    if not Path(val).is_absolute():
        setattr(settings, attr, str(ROOT / val))