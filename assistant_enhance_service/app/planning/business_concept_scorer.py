from __future__ import annotations
import re
from dataclasses import dataclass, field
from app.planning.business_concepts import BUSINESS_CONCEPTS, concept_names, default_concept, get_concept
from app.schema.semantic_catalog import TABLE_DESCRIPTIONS
_TOKEN_RE = re.compile('[a-z0-9]+')

@dataclass
class ConceptScoreDetail:
    concept: str
    score: float
    components: dict[str, float] = field(default_factory=dict)

@dataclass
class ConceptSelection:
    business_concept: str
    confidence: float
    candidates: list[str]
    scores: list[ConceptScoreDetail]
    rationale: str

def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))

def _phrase_hits(question_tokens: set[str], phrases: tuple[str, ...]) -> float:
    if not phrases:
        return 0.0
    hits = 0.0
    for phrase in phrases:
        phrase_tokens = _tokens(phrase)
        if not phrase_tokens:
            continue
        overlap = len(question_tokens & phrase_tokens) / len(phrase_tokens)
        if overlap >= 0.5:
            hits += overlap
    return min(hits, 1.5)

def _table_affinity(concept_id: str, prior_metric: str | None) -> float:
    concept = get_concept(concept_id)
    if prior_metric and concept.metric == prior_metric:
        return 0.1
    return 0.0

def _column_affinity(concept_id: str, context: str) -> float:
    concept = get_concept(concept_id)
    ctx = context.lower()
    score = 0.0
    for col in concept.related_columns:
        if col.lower() in ctx:
            score += 0.03
    for table in concept.primary_tables:
        desc = TABLE_DESCRIPTIONS.get(table, '').lower()
        if desc and any((tok in ctx for tok in _tokens(desc) if len(tok) > 4)):
            score += 0.02
    return min(score, 0.08)

def extract_candidates(data: dict, prior_concept: str | None) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    seen: set[str] = set()
    raw_candidates = data.get('business_candidates') or []
    if isinstance(raw_candidates, list):
        for item in raw_candidates:
            if isinstance(item, str):
                (cid, conf) = (item, 0.7)
            elif isinstance(item, dict):
                cid = str(item.get('concept') or item.get('business_concept') or '')
                conf = float(item.get('confidence', item.get('score', 0.7)))
            else:
                continue
            if cid in concept_names() and cid not in seen:
                out.append((cid, max(0.0, min(1.0, conf))))
                seen.add(cid)
    primary = str(data.get('business_concept') or '')
    if primary in concept_names() and primary not in seen:
        out.insert(0, (primary, float(data.get('confidence', 0.75))))
        seen.add(primary)
    for alt in data.get('alternatives') or []:
        cid = str(alt)
        if cid in concept_names() and cid not in seen:
            out.append((cid, 0.65))
            seen.add(cid)
    if prior_concept and prior_concept in concept_names() and (prior_concept not in seen):
        out.append((prior_concept, 0.55))
    if not out:
        fallback = prior_concept or default_concept()
        out.append((fallback, 0.4))
    return out[:5]

def score_candidates(question: str, candidates: list[tuple[str, float]], *, prior_concept: str | None, prior_metric: str | None, inherit: bool, conversation_context: str, llm_confidence: float) -> ConceptSelection:
    q_tokens = _tokens(question)
    ctx = f'{conversation_context} {question}'
    details: list[ConceptScoreDetail] = []
    for (idx, (cid, llm_rank_conf)) in enumerate(candidates):
        components: dict[str, float] = {}
        components['llm_rank'] = llm_rank_conf * 0.45
        components['llm_position'] = max(0.0, 1.0 - idx * 0.08) * 0.15
        concept = get_concept(cid)
        ex_hit = _phrase_hits(q_tokens, concept.examples)
        neg_hit = _phrase_hits(q_tokens, concept.negative_examples)
        components['ontology_positive'] = ex_hit * 0.18
        components['ontology_negative'] = -neg_hit * 0.12
        if inherit and prior_concept == cid:
            components['prior_concept'] = 0.12
        components['table_metric'] = _table_affinity(cid, prior_metric)
        components['schema_context'] = _column_affinity(cid, ctx)
        if idx == 0:
            components['llm_global_confidence'] = llm_confidence * 0.08
        total = sum(components.values())
        details.append(ConceptScoreDetail(concept=cid, score=round(total, 4), components=components))
    details.sort(key=lambda d: (-d.score, d.concept))
    winner = details[0]
    margin = winner.score - (details[1].score if len(details) > 1 else 0.0)
    rationale_parts = [f'selected={winner.concept}', f'score={winner.score:.3f}', f'margin={margin:.3f}']
    top_components = sorted(winner.components.items(), key=lambda x: -abs(x[1]))[:3]
    rationale_parts.append('drivers=' + ', '.join((f'{k}:{v:+.3f}' for (k, v) in top_components)))
    return ConceptSelection(business_concept=winner.concept, confidence=round(min(0.99, max(0.5, winner.score)), 3), candidates=[d.concept for d in details], scores=details, rationale='; '.join(rationale_parts))