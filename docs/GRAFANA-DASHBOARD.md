# Grafana Dashboard Guide

This guide shows what the CHUK Tool Processor Grafana dashboard displays and how to use it.

## Dashboard Overview

The dashboard (`docs/grafana-dashboard.json`) provides complete observability for CHUK Tool Processor in a single screen with 10 panels.

## Dashboard Panels

### 1. Total Calls/Sec (Gauge)
**Shows**: Current rate of tool calls per second across all tools

**PromQL Query**:
```promql
sum(rate(tool_executions_total[1m]))
```

**What it tells you**: How busy your tool processor is right now
- **High values**: Heavy usage, ensure adequate resources
- **Low/zero values**: System idle or potential issues
- **Sudden drops**: May indicate problems upstream

---

### 2. Error Rate % (Gauge)
**Shows**: Percentage of tool calls failing

**PromQL Query**:
```promql
(sum(rate(tool_executions_total{status="error"}[5m])) /
 sum(rate(tool_executions_total[5m]))) * 100
```

**What it tells you**: Overall system health
- **< 1%**: Healthy system
- **1-5%**: Investigate error patterns
- **> 5%**: Critical - check errors immediately

---

### 3. Cache Hit Rate % (Gauge)
**Shows**: Percentage of tool calls served from cache

**PromQL Query**:
```promql
(sum(rate(tool_cache_operations_total{result="hit"}[5m])) /
 sum(rate(tool_cache_operations_total{operation="lookup"}[5m]))) * 100
```

**What it tells you**: Cache effectiveness
- **High (>60%)**: Cache working well, saving resources
- **Low (<20%)**: Consider increasing cache TTL or checking cache invalidation
- **Zero**: Cache disabled or no repeated calls

---

### 4. Circuit Breaker Status (Gauge)
**Shows**: Current state of circuit breakers (0=CLOSED, 1=OPEN, 2=HALF_OPEN)

**PromQL Query**:
```promql
max(tool_circuit_breaker_state)
```

**What it tells you**: System resilience status
- **0 (CLOSED)**: All tools healthy
- **1 (OPEN)**: One or more tools are circuit-broken (too many failures)
- **2 (HALF_OPEN)**: Testing recovery

**Action**: If showing OPEN, check which tool is failing and investigate

---

### 5. Tool Call Rate (Time Series Graph)
**Shows**: Tool execution rate over time, broken down by tool name

**PromQL Query**:
```promql
sum by(tool) (rate(tool_executions_total[1m]))
```

**What it tells you**: Tool usage patterns
- Identify which tools are most used
- Spot usage spikes (potential scaling issues)
- Correlate with error rates to find problematic tools

---

### 6. Latency Percentiles (Stat Panels)
**Shows**: P50, P95, and P99 latency for tool executions

**PromQL Queries**:
```promql
# P50 (Median)
histogram_quantile(0.5,
  sum by(le) (rate(tool_execution_duration_seconds_bucket[5m])))

# P95
histogram_quantile(0.95,
  sum by(le) (rate(tool_execution_duration_seconds_bucket[5m])))

# P99
histogram_quantile(0.99,
  sum by(le) (rate(tool_execution_duration_seconds_bucket[5m])))
```

**What it tells you**: Performance characteristics
- **P50**: Typical execution time
- **P95**: 95% of calls complete within this time
- **P99**: Worst-case latency (outliers)

**Target values** (depends on your tools):
- P50: < 100ms for local tools, < 500ms for API tools
- P95: < 500ms for local tools, < 2s for API tools
- P99: < 1s for local tools, < 5s for API tools

---

### 7. Success vs Error Rate (Time Series Graph)
**Shows**: Success and error rates over time

**PromQL Queries**:
```promql
# Success rate
sum(rate(tool_executions_total{status="success"}[1m]))

# Error rate
sum(rate(tool_executions_total{status="error"}[1m]))
```

**What it tells you**: System health trends
- Spot when errors started
- Correlate with deployments or external events
- See if retries are helping (errors should be lower than without retries)

---

### 8. Cache Hit Rate by Tool (Time Series Graph)
**Shows**: Cache hit rate for each tool over time

**PromQL Query**:
```promql
sum by(tool) (rate(tool_cache_operations_total{result="hit"}[5m])) /
sum by(tool) (rate(tool_cache_operations_total{operation="lookup"}[5m]))
```

**What it tells you**: Which tools benefit most from caching
- **High hit rates**: Tool has stable, cacheable results
- **Low hit rates**: Results change frequently or cache TTL too short
- **Zero hit rate**: Tool not using cache or unique arguments every time

**Optimization**: Increase cache TTL for tools with high hit rates

---

### 9. Retry Rate % (Gauge)
**Shows**: Percentage of tool calls that required retries

**PromQL Query**:
```promql
(sum(rate(tool_retry_attempts_total{attempt!="0"}[5m])) /
 sum(rate(tool_executions_total[5m]))) * 100
```

**What it tells you**: Reliability of tools and external dependencies
- **< 5%**: Normal transient errors
- **5-15%**: Flaky tools or unreliable dependencies
- **> 15%**: Critical reliability issues

**Action**: High retry rates mean:
- External APIs are flaky (consider circuit breaker)
- Network issues
- Tools need better error handling

---

### 10. Top 10 Tools (Table)
**Shows**: Most active tools with their metrics

**PromQL Queries**:
```promql
# Total calls
topk(10, sum by(tool) (rate(tool_executions_total[5m])))

# Error count
topk(10, sum by(tool) (rate(tool_executions_total{status="error"}[5m])))

# Average duration
topk(10,
  sum by(tool) (rate(tool_execution_duration_seconds_sum[5m])) /
  sum by(tool) (rate(tool_execution_duration_seconds_count[5m])))
```

**What it tells you**: Tool hotspots
- Which tools are most frequently used
- Which tools have the most errors
- Which tools are slowest

**Use cases**:
- Prioritize optimization efforts
- Identify candidates for caching
- Find tools that need better error handling

---

## Example Dashboard State

Based on live metrics from a running system:

```
Total Calls/Sec:     15.2 calls/sec
Error Rate:          2.1%
Cache Hit Rate:      45.6%
Circuit Breaker:     0 (CLOSED - Healthy)

Latency Percentiles:
  P50: 68ms
  P95: 234ms
  P99: 511ms

Top Tools:
1. calculator     - 9.2 calls/sec, 0% errors, 42ms avg
2. weather        - 3.1 calls/sec, 0% errors, 95ms avg
3. database       - 1.8 calls/sec, 5% errors, 178ms avg
4. api_call       - 0.9 calls/sec, 0% errors, 112ms avg
5. slow_tool      - 0.2 calls/sec, 0% errors, 687ms avg

Cache Performance:
- weather:    87% hit rate (highly cacheable)
- database:   72% hit rate (good caching)
- calculator: 0% hit rate (unique calculations)

Retry Rate: 3.2% (normal transient failures)
```

## Common Patterns

### Pattern 1: Healthy System
- Error rate < 1%
- Cache hit rate > 40%
- Circuit breaker: CLOSED
- Retry rate < 5%
- P99 latency within acceptable range

### Pattern 2: Tool Overload
- High call rate (>100 calls/sec)
- Increasing P99 latency
- Rising error rate
- **Action**: Scale up concurrency or add rate limiting

### Pattern 3: External Dependency Failure
- Specific tool error rate >10%
- Circuit breaker: OPEN
- High retry rate for that tool
- **Action**: Check external service health, circuit breaker prevents cascading failure

### Pattern 4: Poor Cache Configuration
- Low cache hit rate (<20%)
- High P50 latency
- **Action**: Increase cache TTL or review cache key generation

### Pattern 5: System Recovery
- Circuit breaker: HALF_OPEN
- Error rate decreasing
- Retry rate elevated but declining
- **Action**: Monitor - system is auto-recovering

## Import Instructions

1. **Configure Prometheus scraping:**
   ```yaml
   # prometheus.yml
   scrape_configs:
     - job_name: 'chuk-tool-processor'
       scrape_interval: 15s
       static_configs:
         - targets: ['your-app:9090']  # Your metrics port
   ```

2. **Import dashboard:**
   - Grafana → Dashboards → Import
   - Upload `docs/grafana-dashboard.json`
   - Select your Prometheus data source

3. **Adjust time range:**
   - Default: Last 1 hour
   - Recommendation: Last 15 minutes for active monitoring
   - Auto-refresh: Every 5 seconds

## Alerting Recommendations

Based on this dashboard, configure alerts for:

1. **Error Rate Alert**
   ```promql
   (sum(rate(tool_executions_total{status="error"}[5m])) /
    sum(rate(tool_executions_total[5m]))) > 0.05
   ```
   Fire when error rate > 5%

2. **Circuit Breaker Alert**
   ```promql
   max(tool_circuit_breaker_state) == 1
   ```
   Fire when any circuit breaker opens

3. **Latency Alert**
   ```promql
   histogram_quantile(0.99,
     sum by(le) (rate(tool_execution_duration_seconds_bucket[5m]))) > 5.0
   ```
   Fire when P99 latency > 5 seconds

4. **Retry Rate Alert**
   ```promql
   (sum(rate(tool_retry_attempts_total{attempt!="0"}[5m])) /
    sum(rate(tool_executions_total[5m]))) > 0.15
   ```
   Fire when retry rate > 15%

## Screenshot

![Grafana Dashboard](img/grafana-dashboard.png)

_Screenshot shows all 10 panels with live data from a running system_

## Next Steps

1. **After importing**: Let it run for 5-10 minutes to see patterns
2. **Set baselines**: Note typical values for your workload
3. **Configure alerts**: Based on your SLOs
4. **Team review**: Share dashboard link with ops team
5. **Incident response**: Bookmark for troubleshooting

---

For more information:
- [OBSERVABILITY.md](../OBSERVABILITY.md) - Complete observability guide
- [CONFIGURATION.md](CONFIGURATION.md) - Tuning parameters
- [ERRORS.md](ERRORS.md) - Error handling guide
