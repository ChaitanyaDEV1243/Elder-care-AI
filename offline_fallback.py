import json
import os
from datetime import datetime


CACHE_FILE = "offline_cache.json"


def save_to_cache(key: str, data: dict):
    """
    Save an API response locally so it can be reused
    when the network/live service is unavailable.
    """

    cache = {}

    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except (json.JSONDecodeError, OSError):
            cache = {}

    cache[key] = {
        "cached_at": datetime.now().isoformat(),
        "data": data
    }

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


def load_from_cache(key: str):
    """
    Retrieve a previously cached response.
    Returns None if no cached response exists.
    """

    if not os.path.exists(CACHE_FILE):
        return None

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    entry = cache.get(key)

    if entry is None:
        return None

    return entry["data"]


def get_with_fallback(
    key: str,
    live_function,
    *args,
    **kwargs
):
    """
    Try the live function first.

    If it succeeds:
        return live data and cache it.

    If it fails:
        return cached data.

    If no cached data exists:
        return an offline error response.
    """

    try:
        live_data = live_function(*args, **kwargs)

        save_to_cache(key, live_data)

        return {
            "source": "live",
            "data": live_data
        }

    except Exception as e:

        cached_data = load_from_cache(key)

        if cached_data is not None:
            return {
                "source": "offline_cache",
                "data": cached_data
            }

        return {
            "source": "offline",
            "data": None,
            "error": str(e)
        }