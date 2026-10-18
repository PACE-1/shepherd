"""Weather forecast and the rider's location for planned outdoor sessions (#117). See weather.py for the privacy rules."""
from fastapi import APIRouter, HTTPException

import api_models
import weather

router = APIRouter()


def _path():
    from profile_manager import ProfileManager
    return ProfileManager.get().active_dir / weather.LOCATION_FILE


def _location(place):
    return {"has_location": place is not None, "place": place, "network_enabled": not weather.net_disabled()}


@router.get("/api/weather/location", responses={200: {"model": api_models.WeatherLocation}})
def weather_location():
    return _location(weather.read_location(_path()))


@router.put("/api/weather/location", responses={200: {"model": api_models.WeatherLocation}})
def weather_location_set(body: dict):
    """Stores the chosen place in the profile folder, coordinates rounded to 2 decimals."""
    try:
        place = weather.write_location(_path(), body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except OSError:
        raise HTTPException(status_code=409, detail="The location could not be saved")
    return _location(place)


@router.delete("/api/weather/location", responses={200: {"model": api_models.WeatherLocation}})
def weather_location_clear():
    """No location: the forecast simply stays off."""
    weather.clear_location(_path())
    return _location(None)


@router.get("/api/weather/search", responses={200: {"model": api_models.WeatherSearch}})
def weather_search(q: str = ""):
    """Place-name search through Open-Meteo's geocoder. The typed text is sent there and is not logged."""
    try:
        return {"available": True, "results": weather.search_places(q)}
    except weather.WeatherUnavailable:
        return {"available": False, "results": [],
                "message": "Place search is unavailable right now (no network, or network use is switched off). "
                           "You can continue without a location and add one later in Settings."}


@router.get("/api/weather/forecast", responses={200: {"model": api_models.WeatherForecast}})
def weather_forecast():
    """Rated days for the next week at the saved location. Never an error: it degrades to a status."""
    out = {"attribution": weather.ATTRIBUTION}
    place = weather.read_location(_path())
    if place is None:
        return {**out, "status": "no_location", "days": []}
    try:
        days = weather.daily(weather.get_hours(place["latitude"], place["longitude"]))
    except weather.WeatherUnavailable:
        return {**out, "status": "unavailable", "days": [], "message": "Forecast unavailable"}
    return {**out, "status": "ok", "days": days}
