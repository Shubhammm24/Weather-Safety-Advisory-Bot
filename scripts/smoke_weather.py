"""
Smoke test for the weather client.

Usage: python -m scripts.smoke_weather
Run from the project root (weather-advisor/).
"""

import sys
import os

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.weather.client import geocode, fetch_forecast
from app.weather.errors import LocationNotFound, WeatherUnavailable


def main():
    print("=" * 60)
    print("Weather Client Smoke Test")
    print("=" * 60)

    # --- Test 1: Geocode Bhopal ---
    print("\n[1] Geocoding 'Bhopal'...")
    try:
        location = geocode("Bhopal")
        print(f"  Name:      {location['name']}")
        print(f"  Country:   {location['country']}")
        print(f"  Admin1:    {location['admin1']}")
        print(f"  Latitude:  {location['latitude']}")
        print(f"  Longitude: {location['longitude']}")
        print(f"  Timezone:  {location['timezone']}")
    except Exception as exc:
        print(f"  FAILED: {exc}")
        return

    # --- Test 2: Fetch Forecast ---
    print(f"\n[2] Fetching forecast for ({location['latitude']}, {location['longitude']})...")
    try:
        forecast = fetch_forecast(location["latitude"], location["longitude"])
        raw = forecast["raw"]
        current = raw["current"]

        print(f"  Fetched at:     {forecast['fetched_at']}")
        print(f"  Resolved lat:   {forecast['location']['latitude']}")
        print(f"  Resolved lon:   {forecast['location']['longitude']}")
        print(f"\n  Current conditions:")
        print(f"    Temperature:      {current['temperature_2m']} {raw['current_units']['temperature_2m']}")
        print(f"    Feels like:       {current['apparent_temperature']} {raw['current_units']['apparent_temperature']}")
        print(f"    Precipitation:    {current['precipitation']} {raw['current_units']['precipitation']}")
        print(f"    Precip prob:      {current['precipitation_probability']}{raw['current_units']['precipitation_probability']}")
        print(f"    Wind speed:       {current['wind_speed_10m']} {raw['current_units']['wind_speed_10m']}")
        print(f"    Wind gusts:       {current['wind_gusts_10m']} {raw['current_units']['wind_gusts_10m']}")
        print(f"    UV index:         {current['uv_index']}")
        print(f"    Weather code:     {current['weather_code']}")

        # Print next 24h of hourly precipitation
        hourly = raw["hourly"]
        print(f"\n  Next 24h hourly precipitation:")
        times = hourly["time"][:24]
        precip = hourly["precipitation"][:24]
        precip_prob = hourly["precipitation_probability"][:24]
        for t, p, pp in zip(times, precip, precip_prob):
            bar = "█" * int(p * 5) if p > 0 else "·"
            print(f"    {t}  {p:5.1f} mm  ({pp:3d}%)  {bar}")

    except Exception as exc:
        print(f"  FAILED: {exc}")
        return

    # --- Test 3: Nonsense city ---
    print(f"\n[3] Geocoding nonsense city 'Qwxyzzzz'...")
    try:
        geocode("Qwxyzzzz")
        print("  UNEXPECTED: Got a result (should have raised LocationNotFound)")
    except LocationNotFound as exc:
        print(f"  Correctly raised LocationNotFound: {exc.message}")
    except Exception as exc:
        print(f"  UNEXPECTED ERROR: {type(exc).__name__}: {exc}")

    print("\n" + "=" * 60)
    print("Smoke test complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
