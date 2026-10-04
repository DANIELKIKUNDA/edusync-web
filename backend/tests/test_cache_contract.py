import pytest

from edusync.adapters.redis_cache import RedisCacheAdapter


def test_cache_requires_explicit_scope_and_namespaces_keys_without_connecting():
    with pytest.raises(ValueError):
        RedisCacheAdapter("redis://localhost", "")
    cache = RedisCacheAdapter("redis://localhost", "school:abc")
    assert cache._key("dashboard:counts") == "edusync:school:abc:dashboard:counts"


def test_cache_refuses_blank_keys():
    cache = RedisCacheAdapter("redis://localhost", "platform")
    with pytest.raises(ValueError):
        cache._key("")
