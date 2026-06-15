from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from app.config import settings

class TurnLogger:

    def __init__(self, engine: str='analytics', log_dir: str | None=None) -> None:
        self.engine = engine
        self.dir = Path(log_dir or settings.analytics_log_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.log = logging.getLogger(f'assistant_{engine}')
        if not self.log.handlers:
            h = logging.StreamHandler()
            h.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
            self.log.addHandler(h)
            self.log.setLevel(logging.INFO)

    def write(self, session_id: str, record: dict[str, Any]) -> None:
        record = {'timestamp': datetime.now(timezone.utc).isoformat(), 'session_id': session_id, **record}
        day = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        safe = ''.join((c if c.isalnum() or c in '-_' else '_' for c in session_id[:48]))
        with open(self.dir / f'{day}.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, default=str, ensure_ascii=False) + '\n')
        with open(self.dir / f'{day}_{safe}.readable.log', 'a', encoding='utf-8') as f:
            f.write(f"\n--- {record['timestamp']} session={session_id} ---\n")
            for (k, v) in record.items():
                if k not in ('timestamp', 'session_id'):
                    f.write(f'{k}: {v}\n')
        self.log.info('session=%s intent=%s rows=%s', session_id, record.get('intent'), record.get('rows'))