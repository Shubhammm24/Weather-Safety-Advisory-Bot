# Graph Documentation

## Mermaid Diagram

```mermaid
graph TD
    A[parse_intent] -->|off-topic| B[scope_reply]
    A -->|no location| C[ask_location]
    A -->|has location| D[resolve_location]
    D -->|fail| E[honest_failure]
    D -->|success| F[fetch_weather]
    F -->|fail| E
    F -->|success| G[match_sops]
    G -->|no match| H[no_sop_reply]
    G -->|matched| I[compose_reply]
    I --> J[check_grounding]
    J -->|pass| K[END]
    J -->|fail, retry 1| I
    J -->|fail, retry 2| L[template_reply]
    B --> K
    C --> K
    H --> K
    E --> K
    L --> K

    style A fill:#6366f1,stroke:#4f46e5,color:#fff
    style E fill:#f87171,stroke:#dc2626,color:#fff
    style I fill:#34d399,stroke:#059669,color:#fff
    style J fill:#fbbf24,stroke:#d97706,color:#000
    style L fill:#f97316,stroke:#ea580c,color:#fff
    style K fill:#1e1e30,stroke:#6366f1,color:#e8e8f0
```

## Node Descriptions

| Node | Type | Description |
|------|------|-------------|
| parse_intent | LLM | Extracts structured intent (location, activity, groups, time) from user message |
| scope_reply | Fixed text | Replies when question is off-topic (no LLM) |
| ask_location | Fixed text | Asks user for location when none is provided |
| resolve_location | Code | Geocodes the location name via Open-Meteo API |
| fetch_weather | Code | Fetches 3-day forecast from Open-Meteo API |
| match_sops | Code | Computes metrics, evaluates all SOPs, resolves conflicts |
| no_sop_reply | Fixed text | Replies when no SOP matches the conditions |
| compose_reply | LLM | Phrases the advisory in natural language using pre-filled guidance |
| check_grounding | Code | Verifies all numbers in the reply exist in the weather data |
| template_reply | Fixed text | Fallback when grounding fails twice (no LLM) |
| honest_failure | Fixed text | Reports geocoding or weather API failures honestly |
