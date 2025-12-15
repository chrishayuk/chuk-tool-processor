# chuk_tool_processor/guards/__init__.py
"""Tool call guards - composable checks for tool execution.

Core guards:
- PreconditionGuard: Blocks premature parameterized tool calls
- BudgetGuard: Enforces discovery/execution budgets
- UnresolvedReferenceGuard: Detects unsubstituted placeholders
- RunawayGuard: Stops degenerate/saturated loops
- PerToolGuard: Limits per-tool call frequency

Runtime constitution guards:
- SchemaStrictnessGuard: Validates arguments against JSON schemas
- OutputSizeGuard: Prevents pathological payload sizes
- SensitiveDataGuard: Redacts or blocks secrets
- ConcurrencyGuard: Limits simultaneous in-flight calls
- NetworkPolicyGuard: SSRF defense and network policy
- SideEffectGuard: Controls read/write/destructive operations
- TimeoutBudgetGuard: Enforces wall-clock time limits
- RetrySafetyGuard: Controls retry behavior and backoff
- ProvenanceGuard: Tracks output attribution and lineage
- PlanShapeGuard: Detects pathological execution patterns

Composition:
- GuardChain: Composes multiple guards in sequence
"""

from chuk_tool_processor.guards.assumption_trace import (
    Assumption,
    AssumptionTraceGuard,
    AssumptionTraceGuardConfig,
    ToolCall,
    TraceViolation,
    inventory_sigma_constraints,
)
from chuk_tool_processor.guards.base import (
    BaseGuard,
    Guard,
    GuardResult,
    GuardVerdict,
)
from chuk_tool_processor.guards.budget import (
    BudgetGuard,
    BudgetGuardConfig,
    BudgetState,
)
from chuk_tool_processor.guards.chain import (
    GuardChain,
    GuardChainResult,
)
from chuk_tool_processor.guards.concurrency import (
    ConcurrencyConfig,
    ConcurrencyGuard,
    ConcurrencyLimitExceeded,
    ConcurrencyState,
)
from chuk_tool_processor.guards.models import (
    EnforcementLevel,
    ToolClassification,
)
from chuk_tool_processor.guards.network_policy import (
    DEFAULT_LOCALHOST_PATTERNS,
    DEFAULT_METADATA_IPS,
    DEFAULT_URL_ARGUMENT_NAMES,
    NetworkPolicyConfig,
    NetworkPolicyGuard,
    NetworkViolation,
    NetworkViolationType,
)
from chuk_tool_processor.guards.output_size import (
    OutputSizeConfig,
    OutputSizeGuard,
    SizeViolation,
    SizeViolationType,
    TruncatedResult,
    TruncationMode,
)
from chuk_tool_processor.guards.per_tool import (
    PerToolGuard,
    PerToolGuardConfig,
)
from chuk_tool_processor.guards.plan_shape import (
    PlanShapeConfig,
    PlanShapeGuard,
    PlanShapeState,
    PlanShapeViolation,
    PlanShapeViolationType,
    ToolCallSpec,
)
from chuk_tool_processor.guards.precondition import (
    PreconditionGuard,
    PreconditionGuardConfig,
)
from chuk_tool_processor.guards.provenance import (
    ProvenanceConfig,
    ProvenanceGuard,
    ProvenanceRecord,
)
from chuk_tool_processor.guards.retry_safety import (
    ErrorClass,
    RetrySafetyConfig,
    RetrySafetyGuard,
    RetryState,
)
from chuk_tool_processor.guards.runaway import (
    RunawayGuard,
    RunawayGuardConfig,
)
from chuk_tool_processor.guards.saturation import (
    SaturationGuard,
    SaturationGuardConfig,
)
from chuk_tool_processor.guards.schema_strictness import (
    SchemaStrictnessConfig,
    SchemaStrictnessGuard,
    SchemaValidationResult,
    SchemaViolation,
    SchemaViolationType,
)
from chuk_tool_processor.guards.sensitive_data import (
    RedactMode,
    SensitiveDataConfig,
    SensitiveDataGuard,
    SensitiveDataType,
    SensitiveMatch,
)
from chuk_tool_processor.guards.side_effect import (
    Environment,
    ExecutionMode,
    SideEffectClass,
    SideEffectConfig,
    SideEffectGuard,
)
from chuk_tool_processor.guards.timeout_budget import (
    BudgetStatus,
    DegradeAction,
    TimeoutBudgetConfig,
    TimeoutBudgetGuard,
    TimeoutBudgetState,
)
from chuk_tool_processor.guards.unresolved import (
    UnresolvedReferenceGuard,
    UnresolvedReferenceGuardConfig,
)

__all__ = [
    # Base
    "BaseGuard",
    "Guard",
    "GuardResult",
    "GuardVerdict",
    # Models
    "EnforcementLevel",
    "ToolClassification",
    # Chain
    "GuardChain",
    "GuardChainResult",
    # Original guards
    "BudgetGuard",
    "BudgetGuardConfig",
    "BudgetState",
    "PerToolGuard",
    "PerToolGuardConfig",
    "PreconditionGuard",
    "PreconditionGuardConfig",
    "RunawayGuard",
    "RunawayGuardConfig",
    "UnresolvedReferenceGuard",
    "UnresolvedReferenceGuardConfig",
    # Schema strictness
    "SchemaStrictnessGuard",
    "SchemaStrictnessConfig",
    "SchemaValidationResult",
    "SchemaViolation",
    "SchemaViolationType",
    # Output size
    "OutputSizeGuard",
    "OutputSizeConfig",
    "SizeViolation",
    "SizeViolationType",
    "TruncatedResult",
    "TruncationMode",
    # Sensitive data
    "SensitiveDataGuard",
    "SensitiveDataConfig",
    "SensitiveDataType",
    "SensitiveMatch",
    "RedactMode",
    # Concurrency
    "ConcurrencyGuard",
    "ConcurrencyConfig",
    "ConcurrencyState",
    "ConcurrencyLimitExceeded",
    # Network policy
    "NetworkPolicyGuard",
    "NetworkPolicyConfig",
    "NetworkViolation",
    "NetworkViolationType",
    "DEFAULT_METADATA_IPS",
    "DEFAULT_LOCALHOST_PATTERNS",
    "DEFAULT_URL_ARGUMENT_NAMES",
    # Side effect
    "SideEffectGuard",
    "SideEffectConfig",
    "SideEffectClass",
    "ExecutionMode",
    "Environment",
    # Timeout budget
    "TimeoutBudgetGuard",
    "TimeoutBudgetConfig",
    "TimeoutBudgetState",
    "BudgetStatus",
    "DegradeAction",
    # Retry safety
    "RetrySafetyGuard",
    "RetrySafetyConfig",
    "RetryState",
    "ErrorClass",
    # Provenance
    "ProvenanceGuard",
    "ProvenanceConfig",
    "ProvenanceRecord",
    # Plan shape
    "PlanShapeGuard",
    "PlanShapeConfig",
    "PlanShapeState",
    "PlanShapeViolation",
    "PlanShapeViolationType",
    "ToolCallSpec",
    # Saturation sanity
    "SaturationGuard",
    "SaturationGuardConfig",
    # Assumption-trace consistency
    "AssumptionTraceGuard",
    "AssumptionTraceGuardConfig",
    "Assumption",
    "ToolCall",
    "TraceViolation",
    "inventory_sigma_constraints",
]
