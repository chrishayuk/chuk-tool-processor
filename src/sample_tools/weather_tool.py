# sample_tools/weather_tool.py
"""
Strict Weather tool — sync core + async façade.

• Uses Nominatim to geocode any free-text location string.
• Calls Open-Meteo for current weather (metric or imperial units).
• Raises on any error so callers can decide how to handle failures.

ValidatedTool *must* expose a synchronous `_execute()` that returns a
plain `dict`; `run()` wraps that in the validated `Result` model.
An optional `arun()` is provided for “await tool(args)” convenience.
"""
from __future__ import annotations

import asyncio
from typing import Dict, Tuple

import httpx
from geopy.geocoders import Nominatim
from chuk_tool_processor.registry.decorators import register_tool
from chuk_tool_processor.models.validated_tool import ValidatedTool

# ─────────────────────────── helpers ────────────────────────────────
_GEOCODER = Nominatim(user_agent="a2a_demo_weather", timeout=5)

_OM_CODE_MAP: dict[int, str] = {
    0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Dense drizzle",
    56: "Freezing drizzle", 57: "Dense freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow",
    95: "Thunderstorm",
}


def _geocode_sync(location: str) -> Tuple[float, float]:
    """Return (lat, lon) for *location* or raise ValueError."""
    geo = _GEOCODER.geocode(location)
    if not geo:
        raise ValueError(f"Cannot geocode {location!r}")
    return geo.latitude, geo.longitude


def _fetch_weather_sync(lat: float, lon: float, units: str) -> Dict:
    """Call Open-Meteo and return canonical keys (blocking)."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": ["temperature_2m", "relative_humidity_2m", "weather_code"],
        "temperature_unit": "fahrenheit" if units == "imperial" else "celsius",
    }
    url = "https://api.open-meteo.com/v1/forecast"
    with httpx.Client(timeout=8) as http:
        rsp = http.get(url, params=params)
        rsp.raise_for_status()
    cur = rsp.json()["current"]
    return {
        "temperature": cur["temperature_2m"],
        "humidity": cur["relative_humidity_2m"],
        "conditions": _OM_CODE_MAP.get(int(cur["weather_code"]),
                                       f"Code {cur['weather_code']}"),
    }


# Async wrappers for concurrency-friendly usage
async def _geocode_async(location: str) -> Tuple[float, float]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _geocode_sync, location)


async def _fetch_weather_async(lat: float, lon: float, units: str) -> Dict:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _fetch_weather_sync, lat, lon, units)


# ─────────────────────────── tool class ─────────────────────────────
@register_tool(name="weather")
class WeatherTool(ValidatedTool):
    """Return live weather data; raises on failure."""

    # ---------- validated schemas ------------------------------------
    class Arguments(ValidatedTool.Arguments):
        location: str
        units: str = "metric"   # "metric" (°C) or "imperial" (°F)

    class Result(ValidatedTool.Result):
        temperature: float
        conditions: str
        humidity: float
        location: str

    # ---------- REQUIRED sync implementation -------------------------
    def _execute(self, *, location: str, units: str) -> Dict:
        lat, lon = _geocode_sync(location)           # may raise
        data = _fetch_weather_sync(lat, lon, units)  # may raise
        data["location"] = location
        return data

    def run(self, **kwargs) -> Dict:
        args = self.Arguments(**kwargs)
        return self.Result(**self._execute(**args.model_dump())).model_dump()

    # ---------- Optional async façade --------------------------------
    async def arun(self, **kwargs) -> Dict:
        args = self.Arguments(**kwargs)
        lat, lon = await _geocode_async(args.location)
        data = await _fetch_weather_async(lat, lon, args.units)
        data["location"] = args.location
        return self.Result(**data).model_dump()
