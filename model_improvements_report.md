# Enhancing the Analytics Assistant: Advanced Context & Accuracy

While the `assistant_enhance_service` handles basic multi-turn memory and pronoun resolution perfectly, scaling it to handle complex human conversation—such as abrupt context switches, high-level vagueness, and nuanced semantic differences—requires specific architectural upgrades.

Below is a detailed report of the cases you highlighted, how they currently behave, and exactly how we can build out the codebase to support them perfectly.

---

## 1. High-Level Context Questions
**The Challenge:** A user asks, *"How is traffic doing today?"* or *"Give me a summary of the situation."* Currently, the `AnalyticalPlanner` expects strict intents like `count` or `ranking` and explicit metrics. It might fail to generate a plan because "how is traffic doing" lacks a concrete database dimension.

**How to Implement the Solution:**
- **Add a `Macro-Summary` Intent:** Update `app/llm/prompts.py` to recognize a `summary` intent. 
- **Multi-Query Orchestration:** When `summary` is detected, the workflow shouldn't just run one SQL query. Instead, we modify `app/workflow/graph.py` to trigger a **parallel execution block** that simultaneously runs:
  1. Total vehicles today
  2. Total violations today
  3. Top 3 active cameras
- **Synthesis Node:** The LLM then takes all three data points and synthesizes a natural language response: *"Traffic is heavy today with 12,000 vehicles detected. We are seeing a spike in speeding violations, particularly at the Chowking camera."*

## 2. Context Switching Conditions
**The Challenge:** The user asks a series of questions:
1. *"Show me speeding violations at AEYE_5."* (Context: `violations`, `AEYE_5`, `speeding`)
2. *"What about no helmet?"* (Replaces `speeding` with `no helmet`. Keeps `AEYE_5`. Perfect.)
3. **Abrupt Switch:** *"How many total vehicles passed through AEYE_1?"* 

Currently, `state_preservation.py` might mistakenly inherit the "no helmet" filter and apply it to the vehicles query, leading to zero results.

**How to Implement the Solution:**
- **Context Boundaries (State TTL):** Introduce a "Context Shift Detector" in `reference_resolver.py`. If the core `business_concept` changes drastically (e.g., from `violations` to `vehicles`), the system should explicitly **drop all prior filters** unless the user uses a conjunction like "of those".
- **Implementation:** Modify the `State` object in Redis to include an `active_topic`. 
```python
# Pseudo-code for state_preservation.py
if new_concept != previous_state.active_topic:
    # Hard context switch detected!
    clear_inherited_filters(except_time_ranges)
```

## 3. Disambiguating "Similar but Different" Questions
**The Challenge:** The user asks:
- Q1: *"How many speeding violations did we get today?"* (Counts total rows in `traffic_violations`)
- Q2: *"How many unique cars got speeding violations today?"* (Counts distinct `vehicle_num` in `traffic_violations`)
If the model maps both to `metric = violations` and `query_mode = count`, they return the exact same answer, which is incorrect.

**How to Implement the Solution:**
- **Sub-Metrics in the Semantic Space:** We need to expand `app/planning/metrics.py`. Instead of just `violations`, we add `unique_violating_vehicles`.
- **Few-Shot Prompting:** The fastest way to fix this is to edit the LLM System Prompt in `app/llm/prompts.py` to explicitly contrast these cases:
```text
Examples of Semantic Nuance:
User: "How many violations?" -> metric: violations
User: "How many unique cars were speeding?" -> metric: unique_violating_vehicles
```
- **SQL Builder Overrides:** Update `sql_builder.py` so that when `metric == unique_violating_vehicles`, it generates `SELECT COUNT(DISTINCT ve.vehicle_num) ...` instead of `COUNT(*)`.

## Summary of Next Steps for Implementation
If you want to add these into the model now, we would execute this in three phases:
1. **Phase 1:** Update the Prompt definitions (`prompts.py`) to include contrasting examples for similar questions and add the new sub-metrics.
2. **Phase 2:** Update `reference_resolver.py` to detect "Context Switches" and safely clear old memory constraints to prevent filter bleeding.
3. **Phase 3:** Update the `AnalyticalPlanner` and `sql_builder.py` to handle high-level "summary" intents by mapping them to multiple parallel SQL queries.
