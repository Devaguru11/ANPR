from __future__ import annotations
import re
from typing import Any

def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)

def breakdown_prompt(system: str, user: str, catalog: str='', metadata: str='', context: str='') -> dict[str, Any]:
    system_t = estimate_tokens(system)
    user_t = estimate_tokens(user)
    catalog_t = estimate_tokens(catalog)
    metadata_t = estimate_tokens(metadata)
    context_t = estimate_tokens(context)
    semantic_total = system_t + user_t
    return {'system_tokens': system_t, 'user_tokens': user_t, 'catalog_tokens': catalog_t, 'metadata_tokens': metadata_t, 'conversation_context_tokens': context_t, 'semantic_prompt_tokens': semantic_total, 'answer_prompt_tokens': 0, 'schema_tokens': catalog_t, 'conversation_tokens': context_t, 'total_tokens': semantic_total, 'largest_contributor': max([('system', system_t), ('user', user_t), ('catalog', catalog_t), ('metadata', metadata_t), ('conversation_context', context_t)], key=lambda x: x[1])[0]}