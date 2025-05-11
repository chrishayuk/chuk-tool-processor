"""
examples/demo_strategies_wrappers.py
====================================

Demonstrates, in one run:

  • In-process execution via ToolExecutor
  • Retry logic (fails once, then succeeds) via RetryableToolExecutor
  • Global rate-limit via RateLimitedToolExecutor
  • Result caching with 2-second TTL via CachingToolExecutor

Logging for the initial flaky failure is silenced, so the run is tidy.

Expected flow
-------------
1. Echo   – cache MISS → stored
2. Echo   – cache HIT  (machine == "cache")
3. wait 3 s – cache entry expires
4. Echo   – MISS again
5. Flaky  – first failure, one retry, success (result == 14)
6. Two rapid echo calls – rate-limit pauses second ≈1 s
"""
from __future__ import annotations

import asyncio
import logging
import time

from chuk_tool_processor.execution.tool_executor import ToolExecutor
from chuk_tool_processor.execution.wrappers.caching import (
    CachingToolExecutor,
    InMemoryCache,
)
from chuk_tool_processor.execution.wrappers.rate_limiting import (
    RateLimiter,
    RateLimitedToolExecutor,
)
from chuk_tool_processor.execution.wrappers.retry import (
    RetryConfig,
    RetryableToolExecutor,
)
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.registry.interface import ToolRegistryInterface

# --------------------------------------------------------------------------- #
# 0. Silence noisy ERROR log from first flaky failure
# --------------------------------------------------------------------------- #
lib_log = logging.getLogger(
    "chuk_tool_processor.execution.inprocess_strategy"
)
lib_log.setLevel(logging.CRITICAL)   # higher than ERROR
lib_log.propagate = False            # prevent bubbling to root


# --------------------------------------------------------------------------- #
# 1. Demo tools
# --------------------------------------------------------------------------- #
class EchoTool:
    async def execute(self, *, text: str):
        return f"echo: {text}"


class FlakyTool:
    """Fails once, succeeds on subsequent calls."""

    def __init__(self):
        self._called = False

    async def _aexecute(self, value: int):
        if not self._called:
            self._called = True
            raise RuntimeError("flaky failure – try again")
        return value * 2


# --------------------------------------------------------------------------- #
# 2. Registry with stateful FlakyTool instance
# --------------------------------------------------------------------------- #
class DemoRegistry(ToolRegistryInterface):
    def __init__(self):
        self._tools = {
            "echo": EchoTool,      # class: new instance per exec
            "flaky": FlakyTool(),  # instance: state survives retry
        }

    def get_tool(self, name):
        return self._tools.get(name)


# --------------------------------------------------------------------------- #
# 3. Build executor stack
# --------------------------------------------------------------------------- #
base_exec = ToolExecutor(DemoRegistry())

retry_exec = RetryableToolExecutor(
    base_exec,
    default_config=RetryConfig(
        max_retries=2,
        base_delay=0.2,  # short delay for demo
        jitter=False,
        retry_on_exceptions=[RuntimeError],
    ),
)

rate_limiter = RateLimiter(global_limit=1, global_period=1)  # 1 req / sec
rl_exec = RateLimitedToolExecutor(retry_exec, rate_limiter)

cache_exec = CachingToolExecutor(
    rl_exec,
    cache=InMemoryCache(default_ttl=2),  # 2-second TTL
    default_ttl=2,
)

echo_call  = ToolCall(tool="echo",  arguments={"text": "hi"})
flaky_call = ToolCall(tool="flaky", arguments={"value": 7})

# --------------------------------------------------------------------------- #
async def main():
    print("\n--- 1) Echo (MISS) ---------------------------------------")
    print((await cache_exec.execute([echo_call]))[0].model_dump())

    print("\n--- 2) Echo (HIT) ----------------------------------------")
    print((await cache_exec.execute([echo_call]))[0].model_dump())

    print("\n--- waiting 3 s for cache to expire ----------------------")
    await asyncio.sleep(3)

    print("\n--- 3) Echo (MISS again, TTL expired) --------------------")
    print((await cache_exec.execute([echo_call]))[0].model_dump())

    print("\n--- 4) Flaky tool (retry succeeds) -----------------------")
    print((await cache_exec.execute([flaky_call]))[0].model_dump())

    print("\n--- 5) Rate-limit demo -----------------------------------")
    start = time.monotonic()
    await cache_exec.execute([ToolCall(tool="echo", arguments={"text": "one"})])
    await cache_exec.execute([ToolCall(tool="echo", arguments={"text": "two"})])
    print(f"Elapsed ≈{time.monotonic() - start:.2f}s  (≥ 1 s by limit)")


if __name__ == "__main__":
    asyncio.run(main())
