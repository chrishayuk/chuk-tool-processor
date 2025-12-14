# tests/execution/wrappers/test_redis_circuit_breaker.py
"""
Tests for the Redis-backed circuit breaker implementation.

These tests use fakeredis for in-memory Redis simulation, allowing testing
without a real Redis server.
"""

import asyncio
from datetime import UTC, datetime

import pytest
import pytest_asyncio

# Check if redis and fakeredis are available
pytest.importorskip("redis")
fakeredis = pytest.importorskip("fakeredis")

from chuk_tool_processor.execution.wrappers.redis_circuit_breaker import (  # noqa: E402
    RedisCircuitBreaker,
    RedisCircuitBreakerConfig,
    RedisCircuitBreakerExecutor,
)
from chuk_tool_processor.models.tool_call import ToolCall  # noqa: E402
from chuk_tool_processor.models.tool_result import ToolResult  # noqa: E402


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest_asyncio.fixture
async def fake_redis():
    """Create a fake Redis client for testing."""
    server = fakeredis.FakeServer()
    redis = fakeredis.aioredis.FakeRedis(server=server, decode_responses=False)
    yield redis
    await redis.aclose()


@pytest_asyncio.fixture
async def breaker(fake_redis):
    """Create a RedisCircuitBreaker with fake Redis."""
    return RedisCircuitBreaker(
        fake_redis,
        default_config=RedisCircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            reset_timeout=0.1,  # Short timeout for testing
            half_open_max_calls=1,
            failure_window=60.0,
        ),
    )


# --------------------------------------------------------------------------- #
# RedisCircuitBreaker Tests
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_circuit_breaker_init(fake_redis):
    """Test RedisCircuitBreaker initialization."""
    breaker = RedisCircuitBreaker(
        fake_redis,
        default_config=RedisCircuitBreakerConfig(
            failure_threshold=5,
            reset_timeout=60.0,
        ),
    )
    assert breaker.default_config.failure_threshold == 5
    assert breaker.default_config.reset_timeout == 60.0


@pytest.mark.asyncio
async def test_circuit_breaker_initial_state(breaker):
    """Test that circuit breaker starts in CLOSED state."""
    can_execute = await breaker.can_execute("test_tool")
    assert can_execute is True

    state = await breaker.get_state("test_tool")
    assert state["state"] == "closed"


@pytest.mark.asyncio
async def test_circuit_opens_after_failures(breaker):
    """Test circuit opens after reaching failure threshold."""
    # Record failures
    for _ in range(3):
        await breaker.record_failure("test_tool")

    # Circuit should be OPEN
    state = await breaker.get_state("test_tool")
    assert state["state"] == "open"

    # Should not allow execution
    can_execute = await breaker.can_execute("test_tool")
    assert can_execute is False


@pytest.mark.asyncio
async def test_circuit_half_open_after_timeout(breaker):
    """Test circuit transitions to HALF_OPEN after reset timeout."""
    # Open the circuit
    for _ in range(3):
        await breaker.record_failure("test_tool")

    # Should not allow execution immediately
    can_execute = await breaker.can_execute("test_tool")
    assert can_execute is False

    # Wait for reset timeout
    await asyncio.sleep(0.15)

    # Should transition to HALF_OPEN and allow one request
    can_execute = await breaker.can_execute("test_tool")
    assert can_execute is True

    state = await breaker.get_state("test_tool")
    assert state["state"] == "half_open"


@pytest.mark.asyncio
async def test_circuit_closes_after_successes(breaker):
    """Test circuit closes after enough successes in HALF_OPEN."""
    # Open the circuit
    for _ in range(3):
        await breaker.record_failure("test_tool")

    # Wait and transition to HALF_OPEN
    await asyncio.sleep(0.15)
    await breaker.can_execute("test_tool")

    # Record successes
    await breaker.record_success("test_tool")

    # Need to get another slot for second success test
    await asyncio.sleep(0.15)
    await breaker.can_execute("test_tool")
    await breaker.record_success("test_tool")

    # Circuit should be CLOSED
    state = await breaker.get_state("test_tool")
    assert state["state"] == "closed"


@pytest.mark.asyncio
async def test_circuit_reopens_on_half_open_failure(breaker):
    """Test circuit reopens if failure occurs during HALF_OPEN."""
    # Open the circuit
    for _ in range(3):
        await breaker.record_failure("test_tool")

    # Wait and transition to HALF_OPEN
    await asyncio.sleep(0.15)
    await breaker.can_execute("test_tool")

    # Failure during HALF_OPEN
    await breaker.record_failure("test_tool")

    # Should be back to OPEN
    state = await breaker.get_state("test_tool")
    assert state["state"] == "open"


@pytest.mark.asyncio
async def test_circuit_half_open_max_calls(breaker):
    """Test HALF_OPEN limits concurrent calls."""
    # Open the circuit
    for _ in range(3):
        await breaker.record_failure("test_tool")

    # Wait and transition to HALF_OPEN
    await asyncio.sleep(0.15)

    # First call should be allowed
    can_execute1 = await breaker.can_execute("test_tool")
    assert can_execute1 is True

    # Second call should be blocked (max_calls=1)
    can_execute2 = await breaker.can_execute("test_tool")
    assert can_execute2 is False


@pytest.mark.asyncio
async def test_per_tool_circuits(fake_redis):
    """Test that each tool has its own circuit."""
    breaker = RedisCircuitBreaker(
        fake_redis,
        default_config=RedisCircuitBreakerConfig(
            failure_threshold=2,
            reset_timeout=60.0,
        ),
    )

    # Open circuit for tool1
    await breaker.record_failure("tool1")
    await breaker.record_failure("tool1")

    # tool1 circuit should be OPEN
    can_execute1 = await breaker.can_execute("tool1")
    assert can_execute1 is False

    # tool2 circuit should be CLOSED
    can_execute2 = await breaker.can_execute("tool2")
    assert can_execute2 is True


@pytest.mark.asyncio
async def test_per_tool_config(fake_redis):
    """Test per-tool circuit breaker configurations."""
    breaker = RedisCircuitBreaker(
        fake_redis,
        default_config=RedisCircuitBreakerConfig(failure_threshold=5),
        tool_configs={
            "sensitive_tool": RedisCircuitBreakerConfig(failure_threshold=1),
        },
    )

    # One failure should open sensitive_tool
    await breaker.record_failure("sensitive_tool")
    can_execute = await breaker.can_execute("sensitive_tool")
    assert can_execute is False

    # One failure should NOT open normal_tool
    await breaker.record_failure("normal_tool")
    can_execute = await breaker.can_execute("normal_tool")
    assert can_execute is True


@pytest.mark.asyncio
async def test_get_all_states(fake_redis):
    """Test getting all circuit states."""
    breaker = RedisCircuitBreaker(
        fake_redis,
        default_config=RedisCircuitBreakerConfig(failure_threshold=2),
    )

    # Open circuit for tool1
    await breaker.record_failure("tool1")
    await breaker.record_failure("tool1")

    # Create state for tool2 (closed)
    await breaker.can_execute("tool2")

    # Get all states
    states = await breaker.get_all_states()
    assert "tool1" in states
    assert states["tool1"]["state"] == "open"


@pytest.mark.asyncio
async def test_reset_circuit(breaker):
    """Test manually resetting a circuit."""
    # Open the circuit
    for _ in range(3):
        await breaker.record_failure("test_tool")

    # Verify OPEN
    state = await breaker.get_state("test_tool")
    assert state["state"] == "open"

    # Reset
    await breaker.reset("test_tool")

    # Should be able to execute now
    can_execute = await breaker.can_execute("test_tool")
    assert can_execute is True


@pytest.mark.asyncio
async def test_reset_all(fake_redis):
    """Test resetting all circuits."""
    breaker = RedisCircuitBreaker(
        fake_redis,
        default_config=RedisCircuitBreakerConfig(failure_threshold=2),
    )

    # Open circuits for multiple tools
    await breaker.record_failure("tool1")
    await breaker.record_failure("tool1")
    await breaker.record_failure("tool2")
    await breaker.record_failure("tool2")

    # Reset all
    count = await breaker.reset_all()
    assert count > 0

    # All should be able to execute
    assert await breaker.can_execute("tool1") is True
    assert await breaker.can_execute("tool2") is True


@pytest.mark.asyncio
async def test_key_prefix(fake_redis):
    """Test custom key prefix isolation."""
    breaker1 = RedisCircuitBreaker(
        fake_redis,
        default_config=RedisCircuitBreakerConfig(failure_threshold=2),
        key_prefix="app1:cb",
    )
    breaker2 = RedisCircuitBreaker(
        fake_redis,
        default_config=RedisCircuitBreakerConfig(failure_threshold=2),
        key_prefix="app2:cb",
    )

    # Open circuit in breaker1
    await breaker1.record_failure("tool")
    await breaker1.record_failure("tool")

    # Breaker1 should be OPEN
    assert await breaker1.can_execute("tool") is False

    # Breaker2 should be CLOSED (different prefix)
    assert await breaker2.can_execute("tool") is True


@pytest.mark.asyncio
async def test_failure_window(fake_redis):
    """Test sliding window for failure counting."""
    breaker = RedisCircuitBreaker(
        fake_redis,
        default_config=RedisCircuitBreakerConfig(
            failure_threshold=3,
            failure_window=0.5,  # 500ms window
        ),
    )

    # Record 2 failures
    await breaker.record_failure("test_tool")
    await breaker.record_failure("test_tool")

    # Wait for first failures to expire
    await asyncio.sleep(0.6)

    # Record 1 more failure (previous 2 should be expired)
    await breaker.record_failure("test_tool")

    # Should still be CLOSED (only 1 failure in window)
    can_execute = await breaker.can_execute("test_tool")
    assert can_execute is True


# --------------------------------------------------------------------------- #
# RedisCircuitBreakerExecutor Tests
# --------------------------------------------------------------------------- #
class DummyExecutor:
    """Simple executor that can simulate failures."""

    def __init__(self):
        self.call_count = 0
        self.should_fail = False

    async def execute(self, calls, timeout=None, use_cache=True):
        self.call_count += 1
        results = []
        for call in calls:
            now = datetime.now(UTC)
            if self.should_fail:
                results.append(
                    ToolResult(
                        tool=call.tool,
                        result=None,
                        error="Simulated failure",
                        start_time=now,
                        end_time=now,
                        machine="test",
                        pid=0,
                    )
                )
            else:
                results.append(
                    ToolResult(
                        tool=call.tool,
                        result={"success": True},
                        error=None,
                        start_time=now,
                        end_time=now,
                        machine="test",
                        pid=0,
                    )
                )
        return results


@pytest.mark.asyncio
async def test_executor_allows_calls_when_closed(fake_redis):
    """Test executor allows calls in CLOSED state."""
    breaker = RedisCircuitBreaker(
        fake_redis,
        default_config=RedisCircuitBreakerConfig(failure_threshold=3),
    )
    exec_ = DummyExecutor()
    circuit_exec = RedisCircuitBreakerExecutor(exec_, breaker)

    call = ToolCall(tool="test_tool", arguments={})
    results = await circuit_exec.execute([call])

    assert len(results) == 1
    assert results[0].error is None
    assert exec_.call_count == 1


@pytest.mark.asyncio
async def test_executor_opens_circuit_after_failures(fake_redis):
    """Test executor opens circuit after failure threshold."""
    breaker = RedisCircuitBreaker(
        fake_redis,
        default_config=RedisCircuitBreakerConfig(failure_threshold=3),
    )
    exec_ = DummyExecutor()
    exec_.should_fail = True
    circuit_exec = RedisCircuitBreakerExecutor(exec_, breaker)

    call = ToolCall(tool="test_tool", arguments={})

    # Execute until circuit opens
    await circuit_exec.execute([call])
    await circuit_exec.execute([call])
    await circuit_exec.execute([call])

    # Circuit should be open
    assert exec_.call_count == 3

    # Next call should be rejected
    results = await circuit_exec.execute([call])
    assert results[0].error is not None
    assert "circuit breaker" in results[0].error.lower()
    assert exec_.call_count == 3  # Not executed


@pytest.mark.asyncio
async def test_executor_half_open_recovery(fake_redis):
    """Test executor recovers through HALF_OPEN state."""
    breaker = RedisCircuitBreaker(
        fake_redis,
        default_config=RedisCircuitBreakerConfig(
            failure_threshold=2,
            success_threshold=2,
            reset_timeout=0.1,
        ),
    )
    exec_ = DummyExecutor()
    exec_.should_fail = True
    circuit_exec = RedisCircuitBreakerExecutor(exec_, breaker)

    call = ToolCall(tool="test_tool", arguments={})

    # Open the circuit
    await circuit_exec.execute([call])
    await circuit_exec.execute([call])

    # Wait for reset timeout
    await asyncio.sleep(0.15)

    # Fix the executor and try again
    exec_.should_fail = False

    # First success
    results = await circuit_exec.execute([call])
    assert results[0].error is None

    # Wait for another half-open slot
    await asyncio.sleep(0.15)

    # Second success should close circuit
    results = await circuit_exec.execute([call])
    assert results[0].error is None

    # Circuit should be closed now
    states = await circuit_exec.get_circuit_states()
    assert "test_tool" in states
    assert states["test_tool"]["state"] == "closed"


@pytest.mark.asyncio
async def test_executor_per_tool_circuits(fake_redis):
    """Test executor maintains separate circuits per tool."""
    breaker = RedisCircuitBreaker(
        fake_redis,
        default_config=RedisCircuitBreakerConfig(failure_threshold=2),
    )
    exec_ = DummyExecutor()
    circuit_exec = RedisCircuitBreakerExecutor(exec_, breaker)

    call1 = ToolCall(tool="tool1", arguments={})
    call2 = ToolCall(tool="tool2", arguments={})

    # Fail tool1
    exec_.should_fail = True
    await circuit_exec.execute([call1])
    await circuit_exec.execute([call1])

    exec_.should_fail = False

    # tool1 circuit should be open
    results1 = await circuit_exec.execute([call1])
    assert "circuit breaker" in results1[0].error.lower()

    # tool2 circuit should be closed
    results2 = await circuit_exec.execute([call2])
    assert results2[0].error is None


@pytest.mark.asyncio
async def test_executor_reset_circuit(fake_redis):
    """Test manually resetting a circuit via executor."""
    breaker = RedisCircuitBreaker(
        fake_redis,
        default_config=RedisCircuitBreakerConfig(failure_threshold=2),
    )
    exec_ = DummyExecutor()
    exec_.should_fail = True
    circuit_exec = RedisCircuitBreakerExecutor(exec_, breaker)

    call = ToolCall(tool="test_tool", arguments={})

    # Open the circuit
    await circuit_exec.execute([call])
    await circuit_exec.execute([call])

    # Verify circuit is open
    results = await circuit_exec.execute([call])
    assert "circuit breaker" in results[0].error.lower()

    # Reset the circuit
    await circuit_exec.reset_circuit("test_tool")

    # Fix the executor
    exec_.should_fail = False

    # Should be able to execute now
    results = await circuit_exec.execute([call])
    assert results[0].error is None


@pytest.mark.asyncio
async def test_executor_empty_calls(fake_redis):
    """Test executor handles empty calls list."""
    breaker = RedisCircuitBreaker(fake_redis)
    exec_ = DummyExecutor()
    circuit_exec = RedisCircuitBreakerExecutor(exec_, breaker)

    results = await circuit_exec.execute([])
    assert results == []


@pytest.mark.asyncio
async def test_executor_exception_handling(fake_redis):
    """Test executor handles exceptions from underlying executor."""
    breaker = RedisCircuitBreaker(
        fake_redis,
        default_config=RedisCircuitBreakerConfig(failure_threshold=2),
    )
    exec_ = DummyExecutor()

    async def failing_execute(*args, **kwargs):
        raise ValueError("Simulated exception")

    exec_.execute = failing_execute
    circuit_exec = RedisCircuitBreakerExecutor(exec_, breaker)

    call = ToolCall(tool="test_tool", arguments={})

    # First exception
    results = await circuit_exec.execute([call])
    assert results[0].error is not None

    # Second exception should open circuit
    await circuit_exec.execute([call])

    # Third call should be blocked by circuit
    exec_.execute = DummyExecutor().execute  # Reset to working executor
    results = await circuit_exec.execute([call])
    assert "circuit breaker" in results[0].error.lower()


@pytest.mark.asyncio
async def test_config_defaults():
    """Test RedisCircuitBreakerConfig default values."""
    config = RedisCircuitBreakerConfig()

    assert config.failure_threshold == 5
    assert config.success_threshold == 2
    assert config.reset_timeout == 60.0
    assert config.half_open_max_calls == 1
    assert config.failure_window == 60.0


# --------------------------------------------------------------------------- #
# Additional tests for better coverage
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_circuit_state_with_time_until_half_open(fake_redis):
    """Test get_state returns time_until_half_open when circuit is open."""
    breaker = RedisCircuitBreaker(
        fake_redis,
        default_config=RedisCircuitBreakerConfig(
            failure_threshold=2,
            reset_timeout=10.0,  # Longer timeout
        ),
    )

    # Open the circuit
    await breaker.record_failure("test_tool")
    await breaker.record_failure("test_tool")

    # Get state
    state = await breaker.get_state("test_tool")
    assert state["state"] == "open"
    assert state["time_until_half_open"] is not None
    assert state["time_until_half_open"] > 0
    assert state["config"]["failure_threshold"] == 2
    assert state["config"]["reset_timeout"] == 10.0


@pytest.mark.asyncio
async def test_record_success_in_closed_state(breaker):
    """Test recording success when circuit is closed."""
    # Record some success
    await breaker.record_success("test_tool")

    # Should still be closed
    state = await breaker.get_state("test_tool")
    assert state["state"] == "closed"


@pytest.mark.asyncio
async def test_create_redis_circuit_breaker_function(fake_redis, monkeypatch):
    """Test the create_redis_circuit_breaker factory function."""
    from chuk_tool_processor.execution.wrappers import redis_circuit_breaker

    # Monkeypatch Redis.from_url to return our fake redis
    original_from_url = None

    def mock_from_url(*args, **kwargs):
        return fake_redis

    from redis import asyncio as redis_asyncio

    original_from_url = redis_asyncio.Redis.from_url
    monkeypatch.setattr(redis_asyncio.Redis, "from_url", mock_from_url)

    try:
        breaker = await redis_circuit_breaker.create_redis_circuit_breaker(
            redis_url="redis://localhost:6379/0",
            default_config=RedisCircuitBreakerConfig(failure_threshold=3),
            key_prefix="test_prefix",
        )

        assert breaker is not None
        assert breaker._key_prefix == "test_prefix"
        assert breaker.default_config.failure_threshold == 3
    finally:
        monkeypatch.setattr(redis_asyncio.Redis, "from_url", original_from_url)


@pytest.mark.asyncio
async def test_create_redis_circuit_breaker_executor_function(fake_redis, monkeypatch):
    """Test the create_redis_circuit_breaker_executor factory function."""
    from chuk_tool_processor.execution.wrappers import redis_circuit_breaker

    def mock_from_url(*args, **kwargs):
        return fake_redis

    from redis import asyncio as redis_asyncio

    original_from_url = redis_asyncio.Redis.from_url
    monkeypatch.setattr(redis_asyncio.Redis, "from_url", mock_from_url)

    try:
        exec_ = DummyExecutor()
        circuit_exec = await redis_circuit_breaker.create_redis_circuit_breaker_executor(
            exec_,
            redis_url="redis://localhost:6379/0",
            default_config=RedisCircuitBreakerConfig(failure_threshold=3),
            tool_configs={"special_tool": RedisCircuitBreakerConfig(failure_threshold=1)},
            key_prefix="test_executor",
        )

        assert circuit_exec is not None
        assert circuit_exec.executor is exec_

        # Test execution through the wrapper
        call = ToolCall(tool="test_tool", arguments={})
        results = await circuit_exec.execute([call])
        assert len(results) == 1
    finally:
        monkeypatch.setattr(redis_asyncio.Redis, "from_url", original_from_url)


@pytest.mark.asyncio
async def test_executor_records_success_after_success(fake_redis):
    """Test executor records success after successful execution."""
    breaker = RedisCircuitBreaker(
        fake_redis,
        default_config=RedisCircuitBreakerConfig(failure_threshold=3),
    )
    exec_ = DummyExecutor()
    circuit_exec = RedisCircuitBreakerExecutor(exec_, breaker)

    call = ToolCall(tool="test_tool", arguments={})

    # Execute successfully
    results = await circuit_exec.execute([call])
    assert results[0].error is None

    # Check state - should show no failures
    state = await breaker.get_state("test_tool")
    assert state["failure_count"] == 0


@pytest.mark.asyncio
async def test_executor_with_use_cache_attribute(fake_redis):
    """Test executor passes use_cache to underlying executor that supports it."""
    breaker = RedisCircuitBreaker(fake_redis)

    class CachingExecutor:
        use_cache = True

        async def execute(self, calls, timeout=None, use_cache=True):
            self.last_use_cache = use_cache
            return [ToolResult(tool=c.tool, result={}, error=None) for c in calls]

    exec_ = CachingExecutor()
    circuit_exec = RedisCircuitBreakerExecutor(exec_, breaker)

    call = ToolCall(tool="test_tool", arguments={})
    await circuit_exec.execute([call], use_cache=False)

    assert exec_.last_use_cache is False


@pytest.mark.asyncio
async def test_get_all_states_empty(fake_redis):
    """Test get_all_states when no circuits exist."""
    breaker = RedisCircuitBreaker(
        fake_redis,
        key_prefix="empty_prefix",
    )

    states = await breaker.get_all_states()
    assert states == {}


@pytest.mark.asyncio
async def test_circuit_breaker_private_key_methods(fake_redis):
    """Test private key generation methods."""
    breaker = RedisCircuitBreaker(
        fake_redis,
        key_prefix="myprefix",
    )

    state_key = breaker._state_key("my_tool")
    assert state_key == "myprefix:my_tool:state"

    failures_key = breaker._failures_key("my_tool")
    assert failures_key == "myprefix:my_tool:failures"


@pytest.mark.asyncio
async def test_circuit_breaker_get_config(fake_redis):
    """Test _get_config returns correct config for tools."""
    default_cfg = RedisCircuitBreakerConfig(failure_threshold=5)
    special_cfg = RedisCircuitBreakerConfig(failure_threshold=2)

    breaker = RedisCircuitBreaker(
        fake_redis,
        default_config=default_cfg,
        tool_configs={"special_tool": special_cfg},
    )

    # Default config for unknown tool
    cfg = breaker._get_config("unknown_tool")
    assert cfg.failure_threshold == 5

    # Specific config for special tool
    cfg = breaker._get_config("special_tool")
    assert cfg.failure_threshold == 2


# --------------------------------------------------------------------------- #
# Additional tests for RedisCircuitBreakerExecutor (for coverage)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_executor_rejects_when_circuit_open(fake_redis):
    """Test executor rejects calls and returns proper error when circuit is open."""
    breaker = RedisCircuitBreaker(
        fake_redis,
        default_config=RedisCircuitBreakerConfig(
            failure_threshold=2,
            reset_timeout=60.0,  # Long timeout so it stays open
        ),
    )
    exec_ = DummyExecutor()
    exec_.should_fail = True
    circuit_exec = RedisCircuitBreakerExecutor(exec_, breaker)

    call = ToolCall(tool="test_tool", arguments={})

    # Open the circuit
    await circuit_exec.execute([call])
    await circuit_exec.execute([call])

    exec_.should_fail = False

    # Next call should be rejected with circuit breaker error
    results = await circuit_exec.execute([call])
    assert len(results) == 1
    assert results[0].error is not None
    assert "circuit breaker" in results[0].error.lower()
    # Check error_info is populated
    assert results[0].error_info is not None


@pytest.mark.asyncio
async def test_executor_rejects_multiple_calls_when_open(fake_redis):
    """Test executor rejects multiple calls when circuit is open."""
    breaker = RedisCircuitBreaker(
        fake_redis,
        default_config=RedisCircuitBreakerConfig(
            failure_threshold=2,
            reset_timeout=60.0,
        ),
    )
    exec_ = DummyExecutor()
    exec_.should_fail = True
    circuit_exec = RedisCircuitBreakerExecutor(exec_, breaker)

    call = ToolCall(tool="test_tool", arguments={})

    # Open the circuit
    await circuit_exec.execute([call])
    await circuit_exec.execute([call])

    exec_.should_fail = False

    # Multiple calls should all be rejected
    calls = [
        ToolCall(tool="test_tool", arguments={}),
        ToolCall(tool="test_tool", arguments={}),
    ]
    results = await circuit_exec.execute(calls)
    assert len(results) == 2
    for r in results:
        assert r.error is not None
        assert "circuit breaker" in r.error.lower()


@pytest.mark.asyncio
async def test_executor_records_failure_on_error_result(fake_redis):
    """Test executor records failure when underlying executor returns error result."""
    breaker = RedisCircuitBreaker(
        fake_redis,
        default_config=RedisCircuitBreakerConfig(failure_threshold=3),
    )
    exec_ = DummyExecutor()
    exec_.should_fail = True
    circuit_exec = RedisCircuitBreakerExecutor(exec_, breaker)

    call = ToolCall(tool="test_tool", arguments={})

    # Execute with error
    results = await circuit_exec.execute([call])
    assert results[0].error is not None

    # Check failure was recorded
    state = await breaker.get_state("test_tool")
    assert state["failure_count"] == 1


@pytest.mark.asyncio
async def test_executor_records_success_on_success_result(fake_redis):
    """Test executor records success when underlying executor returns success."""
    breaker = RedisCircuitBreaker(
        fake_redis,
        default_config=RedisCircuitBreakerConfig(failure_threshold=3),
    )
    exec_ = DummyExecutor()
    exec_.should_fail = False
    circuit_exec = RedisCircuitBreakerExecutor(exec_, breaker)

    call = ToolCall(tool="test_tool", arguments={})

    # Execute successfully
    results = await circuit_exec.execute([call])
    assert results[0].error is None

    # Check state is still closed
    state = await breaker.get_state("test_tool")
    assert state["state"] == "closed"


@pytest.mark.asyncio
async def test_executor_handles_exception_during_execution(fake_redis):
    """Test executor handles exceptions thrown by underlying executor."""
    breaker = RedisCircuitBreaker(
        fake_redis,
        default_config=RedisCircuitBreakerConfig(failure_threshold=3),
    )

    class ExceptionExecutor:
        async def execute(self, calls, timeout=None, use_cache=True):
            raise RuntimeError("Simulated exception")

    circuit_exec = RedisCircuitBreakerExecutor(ExceptionExecutor(), breaker)

    call = ToolCall(tool="test_tool", arguments={})

    # Execute - should catch exception
    results = await circuit_exec.execute([call])
    assert len(results) == 1
    assert results[0].error is not None
    assert "Simulated exception" in results[0].error

    # Check failure was recorded
    state = await breaker.get_state("test_tool")
    assert state["failure_count"] == 1


@pytest.mark.asyncio
async def test_executor_timeout_parameter(fake_redis):
    """Test executor passes timeout to underlying executor."""
    breaker = RedisCircuitBreaker(fake_redis)

    class TimeoutTrackingExecutor:
        last_timeout = None

        async def execute(self, calls, timeout=None, use_cache=True):
            self.last_timeout = timeout
            return [ToolResult(tool=c.tool, result={}, error=None) for c in calls]

    exec_ = TimeoutTrackingExecutor()
    circuit_exec = RedisCircuitBreakerExecutor(exec_, breaker)

    call = ToolCall(tool="test_tool", arguments={})
    await circuit_exec.execute([call], timeout=30.0)

    assert exec_.last_timeout == 30.0


@pytest.mark.asyncio
async def test_executor_multiple_tools_independent(fake_redis):
    """Test executor handles multiple tools with independent circuits."""
    breaker = RedisCircuitBreaker(
        fake_redis,
        default_config=RedisCircuitBreakerConfig(failure_threshold=2),
    )
    exec_ = DummyExecutor()
    circuit_exec = RedisCircuitBreakerExecutor(exec_, breaker)

    # Open circuit for tool1 only
    exec_.should_fail = True
    await circuit_exec.execute([ToolCall(tool="tool1", arguments={})])
    await circuit_exec.execute([ToolCall(tool="tool1", arguments={})])

    exec_.should_fail = False

    # tool1 should be blocked, tool2 should work
    results = await circuit_exec.execute(
        [
            ToolCall(tool="tool1", arguments={}),
            ToolCall(tool="tool2", arguments={}),
        ]
    )

    assert len(results) == 2
    # tool1 blocked
    assert "circuit breaker" in results[0].error.lower()
    # tool2 works
    assert results[1].error is None


@pytest.mark.asyncio
async def test_get_state_with_no_time_until_half_open(fake_redis):
    """Test get_state when circuit is closed (no time_until_half_open)."""
    breaker = RedisCircuitBreaker(
        fake_redis,
        default_config=RedisCircuitBreakerConfig(failure_threshold=5),
    )

    # Get state when closed
    state = await breaker.get_state("test_tool")
    assert state["state"] == "closed"
    assert state["time_until_half_open"] is None
    assert state["opened_at"] is None


@pytest.mark.asyncio
async def test_record_success_logs_transition_to_closed(fake_redis):
    """Test that record_success logs when transitioning to closed."""
    breaker = RedisCircuitBreaker(
        fake_redis,
        default_config=RedisCircuitBreakerConfig(
            failure_threshold=2,
            success_threshold=1,  # Close after 1 success
            reset_timeout=0.01,  # Quick transition to half-open
        ),
    )

    # Open the circuit
    await breaker.record_failure("test_tool")
    await breaker.record_failure("test_tool")

    # Wait for half-open
    await asyncio.sleep(0.02)
    await breaker.can_execute("test_tool")

    # Record success to close
    await breaker.record_success("test_tool")

    state = await breaker.get_state("test_tool")
    assert state["state"] == "closed"


@pytest.mark.asyncio
async def test_record_failure_logs_transition_to_open(fake_redis):
    """Test that record_failure logs when transitioning to open."""
    breaker = RedisCircuitBreaker(
        fake_redis,
        default_config=RedisCircuitBreakerConfig(failure_threshold=2),
    )

    # First failure
    await breaker.record_failure("test_tool")
    state = await breaker.get_state("test_tool")
    assert state["state"] == "closed"

    # Second failure - should open
    await breaker.record_failure("test_tool")
    state = await breaker.get_state("test_tool")
    assert state["state"] == "open"


# --------------------------------------------------------------------------- #
# Mocked tests for better coverage of internal code paths
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_can_execute_returns_true_when_closed():
    """Test can_execute returns True (not 1) when circuit is closed."""
    from unittest.mock import AsyncMock, MagicMock

    mock_redis = MagicMock()
    mock_redis.eval = AsyncMock(return_value=1)

    breaker = RedisCircuitBreaker(
        mock_redis,
        default_config=RedisCircuitBreakerConfig(failure_threshold=5),
    )

    result = await breaker.can_execute("test_tool")
    assert result is True
    assert isinstance(result, bool)


@pytest.mark.asyncio
async def test_can_execute_returns_false_when_open():
    """Test can_execute returns False (not 0) when circuit is open."""
    from unittest.mock import AsyncMock, MagicMock

    mock_redis = MagicMock()
    mock_redis.eval = AsyncMock(return_value=0)

    breaker = RedisCircuitBreaker(
        mock_redis,
        default_config=RedisCircuitBreakerConfig(failure_threshold=5),
    )

    result = await breaker.can_execute("test_tool")
    assert result is False
    assert isinstance(result, bool)


@pytest.mark.asyncio
async def test_record_success_transitions_to_closed():
    """Test record_success logs transition to closed state."""
    from unittest.mock import AsyncMock, MagicMock

    mock_redis = MagicMock()
    mock_redis.eval = AsyncMock(return_value=b"closed")

    breaker = RedisCircuitBreaker(
        mock_redis,
        default_config=RedisCircuitBreakerConfig(failure_threshold=5),
    )

    # Should trigger the log path for transitioning to closed
    await breaker.record_success("test_tool")
    mock_redis.eval.assert_called_once()


@pytest.mark.asyncio
async def test_record_success_stays_half_open():
    """Test record_success when staying in half_open state."""
    from unittest.mock import AsyncMock, MagicMock

    mock_redis = MagicMock()
    mock_redis.eval = AsyncMock(return_value=b"half_open")

    breaker = RedisCircuitBreaker(
        mock_redis,
        default_config=RedisCircuitBreakerConfig(failure_threshold=5),
    )

    await breaker.record_success("test_tool")
    mock_redis.eval.assert_called_once()


@pytest.mark.asyncio
async def test_record_failure_transitions_to_open():
    """Test record_failure logs transition to open state."""
    from unittest.mock import AsyncMock, MagicMock

    mock_redis = MagicMock()
    mock_redis.eval = AsyncMock(return_value=b"open")

    breaker = RedisCircuitBreaker(
        mock_redis,
        default_config=RedisCircuitBreakerConfig(failure_threshold=5),
    )

    # Should trigger the log path for transitioning to open
    await breaker.record_failure("test_tool")
    mock_redis.eval.assert_called_once()


@pytest.mark.asyncio
async def test_record_failure_stays_closed():
    """Test record_failure when staying in closed state."""
    from unittest.mock import AsyncMock, MagicMock

    mock_redis = MagicMock()
    mock_redis.eval = AsyncMock(return_value=b"closed")

    breaker = RedisCircuitBreaker(
        mock_redis,
        default_config=RedisCircuitBreakerConfig(failure_threshold=5),
    )

    await breaker.record_failure("test_tool")
    mock_redis.eval.assert_called_once()


@pytest.mark.asyncio
async def test_get_state_with_all_fields():
    """Test get_state returns all expected fields from Redis."""
    from unittest.mock import AsyncMock, MagicMock

    mock_redis = MagicMock()
    mock_redis.hgetall = AsyncMock(
        return_value={
            b"state": b"open",
            b"failure_count": b"5",
            b"success_count": b"0",
            b"opened_at": b"1000000000.5",
            b"half_open_calls": b"0",
        }
    )

    breaker = RedisCircuitBreaker(
        mock_redis,
        default_config=RedisCircuitBreakerConfig(
            failure_threshold=5,
            reset_timeout=60.0,
        ),
    )

    state = await breaker.get_state("test_tool")

    assert state["state"] == "open"
    assert state["failure_count"] == 5
    assert state["success_count"] == 0
    assert state["opened_at"] == 1000000000.5
    assert state["half_open_calls"] == 0
    assert state["config"]["failure_threshold"] == 5


@pytest.mark.asyncio
async def test_get_state_with_empty_redis_data():
    """Test get_state handles empty Redis data."""
    from unittest.mock import AsyncMock, MagicMock

    mock_redis = MagicMock()
    mock_redis.hgetall = AsyncMock(return_value={})

    breaker = RedisCircuitBreaker(
        mock_redis,
        default_config=RedisCircuitBreakerConfig(failure_threshold=5),
    )

    state = await breaker.get_state("test_tool")

    assert state["state"] == "closed"
    assert state["failure_count"] == 0
    assert state["success_count"] == 0
    assert state["opened_at"] is None
    assert state["half_open_calls"] == 0


@pytest.mark.asyncio
async def test_get_state_time_until_half_open_calculation():
    """Test get_state calculates time_until_half_open correctly."""
    import time
    from unittest.mock import AsyncMock, MagicMock

    mock_redis = MagicMock()
    # Set opened_at to now, so there's still time remaining
    current_time = time.time()
    mock_redis.hgetall = AsyncMock(
        return_value={
            b"state": b"open",
            b"failure_count": b"5",
            b"success_count": b"0",
            b"opened_at": str(current_time).encode(),
            b"half_open_calls": b"0",
        }
    )

    breaker = RedisCircuitBreaker(
        mock_redis,
        default_config=RedisCircuitBreakerConfig(
            failure_threshold=5,
            reset_timeout=60.0,
        ),
    )

    state = await breaker.get_state("test_tool")

    assert state["state"] == "open"
    assert state["time_until_half_open"] is not None
    # Should be close to reset_timeout since we just opened
    assert state["time_until_half_open"] > 0
    assert state["time_until_half_open"] <= 60.0


@pytest.mark.asyncio
async def test_get_state_time_until_half_open_expired():
    """Test get_state when time_until_half_open has expired."""
    from unittest.mock import AsyncMock, MagicMock

    mock_redis = MagicMock()
    # Set opened_at to a long time ago
    mock_redis.hgetall = AsyncMock(
        return_value={
            b"state": b"open",
            b"failure_count": b"5",
            b"success_count": b"0",
            b"opened_at": b"1000000000.0",  # Way in the past
            b"half_open_calls": b"0",
        }
    )

    breaker = RedisCircuitBreaker(
        mock_redis,
        default_config=RedisCircuitBreakerConfig(
            failure_threshold=5,
            reset_timeout=60.0,
        ),
    )

    state = await breaker.get_state("test_tool")

    assert state["state"] == "open"
    # Should be None since timeout has expired
    assert state["time_until_half_open"] is None


@pytest.mark.asyncio
async def test_get_all_states_with_multiple_tools():
    """Test get_all_states returns states for multiple tools."""
    from unittest.mock import AsyncMock, MagicMock

    mock_redis = MagicMock()

    # Mock scan_iter to return tool keys
    async def scan_iter_mock(pattern):
        yield b"circuitbreaker:tool1:state"
        yield b"circuitbreaker:tool2:state"

    mock_redis.scan_iter = scan_iter_mock
    mock_redis.hgetall = AsyncMock(
        return_value={
            b"state": b"closed",
            b"failure_count": b"0",
        }
    )

    breaker = RedisCircuitBreaker(
        mock_redis,
        default_config=RedisCircuitBreakerConfig(failure_threshold=5),
    )

    states = await breaker.get_all_states()

    assert "tool1" in states
    assert "tool2" in states


@pytest.mark.asyncio
async def test_get_all_states_handles_string_keys():
    """Test get_all_states handles string keys from Redis."""
    from unittest.mock import AsyncMock, MagicMock

    mock_redis = MagicMock()

    # Mock scan_iter to return string keys (not bytes)
    async def scan_iter_mock(pattern):
        yield "circuitbreaker:tool1:state"

    mock_redis.scan_iter = scan_iter_mock
    mock_redis.hgetall = AsyncMock(
        return_value={
            b"state": b"closed",
        }
    )

    breaker = RedisCircuitBreaker(
        mock_redis,
        default_config=RedisCircuitBreakerConfig(failure_threshold=5),
    )

    states = await breaker.get_all_states()

    assert "tool1" in states


@pytest.mark.asyncio
async def test_get_all_states_skips_malformed_keys():
    """Test get_all_states skips keys with wrong format."""
    from unittest.mock import AsyncMock, MagicMock

    mock_redis = MagicMock()

    # Mock scan_iter to return malformed keys
    async def scan_iter_mock(pattern):
        yield b"circuitbreaker:state"  # Missing tool name
        yield b"invalid"  # Too short
        yield b"circuitbreaker:tool1:state"  # Valid

    mock_redis.scan_iter = scan_iter_mock
    mock_redis.hgetall = AsyncMock(
        return_value={
            b"state": b"closed",
        }
    )

    breaker = RedisCircuitBreaker(
        mock_redis,
        default_config=RedisCircuitBreakerConfig(failure_threshold=5),
    )

    states = await breaker.get_all_states()

    # Only valid key should be included
    assert "tool1" in states


@pytest.mark.asyncio
async def test_reset_calls_delete():
    """Test reset deletes the state and failures keys."""
    from unittest.mock import AsyncMock, MagicMock

    mock_redis = MagicMock()
    mock_redis.delete = AsyncMock()

    breaker = RedisCircuitBreaker(
        mock_redis,
        default_config=RedisCircuitBreakerConfig(failure_threshold=5),
        key_prefix="test",
    )

    await breaker.reset("my_tool")

    mock_redis.delete.assert_called_once()
    call_args = mock_redis.delete.call_args[0]
    assert "test:my_tool:state" in call_args
    assert "test:my_tool:failures" in call_args


@pytest.mark.asyncio
async def test_reset_all_deletes_all_keys():
    """Test reset_all deletes all circuit breaker keys."""
    from unittest.mock import AsyncMock, MagicMock

    mock_redis = MagicMock()
    mock_redis.delete = AsyncMock()

    # Mock scan_iter
    async def scan_iter_mock(pattern):
        yield b"circuitbreaker:tool1:state"
        yield b"circuitbreaker:tool1:failures"
        yield b"circuitbreaker:tool2:state"

    mock_redis.scan_iter = scan_iter_mock

    breaker = RedisCircuitBreaker(
        mock_redis,
        default_config=RedisCircuitBreakerConfig(failure_threshold=5),
    )

    count = await breaker.reset_all()

    assert count == 3
    assert mock_redis.delete.call_count == 3


@pytest.mark.asyncio
async def test_executor_rejects_call_when_circuit_open_with_mocked_breaker():
    """Test executor rejects calls when can_execute returns False."""
    from unittest.mock import AsyncMock, MagicMock

    from chuk_tool_processor.execution.wrappers.redis_circuit_breaker import (
        RedisCircuitBreakerExecutor,
    )

    # Create a mock circuit breaker
    mock_breaker = MagicMock()
    mock_breaker.can_execute = AsyncMock(return_value=False)
    mock_breaker.get_state = AsyncMock(
        return_value={
            "state": "open",
            "failure_count": 5,
            "time_until_half_open": 30.0,
        }
    )

    # Create a mock executor
    mock_executor = MagicMock()

    executor = RedisCircuitBreakerExecutor(mock_executor, mock_breaker)

    call = ToolCall(tool="test_tool", arguments={})
    results = await executor.execute([call])

    assert len(results) == 1
    assert results[0].error is not None
    assert "circuit breaker" in results[0].error.lower()
    assert results[0].error_info is not None
    assert results[0].machine == "redis_circuit_breaker"

    # Verify executor was NOT called
    mock_executor.execute.assert_not_called()


@pytest.mark.asyncio
async def test_executor_handles_multiple_calls_mixed_circuits():
    """Test executor handles multiple calls where some circuits are open."""
    from datetime import UTC, datetime
    from unittest.mock import AsyncMock, MagicMock

    from chuk_tool_processor.execution.wrappers.redis_circuit_breaker import (
        RedisCircuitBreakerExecutor,
    )

    # Create a mock circuit breaker that allows tool2 but not tool1
    mock_breaker = MagicMock()

    async def can_execute_mock(tool):
        return tool != "tool1"  # tool1 is blocked

    mock_breaker.can_execute = AsyncMock(side_effect=can_execute_mock)
    mock_breaker.get_state = AsyncMock(
        return_value={
            "state": "open",
            "failure_count": 5,
            "time_until_half_open": 30.0,
        }
    )
    mock_breaker.record_success = AsyncMock()
    mock_breaker.record_failure = AsyncMock()

    # Create a mock executor that returns success
    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(
        return_value=[
            ToolResult(
                tool="tool2",
                result={"success": True},
                error=None,
                start_time=datetime.now(UTC),
                end_time=datetime.now(UTC),
                machine="test",
                pid=0,
            )
        ]
    )

    executor = RedisCircuitBreakerExecutor(mock_executor, mock_breaker)

    calls = [
        ToolCall(tool="tool1", arguments={}),
        ToolCall(tool="tool2", arguments={}),
    ]
    results = await executor.execute(calls)

    assert len(results) == 2
    # tool1 should be rejected
    assert results[0].error is not None
    assert "circuit breaker" in results[0].error.lower()
    # tool2 should succeed
    assert results[1].error is None


@pytest.mark.asyncio
async def test_executor_records_failure_on_exception():
    """Test executor records failure when underlying executor throws exception."""
    from unittest.mock import AsyncMock, MagicMock

    from chuk_tool_processor.execution.wrappers.redis_circuit_breaker import (
        RedisCircuitBreakerExecutor,
    )

    mock_breaker = MagicMock()
    mock_breaker.can_execute = AsyncMock(return_value=True)
    mock_breaker.record_failure = AsyncMock()

    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(side_effect=RuntimeError("Test exception"))

    executor = RedisCircuitBreakerExecutor(mock_executor, mock_breaker)

    call = ToolCall(tool="test_tool", arguments={})
    results = await executor.execute([call])

    assert len(results) == 1
    assert results[0].error is not None
    assert "Test exception" in results[0].error
    mock_breaker.record_failure.assert_called_once_with("test_tool")


@pytest.mark.asyncio
async def test_executor_records_failure_on_error_result_mocked():
    """Test executor records failure when result has error (mocked version)."""
    from datetime import UTC, datetime
    from unittest.mock import AsyncMock, MagicMock

    from chuk_tool_processor.execution.wrappers.redis_circuit_breaker import (
        RedisCircuitBreakerExecutor,
    )

    mock_breaker = MagicMock()
    mock_breaker.can_execute = AsyncMock(return_value=True)
    mock_breaker.record_failure = AsyncMock()
    mock_breaker.record_success = AsyncMock()

    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(
        return_value=[
            ToolResult(
                tool="test_tool",
                result=None,
                error="Tool failed",
                start_time=datetime.now(UTC),
                end_time=datetime.now(UTC),
                machine="test",
                pid=0,
            )
        ]
    )

    executor = RedisCircuitBreakerExecutor(mock_executor, mock_breaker)

    call = ToolCall(tool="test_tool", arguments={})
    results = await executor.execute([call])

    assert len(results) == 1
    mock_breaker.record_failure.assert_called_once_with("test_tool")
    mock_breaker.record_success.assert_not_called()


@pytest.mark.asyncio
async def test_executor_records_success_on_success_result_mocked():
    """Test executor records success when result has no error (mocked version)."""
    from datetime import UTC, datetime
    from unittest.mock import AsyncMock, MagicMock

    from chuk_tool_processor.execution.wrappers.redis_circuit_breaker import (
        RedisCircuitBreakerExecutor,
    )

    mock_breaker = MagicMock()
    mock_breaker.can_execute = AsyncMock(return_value=True)
    mock_breaker.record_success = AsyncMock()
    mock_breaker.record_failure = AsyncMock()

    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(
        return_value=[
            ToolResult(
                tool="test_tool",
                result={"success": True},
                error=None,
                start_time=datetime.now(UTC),
                end_time=datetime.now(UTC),
                machine="test",
                pid=0,
            )
        ]
    )

    executor = RedisCircuitBreakerExecutor(mock_executor, mock_breaker)

    call = ToolCall(tool="test_tool", arguments={})
    results = await executor.execute([call])

    assert len(results) == 1
    mock_breaker.record_success.assert_called_once_with("test_tool")
    mock_breaker.record_failure.assert_not_called()


@pytest.mark.asyncio
async def test_executor_passes_use_cache_when_available():
    """Test executor passes use_cache to underlying executor when supported."""
    from datetime import UTC, datetime
    from unittest.mock import AsyncMock, MagicMock

    from chuk_tool_processor.execution.wrappers.redis_circuit_breaker import (
        RedisCircuitBreakerExecutor,
    )

    mock_breaker = MagicMock()
    mock_breaker.can_execute = AsyncMock(return_value=True)
    mock_breaker.record_success = AsyncMock()

    mock_executor = MagicMock()
    mock_executor.use_cache = True  # Has use_cache attribute
    mock_executor.execute = AsyncMock(
        return_value=[
            ToolResult(
                tool="test_tool",
                result={"success": True},
                error=None,
                start_time=datetime.now(UTC),
                end_time=datetime.now(UTC),
                machine="test",
                pid=0,
            )
        ]
    )

    executor = RedisCircuitBreakerExecutor(mock_executor, mock_breaker)

    call = ToolCall(tool="test_tool", arguments={})
    await executor.execute([call], use_cache=False)

    # Check that execute was called with use_cache=False
    call_kwargs = mock_executor.execute.call_args[1]
    assert call_kwargs.get("use_cache") is False


@pytest.mark.asyncio
async def test_executor_get_circuit_states():
    """Test executor.get_circuit_states delegates to circuit breaker."""
    from unittest.mock import AsyncMock, MagicMock

    from chuk_tool_processor.execution.wrappers.redis_circuit_breaker import (
        RedisCircuitBreakerExecutor,
    )

    mock_breaker = MagicMock()
    mock_breaker.get_all_states = AsyncMock(
        return_value={
            "tool1": {"state": "open"},
            "tool2": {"state": "closed"},
        }
    )

    executor = RedisCircuitBreakerExecutor(MagicMock(), mock_breaker)

    states = await executor.get_circuit_states()

    assert "tool1" in states
    assert "tool2" in states
    mock_breaker.get_all_states.assert_called_once()


@pytest.mark.asyncio
async def test_executor_reset_circuit_mocked():
    """Test executor.reset_circuit delegates to circuit breaker (mocked version)."""
    from unittest.mock import AsyncMock, MagicMock

    from chuk_tool_processor.execution.wrappers.redis_circuit_breaker import (
        RedisCircuitBreakerExecutor,
    )

    mock_breaker = MagicMock()
    mock_breaker.reset = AsyncMock()

    executor = RedisCircuitBreakerExecutor(MagicMock(), mock_breaker)

    await executor.reset_circuit("test_tool")

    mock_breaker.reset.assert_called_once_with("test_tool")
