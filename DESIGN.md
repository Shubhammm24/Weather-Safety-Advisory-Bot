# Design Document

## Why YAML for SOPs?

SOPs are data, not code. Storing them as YAML files means adding a new policy requires
dropping a file into `sops/`, not modifying any code. This makes policies auditable,
version-controllable, and editable by non-developers.

## Graph Architecture

See [docs/graph.md](docs/graph.md) for the full Mermaid diagram.

The graph has 11 nodes with conditional branching:

1. **parse_intent** (LLM) → routes to scope_reply, ask_location, or resolve_location
2. **resolve_location** (code) → routes to honest_failure or fetch_weather
3. **fetch_weather** (code) → routes to honest_failure or match_sops
4. **match_sops** (code) → routes to no_sop_reply or compose_reply
5. **compose_reply** (LLM) → check_grounding
6. **check_grounding** (code) → END, retry compose, or template_reply

Terminal nodes: scope_reply, ask_location, no_sop_reply, honest_failure, template_reply.

## What is Code vs What is LLM

| Step | LLM | Code | Why |
|------|-----|------|-----|
| Intent extraction | ✓ | | Natural language understanding requires an LLM |
| Location geocoding | | ✓ | Deterministic API call |
| Weather fetching | | ✓ | Deterministic API call |
| Metric computation | | ✓ | Math on weather data; must be exact |
| SOP matching | | ✓ | Threshold/rubric evaluation; deterministic |
| Conflict resolution | | ✓ | Sort-based; must be predictable |
| Reply composition | ✓ | | Natural language generation |
| Number grounding | | ✓ | Regex extraction + set membership check |
| Citation | | ✓ | Must never be written by the LLM |

**Rationale**: The LLM is only used where natural language understanding or generation
is needed. All decisions, numbers, and citations are handled by deterministic code,
making the system auditable and preventing hallucination.

## Number Grounding Enforcement

File: `app/compose/grounding.py`, function: `check_grounding()`

1. Extracts all numbers from the LLM's draft reply using regex.
2. Builds an "allowed set" from: metric values (rounded to 0 and 1 decimal),
   SOP threshold values, user-typed numbers, and common contextual numbers (hours).
3. Rejects any number not in the allowed set.
4. Also rejects any SOP ID patterns (e.g., "SOP-001") in the text.
5. On failure: retries compose once. On second failure: falls back to template_reply.

## Conflict Resolution Rule

File: `app/sops/resolve.py`, function: `resolve_conflicts()`

1. Any SOP marked `lead: true` goes first (e.g., heavy rain SOP-001).
2. Remaining SOPs are sorted by severity rank descending, then by ID for stable ordering.
3. Primary SOP = first in the list. Secondary = next up to 2.
4. Info-level "all clear" SOPs are dropped if any higher-severity SOP also matched.

## How the Fuzzy Picnic SOP Works

File: `sops/006_picnic_rubric.yaml`

Instead of a single threshold, the picnic SOP uses a **rubric**:
- Each weather criterion (rain probability, temperature, wind, UV, thunderstorm) has
  an "if X then Y points" rule.
- Points are summed and mapped to a band: Excellent (7-8), Fair (5-6), Poor (3-4),
  Unsuitable (0-2).
- Each band has its own guidance text.
- This captures the multi-factor nature of "is it a good day for a picnic?" without
  forcing it into a single threshold.

## Honest Gaps

1. **Rain-system detection is a rainfall-total proxy**, not real IMD alerts. Open-Meteo
   provides forecast numbers, not official weather warnings. The SOP uses IMD's heavy
   rainfall classification (≥64.5 mm/24h) applied to forecasted totals, which is an
   approximation of what an actual "heavy rain system" alert would cover.

2. **Adding an 11th SOP**: If the new SOP uses existing metrics and activities, it
   requires only a YAML file in `sops/`. If it needs a new activity, add it to
   `config/vocabulary.yaml`. If it needs a new metric, add computation logic in
   `app/sops/metrics.py` and add the metric name to `ALLOWED_METRICS` in
   `app/sops/schema.py`.

3. **Geocoding takes the first result**. Same-name towns (e.g., "Springfield") may
   resolve to the wrong location. The API provides the resolved coordinates, but
   there's no disambiguation UI.

4. **Intent extraction can misclassify**. Colloquial phrases, multilingual input,
   or ambiguous wording can lead to wrong activity classification. The eval suite
   documents known misclassifications.

## Live Weather Volatility

Some eval cases depend on current weather conditions (e.g., E5 "live Bhopal cycling").
If today's weather is calm, the severe path won't trigger, so those tests record
"inconclusive" rather than a false pass. The replay fixtures (E5b) ensure the severe
path is tested every run regardless of live conditions.
