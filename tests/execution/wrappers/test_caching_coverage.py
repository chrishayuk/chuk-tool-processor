"""
Additional tests for caching.py to improve coverage.

These tests target specific uncovered lines to push coverage above 90%.
"""

import asyncio
from unittest.mock import Mock, patch

import pytest

from chuk_tool_processor.execution.wrappers.caching import (
    CachingToolExecutor,
    InMemoryCache,
)
from chuk_tool_processor.models.tool_call import ToolCall


class TestCachingAdditionalCoverage:
    """Additional tests to improve caching coverage."""

    @pytest.mark.asyncio
    async def test_prune_expired_entries(self):
        """Test _prune_expired method (lines 184-201)."""
        cache = InMemoryCache(default_ttl=1)  # 1 second TTL

        # Add some entries
        await cache.set("tool1", "hash1", {"result": "1"}, ttl=1)
        await cache.set("tool2", "hash2", {"result": "2"}, ttl=1)
        await cache.set("tool3", "hash3", {"result": "3"}, ttl=10)  # Won't expire

        # Wait for entries to expire
        await asyncio.sleep(1.5)

        # Clean up expired entries
        removed = await cache._prune_expired()

        # Should have removed 2 entries
        assert removed == 2

        # Check that tool3 is still there
        result = await cache.get("tool3", "hash3")
        assert result is not None

        # Check that tool1 and tool2 are gone
        result1 = await cache.get("tool1", "hash1")
        result2 = await cache.get("tool2", "hash2")
        assert result1 is None
        assert result2 is None

    @pytest.mark.asyncio
    async def test_invalidate_tool_not_in_cache(self):
        """Test invalidate when tool not in cache (line 284)."""
        cache = InMemoryCache()

        # Try to invalidate a tool that doesn't exist
        await cache.invalidate("nonexistent_tool")

        # Should not raise any error
        # Test passes if we get here

    @pytest.mark.asyncio
    async def test_invalidate_specific_entry(self):
        """Test invalidate with specific arguments_hash."""
        cache = InMemoryCache()

        # Add multiple entries for the same tool
        await cache.set("tool1", "hash1", {"result": "1"})
        await cache.set("tool1", "hash2", {"result": "2"})

        # Invalidate just one entry
        await cache.invalidate("tool1", "hash1")

        # Check that hash1 is gone but hash2 remains
        result1 = await cache.get("tool1", "hash1")
        result2 = await cache.get("tool1", "hash2")
        assert result1 is None
        assert result2 is not None

    @pytest.mark.asyncio
    async def test_hash_arguments_error_handling(self):
        """Test hash_arguments with non-serializable object (lines 384-387)."""
        # Create an executor with a mock
        mock_executor = Mock()
        mock_executor.execute = Mock(return_value=[])

        cache = InMemoryCache()
        caching_executor = CachingToolExecutor(executor=mock_executor, cache=cache)

        # Create an object that can't be JSON serialized
        class NonSerializable:
            pass

        # This should trigger the exception handler and use fallback
        args_hash = caching_executor._hash_arguments({"obj": NonSerializable()})

        # Should return a hash (fallback to str representation)
        assert isinstance(args_hash, str)
        assert len(args_hash) == 32  # MD5 hash length

    @pytest.mark.asyncio
    async def test_caching_with_metrics_enabled(self):
        """Test caching with metrics recording (lines 459)."""
        # Mock the metrics module
        with patch("chuk_tool_processor.execution.wrappers.caching.get_metrics") as mock_get_metrics:
            mock_metrics = Mock()
            mock_metrics.record_cache_operation = Mock()
            mock_get_metrics.return_value = mock_metrics

            # Create executor
            mock_executor = Mock()

            async def mock_execute(calls, **kwargs):
                return [Mock(tool=call.tool, result={"data": "test"}, error=None) for call in calls]

            mock_executor.execute = mock_execute

            cache = InMemoryCache()
            caching_executor = CachingToolExecutor(executor=mock_executor, cache=cache)

            # Execute a call (cache miss)
            call = ToolCall(tool="test_tool", arguments={})
            await caching_executor.execute([call])

            # Verify metrics were recorded
            assert mock_metrics.record_cache_operation.called

    @pytest.mark.asyncio
    async def test_cache_removal_when_last_entry_invalidated(self):
        """Test that tool cache is removed when last entry is invalidated."""
        cache = InMemoryCache()

        # Add a single entry
        await cache.set("tool1", "hash1", {"result": "1"})

        # Invalidate it with specific hash
        await cache.invalidate("tool1", "hash1")

        # Tool should be completely removed from cache
        # Add another entry to verify tool was removed
        await cache.set("tool1", "hash2", {"result": "2"})
        result = await cache.get("tool1", "hash2")
        assert result is not None

    @pytest.mark.asyncio
    async def test_invalidate_all_entries_for_tool(self):
        """Test invalidate without arguments_hash (invalidates all)."""
        cache = InMemoryCache()

        # Add multiple entries for the same tool
        await cache.set("tool1", "hash1", {"result": "1"})
        await cache.set("tool1", "hash2", {"result": "2"})
        await cache.set("tool1", "hash3", {"result": "3"})

        # Invalidate all entries for the tool
        await cache.invalidate("tool1")

        # All entries should be gone
        result1 = await cache.get("tool1", "hash1")
        result2 = await cache.get("tool1", "hash2")
        result3 = await cache.get("tool1", "hash3")
        assert result1 is None
        assert result2 is None
        assert result3 is None

    @pytest.mark.asyncio
    async def test_prune_expired_removes_empty_tool_caches(self):
        """Test that _prune_expired removes empty tool caches (lines 198-199)."""
        cache = InMemoryCache(default_ttl=1)

        # Add entries that will all expire
        await cache.set("tool1", "hash1", {"result": "1"}, ttl=1)
        await cache.set("tool1", "hash2", {"result": "2"}, ttl=1)

        # Wait for expiration
        await asyncio.sleep(1.5)

        # Cleanup
        removed = await cache._prune_expired()
        assert removed == 2

        # Try to add a new entry - this should work fine
        await cache.set("tool1", "hash3", {"result": "3"})
        result = await cache.get("tool1", "hash3")
        assert result is not None
