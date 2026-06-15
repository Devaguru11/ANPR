from __future__ import annotations
import json
import re
from typing import Any
import httpx
from app.config import settings
from app.llm.call_tracker import record_llm_call

class VLLMClient:

    def __init__(self) -> None:
        self.base = settings.vllm_base_url.rstrip('/')
        self.model = settings.vllm_model
        self.timeout = settings.vllm_timeout

    async def chat(self, system: str, user: str, json_mode: bool=False, max_tokens: int=2048) -> str:
        payload: dict[str, Any] = {'model': self.model, 'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}], 'temperature': 0.1, 'max_tokens': max_tokens}
        if json_mode:
            payload['response_format'] = {'type': 'json_object'}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            record_llm_call()
            r = await client.post(f'{self.base}/chat/completions', json=payload)
            r.raise_for_status()
            return r.json()['choices'][0]['message']['content']

    async def chat_json(self, system: str, user: str, max_tokens: int=2048) -> dict[str, Any]:
        text = await self.chat(system, user, json_mode=True, max_tokens=max_tokens)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            m = re.search('\\{[\\s\\S]*\\}', text)
            if m:
                return json.loads(m.group())
            raise

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f'{self.base}/models')
                if r.status_code != 200:
                    return False
                ids = {m.get('id') for m in r.json().get('data', [])}
                return self.model in ids
        except Exception:
            return False