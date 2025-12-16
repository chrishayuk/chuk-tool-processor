# chuk_tool_processor/discovery/__init__.py
"""Tool discovery and search capabilities.

This module provides intelligent tool search with:
- Tokenized OR semantics (any matching keyword scores)
- Synonym expansion ("gaussian" finds "normal", "cdf" finds "cumulative")
- Fuzzy matching fallback for typos
- Namespace aliasing ("math.normal_cdf" finds "normal_cdf")
- Always returns results (fallback to popular tools)
- Session boosting (recently used tools rank higher)

It also provides a base class for dynamic tool providers that allow LLMs
to discover and execute tools on-demand.
"""

from chuk_tool_processor.discovery.dynamic_provider import (
    BaseDynamicToolProvider,
    DynamicToolName,
)
from chuk_tool_processor.discovery.search import (
    SearchResult,
    SessionToolStats,
    ToolSearchEngine,
    extract_keywords,
    find_tool_by_alias,
    find_tool_exact,
    fuzzy_score,
    get_search_engine,
    levenshtein_distance,
    normalize_tool_name,
    score_token_match,
    search_tools,
    tokenize,
)
from chuk_tool_processor.discovery.searchable import SearchableTool
from chuk_tool_processor.discovery.synonyms import (
    DOMAIN_INDICATORS,
    STOPWORDS,
    SYNONYMS,
    compute_domain_penalty,
    detect_query_domain,
    detect_tool_domain,
    expand_with_synonyms,
)

__all__ = [
    # Dynamic provider
    "BaseDynamicToolProvider",
    "DynamicToolName",
    # Core search
    "ToolSearchEngine",
    "SearchResult",
    "SessionToolStats",
    "get_search_engine",
    "search_tools",
    "find_tool_exact",
    # Protocol
    "SearchableTool",
    # Token processing
    "tokenize",
    "extract_keywords",
    "expand_with_synonyms",
    # Scoring
    "score_token_match",
    "fuzzy_score",
    "levenshtein_distance",
    # Name aliasing
    "normalize_tool_name",
    "find_tool_by_alias",
    # Synonyms and domain detection
    "SYNONYMS",
    "DOMAIN_INDICATORS",
    "STOPWORDS",
    "detect_query_domain",
    "detect_tool_domain",
    "compute_domain_penalty",
]
