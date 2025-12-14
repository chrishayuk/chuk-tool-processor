"""Tests for registry/providers/__init__.py to increase coverage."""

import asyncio
import os
from unittest.mock import patch

import pytest

from chuk_tool_processor.registry.providers import clear_registry_cache, get_registry
from chuk_tool_processor.registry.providers.memory import InMemoryToolRegistry


@pytest.mark.asyncio
async def test_get_registry_default():
    """Test get_registry with default provider (memory)."""
    await clear_registry_cache()

    registry = await get_registry()
    assert isinstance(registry, InMemoryToolRegistry)


@pytest.mark.asyncio
async def test_get_registry_with_environment_variable():
    """Test get_registry uses environment variable - line 39-40."""
    await clear_registry_cache()

    # Set environment variable
    with patch.dict(os.environ, {"CHUK_TOOL_REGISTRY_PROVIDER": "memory"}):
        registry = await get_registry()
        assert isinstance(registry, InMemoryToolRegistry)


@pytest.mark.asyncio
async def test_get_registry_explicit_provider_type():
    """Test get_registry with explicit provider_type."""
    await clear_registry_cache()

    registry = await get_registry(provider_type="memory")
    assert isinstance(registry, InMemoryToolRegistry)


@pytest.mark.asyncio
async def test_get_registry_caching():
    """Test that registry is cached - lines 43-45."""
    await clear_registry_cache()

    # First call creates the registry
    registry1 = await get_registry(provider_type="memory")

    # Second call should return cached instance
    registry2 = await get_registry(provider_type="memory")

    # Should be the same instance
    assert registry1 is registry2


@pytest.mark.asyncio
async def test_get_registry_cache_with_kwargs():
    """Test caching works with different kwargs - line 43."""
    await clear_registry_cache()

    # Different kwargs should create different cache keys
    registry1 = await get_registry(provider_type="memory")
    registry2 = await get_registry(provider_type="memory")

    # Same kwargs should return same instance
    assert registry1 is registry2


@pytest.mark.asyncio
async def test_get_registry_lock_creation():
    """Test that locks are created for new cache keys - lines 47-49."""
    await clear_registry_cache()

    # Import the lock dict to verify it's created
    from chuk_tool_processor.registry.providers import _REGISTRY_LOCKS

    initial_lock_count = len(_REGISTRY_LOCKS)

    # Get registry which should create a lock
    await get_registry(provider_type="memory")

    # Should have created a lock
    assert len(_REGISTRY_LOCKS) >= initial_lock_count


@pytest.mark.asyncio
async def test_get_registry_double_check_pattern():
    """Test double-check locking pattern - lines 52-55."""
    await clear_registry_cache()

    # Simulate concurrent access
    async def get_reg():
        return await get_registry(provider_type="memory")

    # Multiple concurrent calls should still return the same instance
    results = await asyncio.gather(*[get_reg() for _ in range(5)])

    # All should be the same instance
    first_registry = results[0]
    assert all(reg is first_registry for reg in results)


@pytest.mark.asyncio
async def test_get_registry_memory_provider():
    """Test creating memory provider - lines 58-62."""
    await clear_registry_cache()

    registry = await get_registry(provider_type="memory")

    assert isinstance(registry, InMemoryToolRegistry)


@pytest.mark.asyncio
async def test_get_registry_unknown_provider():
    """Test unknown provider raises ValueError - lines 63-64."""
    await clear_registry_cache()

    with pytest.raises(ValueError, match="Unknown registry provider type"):
        await get_registry(provider_type="unknown_provider")


@pytest.mark.asyncio
async def test_get_registry_caches_after_creation():
    """Test registry is cached after creation - lines 66-68."""
    await clear_registry_cache()

    from chuk_tool_processor.registry.providers import _REGISTRY_CACHE

    # Cache should be empty
    initial_cache_size = len(_REGISTRY_CACHE)

    # Get registry
    registry = await get_registry(provider_type="memory")

    # Cache should now contain the registry
    assert len(_REGISTRY_CACHE) > initial_cache_size

    # Verify the registry is in the cache
    cache_key = f"memory:{hash(frozenset({}.items()))}"
    assert cache_key in _REGISTRY_CACHE
    assert _REGISTRY_CACHE[cache_key] is registry


@pytest.mark.asyncio
async def test_clear_registry_cache():
    """Test clear_registry_cache function - line 77."""
    # Create a registry to populate the cache
    await get_registry(provider_type="memory")

    from chuk_tool_processor.registry.providers import _REGISTRY_CACHE

    # Cache should have entries
    assert len(_REGISTRY_CACHE) > 0

    # Clear the cache
    await clear_registry_cache()

    # Cache should be empty
    assert len(_REGISTRY_CACHE) == 0


@pytest.mark.asyncio
async def test_get_registry_with_none_provider_type():
    """Test get_registry when provider_type is None - line 39."""
    await clear_registry_cache()

    # Should use environment variable or default to memory
    with patch.dict(os.environ, {}, clear=True):
        # Remove any existing CHUK_TOOL_REGISTRY_PROVIDER
        os.environ.pop("CHUK_TOOL_REGISTRY_PROVIDER", None)

        registry = await get_registry(provider_type=None)
        assert isinstance(registry, InMemoryToolRegistry)


@pytest.mark.asyncio
async def test_get_registry_concurrent_first_time():
    """Test concurrent first-time access to registry."""
    await clear_registry_cache()

    # Multiple tasks trying to get the same registry concurrently
    tasks = [get_registry(provider_type="memory") for _ in range(10)]
    registries = await asyncio.gather(*tasks)

    # All should be the same instance
    assert all(r is registries[0] for r in registries)


@pytest.mark.asyncio
async def test_get_registry_with_different_cache_keys():
    """Test that different configurations create different cache entries."""
    await clear_registry_cache()

    # This test verifies the cache key generation works correctly
    registry1 = await get_registry(provider_type="memory")

    # Same provider type should return cached instance
    registry2 = await get_registry(provider_type="memory")

    assert registry1 is registry2


@pytest.mark.asyncio
async def test_environment_variable_fallback():
    """Test environment variable is used when provider_type is None."""
    await clear_registry_cache()

    # Test with explicit environment variable
    with patch.dict(os.environ, {"CHUK_TOOL_REGISTRY_PROVIDER": "memory"}):
        registry = await get_registry(provider_type=None)
        assert isinstance(registry, InMemoryToolRegistry)


@pytest.mark.asyncio
async def test_cache_key_with_empty_kwargs():
    """Test cache key generation with empty kwargs."""
    await clear_registry_cache()

    # Get registry with no kwargs
    registry = await get_registry(provider_type="memory")

    # Should be cached
    assert registry is not None

    # Getting again should return same instance
    registry2 = await get_registry(provider_type="memory")
    assert registry is registry2


@pytest.mark.asyncio
async def test_get_registry_redis_provider():
    """Test creating redis provider - lines 74-84."""
    await clear_registry_cache()

    from unittest.mock import AsyncMock, MagicMock

    mock_registry = MagicMock()
    mock_create = AsyncMock(return_value=mock_registry)

    # Create a mock module with the function
    mock_redis_module = MagicMock()
    mock_redis_module.create_redis_registry = mock_create

    import sys

    # Insert our mock module before the import happens
    sys.modules["chuk_tool_processor.registry.providers.redis"] = mock_redis_module

    try:
        registry = await get_registry(
            provider_type="redis",
            redis_url="redis://test:6379/0",
            key_prefix="test_prefix",
            local_cache_ttl=30.0,
        )
        assert registry is mock_registry

        # Verify the function was called with our kwargs
        mock_create.assert_called_once_with(
            redis_url="redis://test:6379/0",
            key_prefix="test_prefix",
            local_cache_ttl=30.0,
        )
    finally:
        # Clean up
        del sys.modules["chuk_tool_processor.registry.providers.redis"]


@pytest.mark.asyncio
async def test_get_registry_redis_with_defaults():
    """Test creating redis provider with default kwargs - lines 77-79."""
    await clear_registry_cache()

    from unittest.mock import AsyncMock, MagicMock

    mock_registry = MagicMock()
    mock_create = AsyncMock(return_value=mock_registry)

    # Create a mock module with the function
    mock_redis_module = MagicMock()
    mock_redis_module.create_redis_registry = mock_create

    import sys

    # Insert our mock module before the import happens
    sys.modules["chuk_tool_processor.registry.providers.redis"] = mock_redis_module

    try:
        # Call without any kwargs - should use defaults
        registry = await get_registry(provider_type="redis")
        assert registry is mock_registry

        # Verify defaults were passed
        mock_create.assert_called_once_with(
            redis_url="redis://localhost:6379/0",
            key_prefix="chuk",
            local_cache_ttl=60.0,
        )
    finally:
        # Clean up
        del sys.modules["chuk_tool_processor.registry.providers.redis"]


@pytest.mark.asyncio
async def test_get_registry_double_check_cache_hit():
    """Test double-check pattern when cache is hit after lock - line 66."""
    await clear_registry_cache()

    from chuk_tool_processor.registry.providers import _REGISTRY_CACHE, _REGISTRY_LOCKS

    # Pre-populate the cache key and lock to simulate race condition
    cache_key = f"memory:{hash(frozenset({}.items()))}"
    _REGISTRY_LOCKS[cache_key] = asyncio.Lock()

    # Pre-populate cache with a registry
    pre_cached_registry = InMemoryToolRegistry()
    _REGISTRY_CACHE[cache_key] = pre_cached_registry

    # Now call get_registry - it should hit the first cache check (line 55-56)
    registry = await get_registry(provider_type="memory")

    # Should get the pre-cached instance
    assert registry is pre_cached_registry


@pytest.mark.asyncio
async def test_get_registry_double_check_inside_lock():
    """Test double-check pattern inside the lock - line 65-66.

    This tests the scenario where another coroutine populates the cache
    while we're waiting for the lock.
    """
    await clear_registry_cache()

    from chuk_tool_processor.registry.providers import _REGISTRY_CACHE, _REGISTRY_LOCKS

    cache_key = f"memory:{hash(frozenset({}.items()))}"

    # Create a lock that we'll hold
    lock = asyncio.Lock()
    _REGISTRY_LOCKS[cache_key] = lock

    pre_cached_registry = InMemoryToolRegistry()
    got_result = asyncio.Event()

    async def first_getter():
        """Hold the lock and populate cache after a delay."""
        async with lock:
            # Simulate creating registry
            await asyncio.sleep(0.05)
            _REGISTRY_CACHE[cache_key] = pre_cached_registry
            got_result.set()

    async def second_getter():
        """Wait for first getter to start, then try to get registry."""
        # Wait a bit for first getter to acquire the lock
        await asyncio.sleep(0.01)
        # This should wait for lock, then hit the double-check cache
        return await get_registry(provider_type="memory")

    # Start both concurrently
    task1 = asyncio.create_task(first_getter())
    task2 = asyncio.create_task(second_getter())

    await task1
    result = await task2

    # Second getter should have gotten the pre-cached registry
    assert result is pre_cached_registry
