# tests/execution/wrappers/test_circuit_breaker.py
"""
Tests for the circuit breaker wrapper implementation.
"""

import asyncio
from datetime import UTC, datetime

import pytest

from chuk_tool_processor.execution.wrappers.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerExecutor,
    CircuitBreakerState,
    CircuitState,
)
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
class DummyExecutor:
    """Simple executor that can simulate failures."""

    def __init__(self):
        self.call_count = 0
        self.should_fail = False
        self.should_timeout = False

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


# --------------------------------------------------------------------------- #
# CircuitBreakerState tests
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_circuit_state_initial_state():
    """Test circuit breaker starts in CLOSED state."""
    config = CircuitBreakerConfig()
    state = CircuitBreakerState(config)

    assert state.state == CircuitState.CLOSED
    assert state.failure_count == 0
    assert state.success_count == 0
    assert state.opened_at is None


@pytest.mark.asyncio
async def test_circuit_opens_after_threshold_failures():
    """Test circuit opens after reaching failure threshold."""
    config = CircuitBreakerConfig(failure_threshold=3)
    state = CircuitBreakerState(config)

    # Record failures
    await state.record_failure()
    assert state.state == CircuitState.CLOSED
    await state.record_failure()
    assert state.state == CircuitState.CLOSED
    await state.record_failure()
    assert state.state == CircuitState.OPEN
    assert state.opened_at is not None


@pytest.mark.asyncio
async def test_circuit_half_open_after_timeout():
    """Test circuit transitions to HALF_OPEN after reset timeout."""
    config = CircuitBreakerConfig(failure_threshold=2, reset_timeout=0.1)
    state = CircuitBreakerState(config)

    # Open the circuit
    await state.record_failure()
    await state.record_failure()
    assert state.state == CircuitState.OPEN

    # Should not allow execution immediately
    can_execute = await state.can_execute()
    assert can_execute is False

    # Wait for reset timeout
    await asyncio.sleep(0.15)

    # Should transition to HALF_OPEN
    can_execute = await state.can_execute()
    assert can_execute is True
    assert state.state == CircuitState.HALF_OPEN


@pytest.mark.asyncio
async def test_circuit_closes_after_half_open_successes():
    """Test circuit closes after enough successes in HALF_OPEN."""
    config = CircuitBreakerConfig(
        failure_threshold=2,
        success_threshold=2,
        reset_timeout=0.1,
    )
    state = CircuitBreakerState(config)

    # Open the circuit
    await state.record_failure()
    await state.record_failure()
    assert state.state == CircuitState.OPEN

    # Wait and transition to HALF_OPEN
    await asyncio.sleep(0.15)
    await state.can_execute()
    assert state.state == CircuitState.HALF_OPEN

    # Record successes
    await state.record_success()
    assert state.state == CircuitState.HALF_OPEN
    await state.record_success()
    assert state.state == CircuitState.CLOSED
    assert state.failure_count == 0


@pytest.mark.asyncio
async def test_circuit_reopens_on_half_open_failure():
    """Test circuit reopens if failure occurs during HALF_OPEN."""
    config = CircuitBreakerConfig(failure_threshold=2, reset_timeout=0.1)
    state = CircuitBreakerState(config)

    # Open the circuit
    await state.record_failure()
    await state.record_failure()

    # Wait and transition to HALF_OPEN
    await asyncio.sleep(0.15)
    await state.can_execute()
    assert state.state == CircuitState.HALF_OPEN

    # Failure during HALF_OPEN should reopen
    await state.record_failure()
    assert state.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_circuit_half_open_max_calls():
    """Test HALF_OPEN limits concurrent calls."""
    config = CircuitBreakerConfig(
        failure_threshold=2,
        reset_timeout=0.1,
        half_open_max_calls=1,
    )
    state = CircuitBreakerState(config)

    # Open the circuit
    await state.record_failure()
    await state.record_failure()

    # Wait and transition to HALF_OPEN
    await asyncio.sleep(0.15)

    # First call should be allowed
    can_execute1 = await state.can_execute()
    assert can_execute1 is True

    # Second call should be blocked
    can_execute2 = await state.can_execute()
    assert can_execute2 is False


@pytest.mark.asyncio
async def test_circuit_release_half_open_slot():
    """Test releasing HALF_OPEN slots after call completes."""
    config = CircuitBreakerConfig(
        failure_threshold=2,
        reset_timeout=0.1,
        half_open_max_calls=1,
    )
    state = CircuitBreakerState(config)

    # Open and transition to HALF_OPEN
    await state.record_failure()
    await state.record_failure()
    await asyncio.sleep(0.15)

    # Take the slot
    await state.can_execute()

    # Release the slot
    await state.release_half_open_slot()

    # Should be able to take it again
    can_execute = await state.can_execute()
    assert can_execute is True


@pytest.mark.asyncio
async def test_circuit_get_state():
    """Test get_state returns correct state info."""
    config = CircuitBreakerConfig(failure_threshold=2, reset_timeout=10.0)
    state = CircuitBreakerState(config)

    # Initial state
    state_info = state.get_state()
    assert state_info["state"] == "closed"
    assert state_info["failure_count"] == 0
    assert state_info["success_count"] == 0
    assert state_info["time_until_half_open"] is None

    # After opening
    await state.record_failure()
    await state.record_failure()
    state_info = state.get_state()
    assert state_info["state"] == "open"
    assert state_info["time_until_half_open"] is not None


# --------------------------------------------------------------------------- #
# CircuitBreakerExecutor tests
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_executor_allows_calls_when_closed():
    """Test executor allows calls in CLOSED state."""
    exec_ = DummyExecutor()
    circuit = CircuitBreakerExecutor(exec_)

    call = ToolCall(tool="test_tool", arguments={})
    results = await circuit.execute([call])

    assert len(results) == 1
    assert results[0].error is None
    assert exec_.call_count == 1


@pytest.mark.asyncio
async def test_executor_opens_circuit_after_failures():
    """Test executor opens circuit after failure threshold."""
    exec_ = DummyExecutor()
    exec_.should_fail = True

    config = CircuitBreakerConfig(failure_threshold=3)
    circuit = CircuitBreakerExecutor(exec_, default_config=config)

    call = ToolCall(tool="test_tool", arguments={})

    # Execute until circuit opens
    await circuit.execute([call])
    await circuit.execute([call])
    results = await circuit.execute([call])

    # Circuit should be open
    assert exec_.call_count == 3

    # Next call should be rejected
    results = await circuit.execute([call])
    assert results[0].error is not None
    assert "circuit breaker" in results[0].error.lower()
    assert exec_.call_count == 3  # Not executed


@pytest.mark.asyncio
async def test_executor_half_open_recovery():
    """Test executor recovers through HALF_OPEN state."""
    exec_ = DummyExecutor()
    exec_.should_fail = True

    config = CircuitBreakerConfig(
        failure_threshold=2,
        success_threshold=2,
        reset_timeout=0.1,
    )
    circuit = CircuitBreakerExecutor(exec_, default_config=config)

    call = ToolCall(tool="test_tool", arguments={})

    # Open the circuit
    await circuit.execute([call])
    await circuit.execute([call])

    # Wait for reset timeout
    await asyncio.sleep(0.15)

    # Fix the executor and try again
    exec_.should_fail = False

    # First success
    results = await circuit.execute([call])
    assert results[0].error is None

    # Second success should close circuit
    results = await circuit.execute([call])
    assert results[0].error is None

    # Circuit should be closed now
    states = await circuit.get_circuit_states()
    assert states["test_tool"]["state"] == "closed"


@pytest.mark.asyncio
async def test_executor_per_tool_circuits():
    """Test executor maintains separate circuits per tool."""
    exec_ = DummyExecutor()
    config = CircuitBreakerConfig(failure_threshold=2)
    circuit = CircuitBreakerExecutor(exec_, default_config=config)

    call1 = ToolCall(tool="tool1", arguments={})
    call2 = ToolCall(tool="tool2", arguments={})

    # Fail tool1 but not tool2
    exec_.should_fail = True
    await circuit.execute([call1])
    await circuit.execute([call1])

    exec_.should_fail = False

    # tool1 circuit should be open
    results1 = await circuit.execute([call1])
    assert "circuit breaker" in results1[0].error.lower()

    # tool2 circuit should be closed
    results2 = await circuit.execute([call2])
    assert results2[0].error is None


@pytest.mark.asyncio
async def test_executor_per_tool_config():
    """Test executor respects per-tool configurations."""
    exec_ = DummyExecutor()
    exec_.should_fail = True

    tool_configs = {
        "sensitive_tool": CircuitBreakerConfig(failure_threshold=1),
        "robust_tool": CircuitBreakerConfig(failure_threshold=10),
    }
    circuit = CircuitBreakerExecutor(exec_, tool_configs=tool_configs)

    # sensitive_tool should open after 1 failure
    call1 = ToolCall(tool="sensitive_tool", arguments={})
    await circuit.execute([call1])
    results = await circuit.execute([call1])
    assert "circuit breaker" in results[0].error.lower()

    # robust_tool should still be closed after 1 failure
    call2 = ToolCall(tool="robust_tool", arguments={})
    await circuit.execute([call2])
    results = await circuit.execute([call2])
    assert results[0].error == "Simulated failure"  # Not circuit error


@pytest.mark.asyncio
async def test_executor_timeout_threshold():
    """Test executor treats slow calls as failures when timeout_threshold is set."""
    exec_ = DummyExecutor()

    config = CircuitBreakerConfig(
        failure_threshold=2,
        timeout_threshold=0.01,  # Very short timeout
    )
    circuit = CircuitBreakerExecutor(exec_, default_config=config)

    call = ToolCall(tool="test_tool", arguments={})

    # Simulate slow execution
    original_execute = exec_.execute

    async def slow_execute(*args, **kwargs):
        await asyncio.sleep(0.05)  # Slower than threshold
        return await original_execute(*args, **kwargs)

    exec_.execute = slow_execute

    # Execute twice - should open circuit due to timeout
    await circuit.execute([call])
    await circuit.execute([call])

    # Circuit should be open
    results = await circuit.execute([call])
    assert "circuit breaker" in results[0].error.lower()


@pytest.mark.asyncio
async def test_executor_reset_circuit():
    """Test manually resetting a circuit."""
    exec_ = DummyExecutor()
    exec_.should_fail = True

    config = CircuitBreakerConfig(failure_threshold=2)
    circuit = CircuitBreakerExecutor(exec_, default_config=config)

    call = ToolCall(tool="test_tool", arguments={})

    # Open the circuit
    await circuit.execute([call])
    await circuit.execute([call])

    # Verify circuit is open
    results = await circuit.execute([call])
    assert "circuit breaker" in results[0].error.lower()

    # Reset the circuit
    await circuit.reset_circuit("test_tool")

    # Fix the executor
    exec_.should_fail = False

    # Should be able to execute now
    results = await circuit.execute([call])
    assert results[0].error is None


@pytest.mark.asyncio
async def test_executor_empty_calls():
    """Test executor handles empty calls list."""
    exec_ = DummyExecutor()
    circuit = CircuitBreakerExecutor(exec_)

    results = await circuit.execute([])
    assert results == []


@pytest.mark.asyncio
async def test_executor_with_use_cache_parameter():
    """Test executor passes use_cache parameter to underlying executor."""
    exec_ = DummyExecutor()
    circuit = CircuitBreakerExecutor(exec_)

    call = ToolCall(tool="test_tool", arguments={})

    # Execute with use_cache=False
    results = await circuit.execute([call], use_cache=False)
    assert len(results) == 1


@pytest.mark.asyncio
async def test_executor_exception_handling():
    """Test executor handles exceptions from underlying executor."""
    exec_ = DummyExecutor()

    async def failing_execute(*args, **kwargs):
        raise ValueError("Simulated exception")

    exec_.execute = failing_execute

    config = CircuitBreakerConfig(failure_threshold=2)
    circuit = CircuitBreakerExecutor(exec_, default_config=config)

    call = ToolCall(tool="test_tool", arguments={})

    # First exception
    results = await circuit.execute([call])
    assert "exception" in results[0].error.lower()

    # Second exception should open circuit
    await circuit.execute([call])

    # Third call should be blocked by circuit
    results = await circuit.execute([call])
    assert "circuit breaker" in results[0].error.lower()


@pytest.mark.asyncio
async def test_get_circuit_states():
    """Test getting all circuit states."""
    exec_ = DummyExecutor()
    exec_.should_fail = True

    config = CircuitBreakerConfig(failure_threshold=2)
    circuit = CircuitBreakerExecutor(exec_, default_config=config)

    # Open circuit for tool1
    call1 = ToolCall(tool="tool1", arguments={})
    await circuit.execute([call1])
    await circuit.execute([call1])

    # Keep tool2 closed
    exec_.should_fail = False
    call2 = ToolCall(tool="tool2", arguments={})
    await circuit.execute([call2])

    # Get all states
    states = await circuit.get_circuit_states()

    assert "tool1" in states
    assert "tool2" in states
    assert states["tool1"]["state"] == "open"
    assert states["tool2"]["state"] == "closed"


@pytest.mark.asyncio
async def test_circuit_state_success_resets_failures_in_closed():
    """Test successful calls reset failure count in CLOSED state."""
    config = CircuitBreakerConfig(failure_threshold=5)
    state = CircuitBreakerState(config)

    # Record some failures
    await state.record_failure()
    await state.record_failure()
    assert state.failure_count == 2

    # Success should reset
    await state.record_success()
    assert state.failure_count == 0


@pytest.mark.asyncio
async def test_circuit_config_defaults():
    """Test CircuitBreakerConfig default values."""
    config = CircuitBreakerConfig()

    assert config.failure_threshold == 5
    assert config.success_threshold == 2
    assert config.reset_timeout == 60.0
    assert config.half_open_max_calls == 1
    assert config.timeout_threshold is None
