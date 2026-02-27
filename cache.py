"""
Cache module for fernand0 README generator.

Provides file-based caching with TTL (time-to-live) for API responses.
"""

import hashlib
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default TTL values in seconds
DEFAULT_TTL = {
    "github": 3600,  # 1 hour for GitHub API
    "blog": 1800,  # 30 minutes for RSS feeds
    "mastodon": 1800,  # 30 minutes for Mastodon
}

CACHE_DIR = Path(__file__).parent / ".cache"


def get_cache_key(prefix: str, data: Any) -> str:
    """Generate a unique cache key from input data.

    Args:
        prefix: Key prefix to namespace different cache types.
        data: Data to hash for unique key generation.

    Returns:
        Unique cache key string.
    """
    data_str = json.dumps(data, sort_keys=True, default=str)
    data_hash = hashlib.sha256(data_str.encode()).hexdigest()[:16]
    return f"{prefix}_{data_hash}"


def load_cache(key: str) -> Any | None:
    """Load data from cache if it exists and is not expired.

    Args:
        key: The cache key to load.

    Returns:
        Cached data if valid, None if not found or expired.
    """
    cache_file = CACHE_DIR / f"{key}.json"

    if not cache_file.exists():
        return None

    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            cached = json.load(f)

        # Check if cache is expired
        if "expires_at" in cached and cached["expires_at"] < time.time():
            logger.debug("Cache expired for key: %s", key)
            cache_file.unlink(missing_ok=True)
            return None

        logger.debug("Cache hit for key: %s", key)
        return cached.get("data")

    except (json.JSONDecodeError, IOError) as e:
        logger.warning("Failed to load cache for key %s: %s", key, e)
        return None


def save_cache(key: str, data: Any, ttl: int) -> None:
    """Save data to cache with specified TTL.

    Args:
        key: The cache key.
        data: Data to cache.
        ttl: Time-to-live in seconds.
    """
    # Ensure cache directory exists
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    cache_file = CACHE_DIR / f"{key}.json"

    try:
        cached = {
            "data": data,
            "expires_at": time.time() + ttl,
            "created_at": datetime.now().isoformat(),
        }
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cached, f, indent=2)
        logger.debug("Cache saved for key: %s (TTL: %ds)", key, ttl)

    except IOError as e:
        logger.warning("Failed to save cache for key %s: %s", key, e)


def clear_cache(prefix: str | None = None) -> int:
    """Clear cache files.

    Args:
        prefix: Optional prefix to filter which cache files to clear.
               If None, clears all cache files.

    Returns:
        Number of cache files cleared.
    """
    if not CACHE_DIR.exists():
        return 0

    cleared = 0
    for cache_file in CACHE_DIR.glob("*.json"):
        if prefix is None or cache_file.stem.startswith(prefix):
            cache_file.unlink()
            cleared += 1

    logger.info("Cleared %d cache files", cleared)
    return cleared


def get_cache_stats() -> dict[str, Any]:
    """Get statistics about the cache.

    Returns:
        Dictionary with cache statistics.
    """
    if not CACHE_DIR.exists():
        return {"files": 0, "size_bytes": 0}

    files = list(CACHE_DIR.glob("*.json"))
    total_size = sum(f.stat().st_size for f in files)

    return {
        "files": len(files),
        "size_bytes": total_size,
        "size_kb": round(total_size / 1024, 2),
    }
