"""
Reply composition prompt for the LLM.

The LLM's job is ONLY to phrase the advisory in natural language.
It must not invent advice, numbers, or SOP references.
"""

from __future__ import annotations

from typing import Any, Optional

from langchain_groq import ChatGroq
from app import config


def compose_advisory_reply(
    user_question: str,
    primary_title: str,
    primary_severity: str,
    primary_guidance: str,
    primary_verdict: Optional[str],
    secondary_sops: list[dict],
    metric_values: dict[str, Any],
    location_name: str,
    time_window: str,
    window_description: str,
) -> str:
    """
    Use the LLM to compose a natural language advisory reply.

    The LLM receives pre-filled guidance and facts. It must only rephrase
    them in natural language without adding advice or numbers.
    """
    # Build facts table
    facts_lines = []
    for key, value in sorted(metric_values.items()):
        if value is not None and not isinstance(value, bool):
            facts_lines.append(f"  {key}: {value}")
        elif isinstance(value, bool):
            facts_lines.append(f"  {key}: {'yes' if value else 'no'}")

    facts_table = "\n".join(facts_lines) if facts_lines else "  (no data)"

    # Build secondary SOPs text
    secondary_text = ""
    if secondary_sops:
        parts = []
        for s in secondary_sops:
            parts.append(f"- [{s['severity'].upper()}] {s['title']}: {s['guidance'].strip()}")
        secondary_text = "\n\nAdditional advisories:\n" + "\n".join(parts)

    verdict_line = f"\nVerdict: {primary_verdict}" if primary_verdict else ""

    system_prompt = f"""You are writing a weather safety advisory reply. Follow these rules strictly:

1. ONLY restate the guidance provided below. Do NOT add your own advice.
2. ONLY use numbers from the Facts Table below. Do NOT invent or estimate numbers.
3. Do NOT mention SOP IDs like "SOP-001" — the system adds citations automatically.
4. If there is a lead advisory, open with it prominently.
5. Keep the reply short (3-5 sentences max), in plain language.
6. Address the user's specific question directly.
7. State the severity level naturally (e.g., "This is a high-risk situation").

Location: {location_name}
Time window: {window_description}

PRIMARY ADVISORY: [{primary_severity.upper()}] {primary_title}{verdict_line}
Guidance: {primary_guidance.strip()}
{secondary_text}

Facts Table (ONLY these numbers are allowed in your reply):
{facts_table}
"""

    llm = ChatGroq(
        model=config.LLM_MODEL,
        api_key=config.GROQ_API_KEY,
        temperature=0,
        max_retries=3,
    )

    # Retry with backoff for transient API errors
    import time
    for attempt in range(3):
        try:
            response = llm.invoke([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_question},
            ])
            break
        except Exception as exc:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                raise

    return response.content
