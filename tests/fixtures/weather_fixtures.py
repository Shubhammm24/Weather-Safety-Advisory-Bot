"""
Test fixtures: hand-made forecast JSON for deterministic testing.

Each fixture represents a specific weather scenario.
No network calls in these tests.
"""

import json
from pathlib import Path


def _base_forecast(
    current_overrides: dict = None,
    hourly_overrides: dict = None,
    daily_overrides: dict = None,
) -> dict:
    """Build a base forecast structure with optional overrides."""
    hours = 72  # 3 days
    base_times = [f"2026-10-02T{h:02d}:00" for h in range(24)]
    base_times += [f"2026-10-03T{h:02d}:00" for h in range(24)]
    base_times += [f"2026-10-04T{h:02d}:00" for h in range(24)]

    # Defaults: calm weather
    hourly_defaults = {
        "time": base_times,
        "temperature_2m": [25.0] * hours,
        "apparent_temperature": [26.0] * hours,
        "precipitation": [0.0] * hours,
        "precipitation_probability": [0] * hours,
        "wind_speed_10m": [5.0] * hours,
        "wind_gusts_10m": [10.0] * hours,
        "uv_index": [3.0] * hours,
        "weather_code": [0] * hours,
    }

    daily_defaults = {
        "time": ["2026-10-02", "2026-10-03", "2026-10-04"],
        "precipitation_sum": [0.0, 0.0, 0.0],
        "wind_gusts_10m_max": [15.0, 15.0, 15.0],
        "uv_index_max": [5.0, 5.0, 5.0],
    }

    current_defaults = {
        "time": "2026-10-02T10:00",
        "interval": 900,
        "temperature_2m": 25.0,
        "apparent_temperature": 26.0,
        "precipitation": 0.0,
        "precipitation_probability": 0,
        "wind_speed_10m": 5.0,
        "wind_gusts_10m": 10.0,
        "uv_index": 3.0,
        "weather_code": 0,
    }

    if current_overrides:
        current_defaults.update(current_overrides)
    if hourly_overrides:
        hourly_defaults.update(hourly_overrides)
    if daily_overrides:
        daily_defaults.update(daily_overrides)

    return {
        "latitude": 23.23,
        "longitude": 77.40,
        "timezone": "Asia/Kolkata",
        "timezone_abbreviation": "GMT+5:30",
        "current": current_defaults,
        "current_units": {
            "temperature_2m": "°C",
            "apparent_temperature": "°C",
            "precipitation": "mm",
            "precipitation_probability": "%",
            "wind_speed_10m": "km/h",
            "wind_gusts_10m": "km/h",
            "uv_index": "",
            "weather_code": "wmo code",
        },
        "hourly": hourly_defaults,
        "hourly_units": {
            "temperature_2m": "°C",
            "apparent_temperature": "°C",
            "precipitation": "mm",
            "precipitation_probability": "%",
            "wind_speed_10m": "km/h",
            "wind_gusts_10m": "km/h",
            "uv_index": "",
            "weather_code": "wmo code",
        },
        "daily": daily_defaults,
        "daily_units": {
            "precipitation_sum": "mm",
            "wind_gusts_10m_max": "km/h",
            "uv_index_max": "",
        },
    }


def calm_day() -> dict:
    """Calm day: low wind, no rain, moderate UV, comfortable temperature."""
    return _base_forecast()


def high_wind() -> dict:
    """High wind scenario: gusts above 55 km/h."""
    hours = 72
    return _base_forecast(
        hourly_overrides={
            "wind_speed_10m": [45.0] * hours,
            "wind_gusts_10m": [60.0] * hours,
        },
        daily_overrides={
            "wind_gusts_10m_max": [60.0, 55.0, 50.0],
        },
    )


def high_uv_noon() -> dict:
    """High UV at noon: UV index above 8 during 11-16 hours."""
    hours = 72
    uv = [1.0] * hours
    # Set UV high during 11-16 on first day
    for h in range(11, 17):
        uv[h] = 9.5
    return _base_forecast(
        hourly_overrides={
            "uv_index": uv,
        },
        daily_overrides={
            "uv_index_max": [9.5, 5.0, 5.0],
        },
    )


def heavy_multiday_rain() -> dict:
    """Heavy multi-day rain: >64.5mm in 24h, >130mm in 72h."""
    hours = 72
    precip = [3.0] * hours  # 3mm/hour = 72mm/day
    precip_prob = [90] * hours
    return _base_forecast(
        hourly_overrides={
            "precipitation": precip,
            "precipitation_probability": precip_prob,
        },
        daily_overrides={
            "precipitation_sum": [72.0, 72.0, 72.0],  # 72mm/day
        },
    )


def thunderstorm() -> dict:
    """Thunderstorm scenario: weather codes 95-96."""
    hours = 72
    weather_codes = [0] * hours
    # Thunderstorms in afternoon (12-16) on first day
    for h in range(12, 17):
        weather_codes[h] = 95
    return _base_forecast(
        hourly_overrides={
            "weather_code": weather_codes,
            "precipitation": [5.0 if 12 <= i < 17 else 0.0 for i in range(hours)],
            "precipitation_probability": [80 if 12 <= i < 17 else 10 for i in range(hours)],
        },
    )


def missing_uv() -> dict:
    """UV data is null/missing for some hours."""
    hours = 72
    uv = [None] * 24 + [5.0] * 48  # First day UV is missing
    return _base_forecast(
        hourly_overrides={
            "uv_index": uv,
        },
    )


def extreme_heat() -> dict:
    """Extreme heat: apparent temperature above 42°C."""
    hours = 72
    apparent = [32.0] * hours
    # Peak heat during 11-16
    for h in range(11, 17):
        apparent[h] = 43.0
    for h in range(24 + 11, 24 + 17):
        apparent[h] = 42.0
    return _base_forecast(
        hourly_overrides={
            "apparent_temperature": apparent,
            "temperature_2m": [t - 3 for t in apparent],
        },
    )


def high_wind_and_uv() -> dict:
    """Combined high wind and high UV: tests conflict resolution."""
    hours = 72
    uv = [1.0] * hours
    for h in range(11, 17):
        uv[h] = 9.0

    return _base_forecast(
        hourly_overrides={
            "wind_speed_10m": [42.0] * hours,
            "wind_gusts_10m": [55.0] * hours,
            "uv_index": uv,
        },
        daily_overrides={
            "wind_gusts_10m_max": [55.0, 50.0, 45.0],
            "uv_index_max": [9.0, 5.0, 5.0],
        },
    )
