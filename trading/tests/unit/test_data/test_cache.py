import time
from data.cache import TTLCache


class TestTTLCache:
    def test_set_and_get(self):
        cache = TTLCache()
        cache.set("key", "value", ttl_seconds=60)
        assert cache.get("key") == "value"

    def test_missing_key_returns_none(self):
        cache = TTLCache()
        assert cache.get("missing") is None

    def test_expired_entry_returns_none(self):
        cache = TTLCache()
        cache.set("key", "value", ttl_seconds=0)
        time.sleep(0.01)
        assert cache.get("key") is None

    def test_invalidate(self):
        cache = TTLCache()
        cache.set("key", "value", ttl_seconds=60)
        cache.invalidate("key")
        assert cache.get("key") is None

    def test_invalidate_missing_key_no_error(self):
        cache = TTLCache()
        cache.invalidate("missing")  # should not raise

    def test_clear(self):
        cache = TTLCache()
        cache.set("a", 1, ttl_seconds=60)
        cache.set("b", 2, ttl_seconds=60)
        cache.clear()
        assert cache.get("a") is None
        assert cache.get("b") is None

    def test_overwrite(self):
        cache = TTLCache()
        cache.set("key", "old", ttl_seconds=60)
        cache.set("key", "new", ttl_seconds=60)
        assert cache.get("key") == "new"
