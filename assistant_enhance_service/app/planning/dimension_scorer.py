from __future__ import annotations
import re
from dataclasses import dataclass, field
from app.planning.dimension_profiles import DIMENSION_PROFILES, profile_names
from app.planning.dimensions import dimension_names
from app.planning.objectives import ANALYTICAL_OBJECTIVES
_TOKEN_RE = re.compile('[a-z0-9]+')
_SCALAR_OBJECTIVES = frozenset({'metric_summary', 'comparison', 'record_detail'})

@dataclass
class DimensionScoreDetail:
    dimension: str | None
    score: float
    components: dict[str, float] = field(default_factory=dict)

@dataclass
class DimensionSelection:
    dimension: str | None
    confidence: float
    candidates: list[str | None]
    scores: list[DimensionScoreDetail]
    rationale: str

def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))

def _phrase_hits(question: str, phrases: tuple[str, ...]) -> float:
    if not phrases:
        return 0.0
    q = question.lower()
    hits = 0.0
    for phrase in phrases:
        if phrase in q:
            hits += 1.0
            continue
        phrase_tokens = _tokens(phrase)
        if not phrase_tokens:
            continue
        q_tokens = _tokens(q)
        overlap = len(q_tokens & phrase_tokens) / len(phrase_tokens)
        if overlap >= 0.6:
            hits += overlap
    return min(hits, 2.0)

def infer_candidates_from_question(question: str, objective: str) -> list[tuple[str | None, float]]:
    q = question.lower()
    hits: list[tuple[str, float]] = []
    for (name, profile) in DIMENSION_PROFILES.items():
        if objective not in profile.objectives:
            continue
        ex = _phrase_hits(q, profile.examples)
        neg = _phrase_hits(q, profile.negative_examples)
        score = ex - neg * 0.5
        explicit = profile.name.replace('_', ' ')
        if explicit in q:
            score += 0.8
        if name == 'location' and (' area ' in f' {q} ' or ' areas ' in f' {q} '):
            score += 0.5
        if score > 0.35:
            hits.append((name, min(0.78, 0.42 + score * 0.12)))
    hits.sort(key=lambda x: (-x[1], x[0]))
    return [(dim, conf) for (dim, conf) in hits[:4]]

def extract_dimension_candidates(data: dict, prior_dimension: str | None, *, question: str='', objective: str='ranking') -> list[tuple[str | None, float]]:
    out: list[tuple[str | None, float]] = []
    seen: set[str | None] = set()

    def add(dim: str | None, conf: float) -> None:
        if dim is not None and dim not in dimension_names():
            return
        key = dim
        if key in seen:
            return
        seen.add(key)
        out.append((dim, conf))
    raw_candidates = data.get('dimension_candidates') or []
    if isinstance(raw_candidates, list):
        for item in raw_candidates:
            if isinstance(item, str):
                add(None if item in ('null', '') else item, 0.7)
            elif isinstance(item, dict):
                raw = item.get('dimension')
                dim = None if raw in (None, 'null', '') else str(raw)
                conf = float(item.get('confidence', item.get('score', 0.7)))
                add(dim, conf)
    raw_dim = data.get('dimension')
    primary = None if raw_dim in (None, 'null', '') else str(raw_dim)
    if primary in dimension_names():
        add(primary, float(data.get('confidence', 0.75)))
    for alt in data.get('alternatives') or []:
        if alt in dimension_names():
            add(str(alt), 0.55)
    if prior_dimension and prior_dimension in dimension_names():
        add(prior_dimension, 0.45)
    if not out or not any((dim for (dim, _) in out if dim)):
        for (dim, conf) in infer_candidates_from_question(question, objective):
            add(dim, conf)
    if not out:
        add(None, 0.5)
    return out

def score_dimension(question: str, candidates: list[tuple[str | None, float]], *, objective: str, prior_dimension: str | None=None, inherit: bool=False, llm_confidence: float=0.7, llm_dimension: str | None=None) -> DimensionSelection:
    q = question.lower()
    scored: list[DimensionScoreDetail] = []
    for (idx, (dim, llm_rank_conf)) in enumerate(candidates):
        components: dict[str, float] = {}
        if dim is None:
            components['null_prior'] = 0.2 if objective in _SCALAR_OBJECTIVES else 0.0
        else:
            profile = DIMENSION_PROFILES.get(dim)
            if profile:
                ex_hit = _phrase_hits(q, profile.examples)
                neg_hit = _phrase_hits(q, profile.negative_examples)
                components['example_match'] = ex_hit * 0.35
                components['negative_penalty'] = -neg_hit * 0.25
                explicit = profile.name.replace('_', ' ')
                if explicit in q:
                    components['explicit_dimension'] = 0.3
                if dim == 'location' and (' area ' in f' {q} ' or ' areas ' in f' {q} '):
                    components['area_cue'] = 0.22
                if objective in profile.objectives:
                    components['objective_fit'] = 0.12
                elif objective in _SCALAR_OBJECTIVES:
                    components['objective_fit'] = -0.15
        components['llm_rank'] = llm_rank_conf * 0.4
        components['llm_position'] = max(0.0, 1.0 - idx * 0.1) * 0.1
        if dim and dim == llm_dimension:
            components['llm_primary'] = llm_confidence * 0.1
        if inherit and prior_dimension and (dim == prior_dimension):
            components['prior_dimension'] = 0.08
        total = sum(components.values())
        scored.append(DimensionScoreDetail(dimension=dim, score=total, components=components))
    scored.sort(key=lambda s: (-s.score, s.dimension or ''))
    best = scored[0]
    if objective in _SCALAR_OBJECTIVES and best.dimension is not None:
        null_score = next((s.score for s in scored if s.dimension is None), 0.0)
        if null_score + 0.05 >= best.score and (not _phrase_hits(q, _all_examples())):
            best = next((s for s in scored if s.dimension is None))
    if objective == 'trend' and best.dimension is None:
        for fallback in ('date', 'day'):
            detail = next((s for s in scored if s.dimension == fallback), None)
            if detail:
                best = detail
                break
    if objective in {'ranking', 'growth', 'breakdown'} and best.dimension is None:
        for detail in scored:
            if detail.dimension is not None:
                best = detail
                break
    ordered = [s.dimension for s in scored if s.dimension is not None]
    seen: set[str | None] = set()
    unique_candidates: list[str | None] = []
    for dim in ordered:
        if dim in seen:
            continue
        seen.add(dim)
        unique_candidates.append(dim)
    if None not in seen and objective in _SCALAR_OBJECTIVES:
        unique_candidates.append(None)
    confidence = min(0.99, max(0.35, 0.45 + best.score * 0.25))
    rationale = f"selected {best.dimension or 'null'} via scored dimension resolution (score={best.score:.2f}, objective={objective})"
    return DimensionSelection(dimension=best.dimension, confidence=round(confidence, 3), candidates=unique_candidates[:5], scores=scored, rationale=rationale)

def _all_examples() -> tuple[str, ...]:
    phrases: list[str] = []
    for profile in DIMENSION_PROFILES.values():
        phrases.extend(profile.examples)
    return tuple(phrases)

def apply_dimension_selection(data: dict, *, question: str, objective: str, prior_dimension: str | None=None, inherit: bool=False, llm_confidence: float=0.7) -> tuple[str | None, float, list[str | None], dict[str | None, float], str]:
    raw_dim = data.get('dimension')
    llm_dimension = None if raw_dim in (None, 'null', '') else str(raw_dim)
    candidates = extract_dimension_candidates(data, prior_dimension, question=question, objective=objective)
    selection = score_dimension(question, candidates, objective=objective, prior_dimension=prior_dimension, inherit=inherit, llm_confidence=llm_confidence, llm_dimension=llm_dimension)
    score_map = {s.dimension: round(s.score, 3) for s in selection.scores}
    return (selection.dimension, selection.confidence, selection.candidates, score_map, selection.rationale)