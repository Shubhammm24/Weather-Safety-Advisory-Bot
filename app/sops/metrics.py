"""
Weather metrics computation.

Given forecast JSON and a time window, computes all allowed metrics.
Pure Python, no LLM.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional


# Thunderstorm weather codes per WMO standard
THUNDERSTORM_CODES = {95, 96, 99}


def _parse_time(time_str: str) -> datetime:
    """Parse ISO 8601 time string from Open-Meteo."""
    return datetime.fromisoformat(time_str)


def _get_hour_of_day(dt: datetime) -> int:
    """Get hour of day from datetime."""
    return dt.hour


def _resolve_time_window(
    window_name: str,
    hourly_times: list[str],
) -> tuple[list[int], str]:
    """
    Resolve a time window name to indices into the hourly data array.

    Args:
        window_name: One of 'now', 'morning', 'afternoon', 'evening',
                     'night', 'today', 'tomorrow', 'unspecified'.
        hourly_times: List of ISO timestamp strings from the hourly data.

    Returns:
        Tuple of (list of indices, description string).
    """
    if not hourly_times:
        return [], "empty"

    parsed_times = [_parse_time(t) for t in hourly_times]
    now = datetime.now()

    # Determine the "today" date based on the first hourly time
    today_date = parsed_times[0].date()
    tomorrow_date = today_date + timedelta(days=1)

    window_ranges = {
        "morning": (6, 11),
        "afternoon": (12, 16),
        "evening": (17, 20),
        "night": (21, 23),
    }

    indices = []
    description = window_name

    if window_name in ("now", "unspecified"):
        # Current hour + next 2 hours
        current_hour = now.hour
        for i, t in enumerate(parsed_times):
            if t.date() == today_date and current_hour <= t.hour <= current_hour + 2:
                indices.append(i)
        description = f"now ({current_hour}:00-{current_hour + 2}:00)"

    elif window_name == "today":
        current_hour = now.hour
        for i, t in enumerate(parsed_times):
            if t.date() == today_date and t.hour >= current_hour:
                indices.append(i)
        description = f"today ({current_hour}:00-23:00)"

    elif window_name == "tomorrow":
        for i, t in enumerate(parsed_times):
            if t.date() == tomorrow_date and 6 <= t.hour <= 21:
                indices.append(i)
        description = "tomorrow (6:00-21:00)"

    elif window_name in window_ranges:
        start_h, end_h = window_ranges[window_name]
        for i, t in enumerate(parsed_times):
            if t.date() == today_date and start_h <= t.hour <= end_h:
                indices.append(i)
        description = f"{window_name} ({start_h}:00-{end_h}:00)"

    else:
        # Fallback: use all data
        indices = list(range(len(parsed_times)))
        description = f"all available ({len(indices)} hours)"

    return indices, description


def _safe_max(values: list) -> Optional[float]:
    """Max of a list, ignoring None values. Returns None if all are None."""
    filtered = [v for v in values if v is not None]
    return max(filtered) if filtered else None


def _safe_min(values: list) -> Optional[float]:
    """Min of a list, ignoring None values. Returns None if all are None."""
    filtered = [v for v in values if v is not None]
    return min(filtered) if filtered else None


def _safe_sum(values: list) -> Optional[float]:
    """Sum of a list, ignoring None values. Returns None if all are None."""
    filtered = [v for v in values if v is not None]
    return sum(filtered) if filtered else None


def compute_metrics(
    forecast_raw: dict[str, Any],
    time_window: str = "now",
) -> dict[str, Any]:
    """
    Compute all allowed metrics from forecast data for a given time window.

    Args:
        forecast_raw: The 'raw' field from fetch_forecast() result.
        time_window: Time window name from vocabulary.yaml.

    Returns:
        Dict with:
            - metrics: dict of metric_name -> value (None if missing)
            - window_description: human-readable description of the window used
            - hourly_rows_used: list of {time, values} for each hour used
            - daily_data: the daily data used for 24h/72h sums
    """
    hourly = forecast_raw.get("hourly", {})
    daily = forecast_raw.get("daily", {})
    hourly_times = hourly.get("time", [])

    # Resolve time window to indices
    indices, window_desc = _resolve_time_window(time_window, hourly_times)

    # Extract hourly values for the window
    def _extract(field: str) -> list:
        values = hourly.get(field, [])
        return [values[i] if i < len(values) else None for i in indices]

    precip_prob = _extract("precipitation_probability")
    precipitation = _extract("precipitation")
    wind_speed = _extract("wind_speed_10m")
    wind_gusts = _extract("wind_gusts_10m")
    uv_index = _extract("uv_index")
    apparent_temp = _extract("apparent_temperature")
    weather_codes = _extract("weather_code")

    # Compute metrics over the window
    metrics: dict[str, Any] = {}

    metrics["max_precip_prob"] = _safe_max(precip_prob)
    metrics["total_precip"] = _safe_sum(precipitation)
    metrics["max_wind_speed"] = _safe_max(wind_speed)
    metrics["max_wind_gust"] = _safe_max(wind_gusts)
    metrics["max_uv"] = _safe_max(uv_index)
    metrics["min_apparent_temp"] = _safe_min(apparent_temp)
    metrics["max_apparent_temp"] = _safe_max(apparent_temp)

    # Thunderstorm detection
    has_thunderstorm = False
    dominant_code = None
    if weather_codes:
        valid_codes = [c for c in weather_codes if c is not None]
        has_thunderstorm = any(c in THUNDERSTORM_CODES for c in valid_codes)
        # Dominant code = highest WMO code in the window (higher = more severe)
        if valid_codes:
            dominant_code = max(valid_codes)
    metrics["has_thunderstorm"] = has_thunderstorm
    metrics["dominant_weather_code"] = dominant_code

    # Daily sums (use daily data, not hourly)
    daily_precip = daily.get("precipitation_sum", [])
    if daily_precip:
        metrics["precip_sum_24h"] = daily_precip[0] if len(daily_precip) > 0 else None
        metrics["precip_sum_72h"] = (
            sum(v for v in daily_precip[:3] if v is not None)
            if any(v is not None for v in daily_precip[:3])
            else None
        )
    else:
        metrics["precip_sum_24h"] = None
        metrics["precip_sum_72h"] = None

    # Build hourly rows for traceability
    hourly_rows = []
    for i in indices:
        if i < len(hourly_times):
            row = {"time": hourly_times[i]}
            for field in [
                "temperature_2m", "apparent_temperature", "precipitation",
                "precipitation_probability", "wind_speed_10m", "wind_gusts_10m",
                "uv_index", "weather_code",
            ]:
                values = hourly.get(field, [])
                row[field] = values[i] if i < len(values) else None
            hourly_rows.append(row)

    return {
        "metrics": metrics,
        "window_description": window_desc,
        "hourly_rows_used": hourly_rows,
        "daily_data": {
            "precipitation_sum": daily.get("precipitation_sum", []),
            "wind_gusts_10m_max": daily.get("wind_gusts_10m_max", []),
            "uv_index_max": daily.get("uv_index_max", []),
        },
    }
