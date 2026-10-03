"""
Open-Meteo weather client.

Provides geocoding and forecast fetching with proper error handling,
timeouts, caching (10-minute TTL), and retries with exponential backoff.
"""

from __future__ import annotations

import time
import hashlib
import httpx
from datetime import datetime, timezone
from typing import Any

from app import config
from app.weather.errors import LocationNotFound, WeatherUnavailable


# --- In-memory cache with TTL ---
_cache: dict[str, tuple[float, Any]] = {}
_CACHE_TTL = 600  # 10 minutes


def _cache_get(key: str) -> Any | None:
    """Get a value from cache if it exists and hasn't expired."""
    if key in _cache:
        ts, value = _cache[key]
        if time.time() - ts < _CACHE_TTL:
            print(f"[CACHE] Hit for {key[:40]}...")
            return value
        else:
            del _cache[key]
    return None


def _cache_set(key: str, value: Any) -> None:
    """Store a value in cache with current timestamp."""
    _cache[key] = (time.time(), value)


# --- Forecast field configuration ---
# These were verified against the live Open-Meteo API on 2026-10-02.
CURRENT_FIELDS = [
    "temperature_2m",
    "apparent_temperature",
    "precipitation",
    "precipitation_probability",
    "wind_speed_10m",
    "wind_gusts_10m",
    "uv_index",
    "weather_code",
]

HOURLY_FIELDS = CURRENT_FIELDS.copy()

DAILY_FIELDS = [
    "precipitation_sum",
    "wind_gusts_10m_max",
    "uv_index_max",
]


def _make_client() -> httpx.Client:
    """Create an httpx client with configured timeout."""
    return httpx.Client(timeout=config.HTTP_TIMEOUT)


def geocode(name: str) -> dict[str, Any]:
    """
    Geocode a location name using Open-Meteo's geocoding API.

    Args:
        name: Human-readable location name (e.g. "Bhopal").

    Returns:
        Dict with keys: name, country, admin1, latitude, longitude, timezone.

    Raises:
        LocationNotFound: If no results are returned.
        WeatherUnavailable: On network/timeout/non-200 errors.
    """
    cache_key = f"geo:{name.lower().strip()}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    url = config.GEOCODING_BASE_URL
    params = {"name": name, "count": 5, "language": "en", "format": "json"}

    for attempt in range(2):  # one retry
        try:
            with _make_client() as client:
                response = client.get(url, params=params)

            if response.status_code != 200:
                if attempt == 0:
                    continue
                raise WeatherUnavailable(
                    f"Geocoding API returned status {response.status_code}."
                )

            data = response.json()
            results = data.get("results")

            if not results:
                raise LocationNotFound(name)

            # Take the first (most relevant) result
            top = results[0]
            result = {
                "name": top.get("name", name),
                "country": top.get("country", ""),
                "admin1": top.get("admin1", ""),
                "latitude": top["latitude"],
                "longitude": top["longitude"],
                "timezone": top.get("timezone", "auto"),
            }
            _cache_set(cache_key, result)
            return result

        except LocationNotFound:
            raise
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError) as exc:
            if attempt == 0:
                continue
            raise WeatherUnavailable(
                f"Geocoding failed after retry: {type(exc).__name__}: {exc}"
            ) from exc
        except Exception as exc:
            if attempt == 0:
                continue
            raise WeatherUnavailable(
                f"Geocoding unexpected error: {type(exc).__name__}: {exc}"
            ) from exc

    raise WeatherUnavailable("Geocoding failed after all retries.")


def reverse_geocode(latitude: float, longitude: float) -> dict[str, Any]:
    """
    Reverse-geocode coordinates to a location name.

    Uses Open-Meteo's geocoding API by searching for nearby cities
    and picking the closest result.

    Args:
        latitude: Location latitude.
        longitude: Location longitude.

    Returns:
        Dict with keys: name, country, admin1, latitude, longitude, timezone.

    Raises:
        LocationNotFound: If no nearby location can be found.
        WeatherUnavailable: On network/timeout errors.
    """
    # Use Open-Meteo's geocoding with a coordinate-based search
    # We search for the nearest city by using a known nearby name
    # Open-Meteo doesn't have true reverse geocoding, so we use
    # a latitude/longitude-based approach via their API
    url = config.GEOCODING_BASE_URL
    # Search with coordinates by using a generic term and filtering by proximity
    # Actually, Open-Meteo doesn't support reverse geocoding directly.
    # We'll use a simple approach: return coords with a generated name
    # using the forecast API's resolved location data.

    # Use the nominatim-style approach via Open-Meteo's search
    # by querying with lat/lon formatting
    for attempt in range(2):
        try:
            # Use OpenStreetMap Nominatim for reverse geocoding (free, no key needed)
            nominatim_url = "https://nominatim.openstreetmap.org/reverse"
            params = {
                "lat": latitude,
                "lon": longitude,
                "format": "json",
                "zoom": 10,  # city-level
                "addressdetails": 1,
            }
            headers = {
                "User-Agent": "WeatherAdvisoryBot/1.0",
            }

            with _make_client() as client:
                response = client.get(nominatim_url, params=params, headers=headers)

            if response.status_code != 200:
                if attempt == 0:
                    continue
                raise WeatherUnavailable(
                    f"Reverse geocoding API returned status {response.status_code}."
                )

            data = response.json()

            if "error" in data:
                raise LocationNotFound(f"({latitude}, {longitude})")

            address = data.get("address", {})
            # Try to find the best city-level name
            city_name = (
                address.get("city")
                or address.get("town")
                or address.get("village")
                or address.get("municipality")
                or address.get("county")
                or data.get("display_name", "").split(",")[0]
            )

            return {
                "name": city_name,
                "country": address.get("country", ""),
                "admin1": address.get("state", ""),
                "latitude": latitude,
                "longitude": longitude,
                "timezone": "auto",
            }

        except LocationNotFound:
            raise
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError) as exc:
            if attempt == 0:
                continue
            raise WeatherUnavailable(
                f"Reverse geocoding failed after retry: {type(exc).__name__}: {exc}"
            ) from exc
        except Exception as exc:
            if attempt == 0:
                continue
            raise WeatherUnavailable(
                f"Reverse geocoding unexpected error: {type(exc).__name__}: {exc}"
            ) from exc

    raise WeatherUnavailable("Reverse geocoding failed after all retries.")


def fetch_forecast(
    latitude: float, longitude: float, forecast_days: int = 3
) -> dict[str, Any]:
    """
    Fetch weather forecast from Open-Meteo.

    Args:
        latitude: Location latitude.
        longitude: Location longitude.
        forecast_days: Number of days to forecast (default 3).

    Returns:
        Dict with keys:
            - raw: The complete API response JSON.
            - fetched_at: ISO timestamp of when data was fetched.
            - source_url: The URL that was called.
            - location: {latitude, longitude} as resolved by the API.

    Raises:
        WeatherUnavailable: On network/timeout/non-200 errors.
    """
    import time

    url = config.FORECAST_BASE_URL
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": "auto",
        "forecast_days": forecast_days,
        "current": ",".join(CURRENT_FIELDS),
        "hourly": ",".join(HOURLY_FIELDS),
        "daily": ",".join(DAILY_FIELDS),
    }

    # Round coords to 2 decimal places for cache key (same city)
    cache_key = f"forecast:{round(latitude, 2)}:{round(longitude, 2)}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    print(f"[WEATHER] Fetching forecast for ({latitude}, {longitude}), timeout={config.HTTP_TIMEOUT}s")

    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            with _make_client() as client:
                response = client.get(url, params=params)

            print(f"[WEATHER] Attempt {attempt+1}: status={response.status_code}")

            # Handle rate limiting with exponential backoff
            if response.status_code == 429:
                if attempt < max_attempts - 1:
                    wait = 2 ** attempt  # 1s, 2s, 4s, 8s
                    print(f"[WEATHER] Rate limited (429). Waiting {wait}s before retry...")
                    time.sleep(wait)
                    continue
                raise WeatherUnavailable(
                    "Open-Meteo API rate limit exceeded after all retries."
                )

            if response.status_code != 200:
                if attempt < max_attempts - 1:
                    time.sleep(1)
                    continue
                raise WeatherUnavailable(
                    f"Forecast API returned status {response.status_code}."
                )

            data = response.json()

            # Verify expected fields are present
            if "current" not in data or "hourly" not in data or "daily" not in data:
                missing = [k for k in ["current", "hourly", "daily"] if k not in data]
                print(f"[WEATHER] Attempt {attempt+1}: missing fields: {missing}")
                if attempt < max_attempts - 1:
                    time.sleep(1)
                    continue
                raise WeatherUnavailable(
                    "Forecast API response missing expected fields "
                    "(current, hourly, or daily)."
                )

            print(f"[WEATHER] Success: got current, hourly, daily data")
            result = {
                "raw": data,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "source_url": str(response.url),
                "location": {
                    "latitude": data.get("latitude", latitude),
                    "longitude": data.get("longitude", longitude),
                },
            }
            _cache_set(cache_key, result)
            return result

        except WeatherUnavailable:
            raise
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError) as exc:
            print(f"[WEATHER] Attempt {attempt+1} network error: {type(exc).__name__}: {exc}")
            if attempt < max_attempts - 1:
                time.sleep(2 ** attempt)
                continue
            raise WeatherUnavailable(
                f"Forecast fetch failed after retry: {type(exc).__name__}: {exc}"
            ) from exc
        except Exception as exc:
            print(f"[WEATHER] Attempt {attempt+1} unexpected error: {type(exc).__name__}: {exc}")
            if attempt < max_attempts - 1:
                time.sleep(2 ** attempt)
                continue
            raise WeatherUnavailable(
                f"Forecast unexpected error: {type(exc).__name__}: {exc}"
            ) from exc

    raise WeatherUnavailable("Forecast fetch failed after all retries.")
