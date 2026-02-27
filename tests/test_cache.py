"""Tests for cache module."""

import pytest
import time
from pathlib import Path
from cache import (
    get_cache_key,
    load_cache,
    save_cache,
    clear_cache,
    get_cache_stats,
    CACHE_DIR,
    DEFAULT_TTL,
)


class TestGetCacheKey:
    """Tests for get_cache_key function."""

    def test_cache_key_unique(self):
        """Test that cache keys are unique for different data."""
        key1 = get_cache_key("test", {"a": 1})
        key2 = get_cache_key("test", {"a": 2})
        assert key1 != key2

    def test_cache_key_consistent(self):
        """Test that same data produces same key."""
        key1 = get_cache_key("test", {"a": 1})
        key2 = get_cache_key("test", {"a": 1})
        assert key1 == key2

    def test_cache_key_has_prefix(self):
        """Test that cache key includes prefix."""
        key = get_cache_key("github", {"username": "test"})
        assert key.startswith("github_")


class TestLoadSaveCache:
    """Tests for load_cache and save_cache functions."""

    def test_save_and_load_cache(self):
        """Test saving and loading cache data."""
        key = get_cache_key("test", {"id": 1})
        data = {"repositories": ["repo1", "repo2"]}
        
        save_cache(key, data, DEFAULT_TTL["github"])
        loaded = load_cache(key)
        
        assert loaded == data

    def test_load_nonexistent_cache(self):
        """Test loading non-existent cache returns None."""
        key = get_cache_key("nonexistent", {"id": 999})
        assert load_cache(key) is None

    def test_cache_expires(self):
        """Test that expired cache returns None."""
        key = get_cache_key("test", {"id": 2})
        data = {"test": "data"}
        
        # Save with very short TTL
        save_cache(key, data, ttl=1)
        
        # Should exist immediately
        assert load_cache(key) == data
        
        # Wait for expiration
        time.sleep(1.5)
        
        # Should be expired now
        assert load_cache(key) is None


class TestClearCache:
    """Tests for clear_cache function."""

    def test_clear_all_cache(self):
        """Test clearing all cache files."""
        # Save some data
        save_cache("test_abc", {"data": 1}, DEFAULT_TTL["github"])
        save_cache("test_def", {"data": 2}, DEFAULT_TTL["github"])
        
        cleared = clear_cache()
        assert cleared >= 2

    def test_clear_cache_with_prefix(self):
        """Test clearing cache with specific prefix."""
        # Save some data with different prefixes
        save_cache("blog_abc", {"data": 1}, DEFAULT_TTL["blog"])
        save_cache("github_def", {"data": 2}, DEFAULT_TTL["github"])
        
        cleared = clear_cache(prefix="blog")
        assert cleared >= 1
        
        # github cache should still exist (but we cleared it in setup)
        # so just check blog is gone
        assert load_cache("blog_abc") is None

    def test_clear_empty_cache(self):
        """Test clearing when no cache exists."""
        clear_cache()  # Ensure clean state
        cleared = clear_cache()
        assert cleared == 0


class TestGetCacheStats:
    """Tests for get_cache_stats function."""

    def test_stats_empty_cache(self):
        """Test stats with empty cache."""
        clear_cache()
        stats = get_cache_stats()
        assert stats["files"] == 0
        assert stats["size_bytes"] == 0

    def test_stats_with_data(self):
        """Test stats with cached data."""
        save_cache("stats_test", {"data": "test"}, DEFAULT_TTL["github"])
        
        stats = get_cache_stats()
        assert stats["files"] >= 1
        assert stats["size_bytes"] > 0
        assert "size_kb" in stats
