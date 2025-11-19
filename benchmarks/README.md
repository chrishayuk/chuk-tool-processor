# CHUK-Tool-Processor Benchmarks

Performance testing suite for chuk-tool-processor components.

## Benchmark Scripts

### `json_performance.py`
JSON serialization/deserialization performance testing comparing orjson vs stdlib json.

**Tests:**
- Serialization (dumps) of various tool call payloads
- Deserialization (loads) of tool responses
- Round-trip (dumps + loads) performance
- Batch operations (100 tool calls)

**Payload Types:**
- Simple tool calls (basic arguments)
- Complex tool calls (nested data structures)
- OpenAI-style tool_calls format
- Tool results with metadata
- Large batches (multi-agent scenarios)

**Run:**
```bash
# Without orjson (baseline)
python benchmarks/json_performance.py

# With orjson (optimized)
uv add --optional fast-json orjson
python benchmarks/json_performance.py
```

**Expected Results:**
- Serialization: 2-3x faster with orjson
- Deserialization: 2-3x faster with orjson
- Round-trip: 2-3x faster with orjson

### `tool_processing_benchmark.py`
End-to-end tool processor performance testing.

**Tests:**
- Simple tool call parsing (1000 iterations)
- Batch processing (3 tools, 500 iterations)
- JSON format parsing (1000 iterations)
- Concurrent processing (100 parallel requests)
- Memory usage analysis (1000 iterations)

**Run:**
```bash
# Without orjson (baseline)
python benchmarks/tool_processing_benchmark.py

# With orjson (optimized)
uv add --optional fast-json orjson
python benchmarks/tool_processing_benchmark.py
```

**Expected Results:**
- Simple parsing: 500-1500 ops/sec
- Batch processing: 1000-3000 calls/sec
- Concurrent: 100+ batches/sec
- Memory: <50 MB peak usage

## Installation

### Baseline (stdlib json)
```bash
# No additional dependencies needed
python benchmarks/json_performance.py
python benchmarks/tool_processing_benchmark.py
```

### Optimized (with orjson)
```bash
# Install orjson
uv add --optional fast-json orjson

# Or using pip
pip install 'chuk-tool-processor[fast-json]'

# Run benchmarks
python benchmarks/json_performance.py
python benchmarks/tool_processing_benchmark.py
```

## Comparing Performance

### Run both versions
```bash
# Baseline
echo "=== BASELINE (stdlib json) ===" > baseline_results.txt
python benchmarks/json_performance.py >> baseline_results.txt
python benchmarks/tool_processing_benchmark.py >> baseline_results.txt

# Install orjson
uv add --optional fast-json orjson

# Optimized
echo "=== OPTIMIZED (orjson) ===" > optimized_results.txt
python benchmarks/json_performance.py >> optimized_results.txt
python benchmarks/tool_processing_benchmark.py >> optimized_results.txt

# Compare
diff baseline_results.txt optimized_results.txt
```

## Results Directory

Benchmark results are automatically saved to `benchmarks/results/` with timestamps (if enabled).

## Interpreting Results

### JSON Performance
- **Speedup < 1.5x**: Possible issue with orjson installation
- **Speedup 2-3x**: Expected performance improvement
- **Speedup > 3x**: Excellent, especially for complex payloads

### Tool Processing
- **Simple parsing**: Should be fast (>500 ops/sec)
- **Batch processing**: Tests parallel execution
- **Concurrent**: Tests asyncio performance
- **Memory**: Should be stable (<100 MB for 1000 iterations)

### Warning Signs
- Memory usage growing unbounded: Possible leak
- Throughput degrading over time: Performance regression
- orjson slower than stdlib: Installation or compatibility issue

## CI Integration

Add to CI pipeline:
```yaml
- name: Run benchmarks (baseline)
  run: |
    python benchmarks/json_performance.py
    python benchmarks/tool_processing_benchmark.py

- name: Install orjson
  run: uv add --optional fast-json orjson

- name: Run benchmarks (optimized)
  run: |
    python benchmarks/json_performance.py
    python benchmarks/tool_processing_benchmark.py
```

## Development

### Adding New Benchmarks

```python
import time
from chuk_tool_processor.utils import fast_json

def benchmark_new_operation(iterations=1000):
    """Benchmark a new operation."""
    print(f"Running {iterations} iterations...")

    start = time.perf_counter()
    for _ in range(iterations):
        # Your operation here
        pass
    elapsed = time.perf_counter() - start

    throughput = iterations / elapsed
    print(f"Time: {elapsed:.4f}s")
    print(f"Throughput: {throughput:,.0f} ops/sec")

    return elapsed, throughput
```

## Performance Tips

1. **Always use fast_json module** for JSON operations instead of direct `import json`
2. **Install orjson in production** for 2-3x performance boost
3. **Monitor memory usage** for long-running processes
4. **Use batch processing** for multiple tool calls
5. **Enable concurrent processing** for I/O-bound tools

## Optimization Impact

With orjson installed:
- **JSON operations**: 2-3x faster
- **Tool parsing**: 20-30% faster overall
- **Batch processing**: 30-40% faster
- **Memory**: Similar or slightly better
- **Throughput**: 2-3x more tool calls/sec

## Troubleshooting

### orjson not detected
```bash
# Verify installation
python -c "import orjson; print(orjson.__version__)"

# Reinstall if needed
uv add --optional fast-json orjson
```

### Benchmark crashes
```bash
# Check dependencies
uv sync

# Run with error output
python benchmarks/json_performance.py 2>&1 | tee error.log
```

### Low performance
- Check CPU usage during benchmark
- Verify no other processes competing for resources
- Try with different iteration counts
- Compare against baseline results
