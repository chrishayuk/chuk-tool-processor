# chuk_tool_processor/discovery/search.py
"""Intelligent tool search with synonym expansion, fuzzy matching, and OR semantics.

This module provides robust tool discovery that matches how LLMs naturally describe
tools they're looking for, rather than requiring exact substring matches.

Key features:
1. Tokenized OR semantics - any matching token scores
2. Synonym expansion - "gaussian" finds "normal", "cdf" finds "cumulative"
3. Fuzzy matching fallback - handles typos and close matches
4. Always returns something - popular tools when nothing else matches
5. Namespace aliasing - "math.normal_cdf" finds "normal_cdf"
6. Two-stage search - high precision first, then expand if needed
7. Session boosting - recently used tools rank higher
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Generic, TypeVar

from chuk_tool_processor.discovery.searchable import (
    get_tool_description,
    get_tool_parameters,
)
from chuk_tool_processor.discovery.synonyms import (
    STOPWORDS,
    compute_domain_penalty,
    detect_query_domain,
    detect_tool_domain,
    expand_with_synonyms,
)

logger = logging.getLogger(__name__)


# Type variable for tools - any object with name/namespace attributes
T = TypeVar("T")


# ============================================================================
# Search Result Model
# ============================================================================


@dataclass
class SearchResult(Generic[T]):
    """Result of a tool search with scoring information.

    Generic over the tool type T, allowing different tool representations.
    """

    tool: T
    score: float
    match_reasons: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        """Get tool name."""
        return getattr(self.tool, "name", "")

    @property
    def namespace(self) -> str:
        """Get tool namespace."""
        return getattr(self.tool, "namespace", "")

    @property
    def description(self) -> str | None:
        """Get tool description."""
        return get_tool_description(self.tool)


# ============================================================================
# Token Processing
# ============================================================================


def tokenize(text: str) -> list[str]:
    """Tokenize text into searchable terms.

    Handles:
    - snake_case: normal_cdf -> [normal, cdf]
    - camelCase: normalCdf -> [normal, cdf]
    - kebab-case: normal-cdf -> [normal, cdf]
    - dot.notation: math.normal -> [math, normal]
    - Numbers preserved: sin2 -> [sin, 2]

    Args:
        text: Text to tokenize

    Returns:
        List of lowercase tokens
    """
    if not text:
        return []

    # Normalize to lowercase
    text = text.lower()

    # Split on common separators (underscore, dash, dot, space)
    parts = re.split(r"[_\-.\s]+", text)

    tokens = []
    for part in parts:
        if not part:
            continue

        # Split camelCase: normalCdf -> normal, Cdf
        camel_split = re.sub(r"([a-z])([A-Z])", r"\1 \2", part).lower().split()
        for token in camel_split:
            # Further split on number boundaries: sin2 -> sin, 2
            number_split = re.split(r"(\d+)", token)
            for t in number_split:
                if t and len(t) >= 2:  # Minimum token length
                    tokens.append(t)

    return tokens


def extract_keywords(query: str) -> list[str]:
    """Extract meaningful keywords from a natural language query.

    Removes stopwords and extracts the meaningful search terms.

    Args:
        query: Natural language query

    Returns:
        List of keywords (without stopwords)
    """
    tokens = tokenize(query)
    keywords = [t for t in tokens if t not in STOPWORDS]

    # If all tokens were stopwords, return original tokens
    return keywords if keywords else tokens


# ============================================================================
# Scoring Functions
# ============================================================================


def score_token_match(
    query_tokens: set[str],
    tool_name: str,
    tool_description: str | None,
    tool_namespace: str,
    param_names: list[str] | None = None,
) -> tuple[float, list[str]]:
    """Score a tool based on token overlap with query.

    Args:
        query_tokens: Set of query tokens (possibly expanded with synonyms)
        tool_name: Name of the tool
        tool_description: Tool description
        tool_namespace: Tool namespace
        param_names: Optional list of parameter names

    Returns:
        (score, match_reasons) tuple.

    Scoring:
    - Name token exact match: 10 points
    - Name token prefix match: 5 points
    - Description token match: 3 points
    - Namespace match: 2 points
    - Parameter name match: 1 point
    """
    score = 0.0
    reasons = []

    # Tokenize tool attributes
    name_tokens = set(tokenize(tool_name))
    desc_tokens = set(tokenize(tool_description or ""))
    ns_tokens = set(tokenize(tool_namespace))
    param_tokens: set[str] = set()
    if param_names:
        for p in param_names:
            param_tokens.update(tokenize(p))

    # Check each query token
    for qt in query_tokens:
        # Exact name match (highest value)
        if qt in name_tokens:
            score += 10
            reasons.append(f"name:'{qt}'")

        # Prefix match in name (e.g., "norm" matches "normal")
        elif any(nt.startswith(qt) or qt.startswith(nt) for nt in name_tokens):
            score += 5
            reasons.append(f"name_prefix:'{qt}'")

        # Description match
        if qt in desc_tokens:
            score += 3
            reasons.append(f"desc:'{qt}'")

        # Namespace match
        if qt in ns_tokens:
            score += 2
            reasons.append(f"ns:'{qt}'")

        # Parameter name match
        if qt in param_tokens:
            score += 1
            reasons.append(f"param:'{qt}'")

    return score, reasons


def fuzzy_score(query: str, target: str, threshold: float = 0.6) -> float:
    """Calculate fuzzy match score using sequence matching.

    Args:
        query: Query string
        target: Target string to match against
        threshold: Minimum similarity threshold

    Returns:
        Score between 0 and 1, or 0 if below threshold.
    """
    if not query or not target:
        return 0.0

    ratio = SequenceMatcher(None, query.lower(), target.lower()).ratio()
    return ratio if ratio >= threshold else 0.0


def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein edit distance between two strings.

    Args:
        s1: First string
        s2: Second string

    Returns:
        Number of edits required to transform s1 into s2
    """
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


# ============================================================================
# Name Aliasing
# ============================================================================


def normalize_tool_name(name: str) -> set[str]:
    """Generate normalized variants of a tool name for matching.

    Args:
        name: Tool name to normalize

    Returns:
        Set of name variants

    Examples:
    - normal_cdf -> {normal_cdf, normalcdf, normal-cdf, normalCdf}
    - math.normal_cdf -> {normal_cdf, math.normal_cdf, ...}
    """
    variants = {name.lower()}

    # Remove namespace prefix if present
    if "." in name:
        base_name = name.split(".")[-1]
        variants.add(base_name.lower())

    # Generate case variants
    base = name.split(".")[-1] if "." in name else name

    # snake_case to other forms
    variants.add(base.lower().replace("_", ""))  # normalcdf
    variants.add(base.lower().replace("_", "-"))  # normal-cdf

    # Convert to camelCase
    parts = base.split("_")
    if len(parts) > 1:
        camel = parts[0].lower() + "".join(p.capitalize() for p in parts[1:])
        variants.add(camel)  # normalCdf

    return variants


def find_tool_by_alias(query_name: str, tools: list[T]) -> T | None:
    """Find a tool by name, checking aliases and normalized forms.

    Args:
        query_name: Name to search for
        tools: List of tools to search

    Returns:
        Matching tool or None
    """
    query_variants = normalize_tool_name(query_name)

    for tool in tools:
        tool_name = getattr(tool, "name", "")
        tool_namespace = getattr(tool, "namespace", "")

        tool_variants = normalize_tool_name(tool_name)

        # Check if any query variant matches any tool variant
        if query_variants & tool_variants:
            return tool

        # Also check with namespace prefix
        full_name_variants = normalize_tool_name(f"{tool_namespace}.{tool_name}")
        if query_variants & full_name_variants:
            return tool

    return None


# ============================================================================
# Session Tracking
# ============================================================================


@dataclass
class SessionToolStats:
    """Statistics for a tool's usage in the current session."""

    name: str
    call_count: int = 0
    success_count: int = 0
    last_used_turn: int = 0

    @property
    def success_rate(self) -> float:
        """Calculate success rate of tool calls."""
        return self.success_count / self.call_count if self.call_count > 0 else 0.0


# ============================================================================
# Main Search Engine
# ============================================================================


class ToolSearchEngine(Generic[T]):
    """Intelligent tool search engine with caching, ranking, and session awareness.

    Generic over tool type T - works with any object that has name/namespace.

    Features:
    - Two-stage search: high precision first, then expand
    - Session boosting: recently/successfully used tools rank higher
    - Configurable scoring weights
    """

    # Scoring weights (can be tuned)
    WEIGHT_NAME_EXACT = 10.0
    WEIGHT_NAME_PREFIX = 5.0
    WEIGHT_DESC = 3.0
    WEIGHT_NAMESPACE = 2.0
    WEIGHT_PARAM = 1.0

    # Session boost weights
    BOOST_RECENT_USE = 2.0  # Boost for tools used recently
    BOOST_SUCCESS = 1.5  # Additional boost for successful use
    BOOST_CALL_COUNT = 0.5  # Small boost per successful call
    BOOST_DECAY_TURNS = 5  # How many turns before boost decays

    def __init__(self) -> None:
        self._tool_cache: list[T] | None = None
        self._search_index: dict[str, set[str]] | None = None  # tool_name -> searchable tokens

        # Session tracking
        self._session_stats: dict[str, SessionToolStats] = {}
        self._current_turn: int = 0

    def set_tools(self, tools: list[T]) -> None:
        """Cache tools and build search index.

        Args:
            tools: List of tools to index
        """
        self._tool_cache = tools
        self._build_search_index()

    # =========================================================================
    # Session Tracking
    # =========================================================================

    def record_tool_use(
        self,
        tool_name: str,
        success: bool = True,
    ) -> None:
        """Record a tool usage in the current session.

        This information is used to boost frequently/successfully used tools
        in search results.

        Args:
            tool_name: Name of the tool that was used
            success: Whether the tool call was successful
        """
        if tool_name not in self._session_stats:
            self._session_stats[tool_name] = SessionToolStats(name=tool_name)

        stats = self._session_stats[tool_name]
        stats.call_count += 1
        if success:
            stats.success_count += 1
        stats.last_used_turn = self._current_turn

        logger.debug(
            f"Recorded tool use: {tool_name} (calls={stats.call_count}, success_rate={stats.success_rate:.0%})"
        )

    def advance_turn(self) -> None:
        """Advance the session turn counter.

        Call this at the start of each new user prompt to track recency.
        """
        self._current_turn += 1
        logger.debug(f"Advanced to turn {self._current_turn}")

    def reset_session(self) -> None:
        """Reset session statistics (e.g., for a new conversation)."""
        self._session_stats.clear()
        self._current_turn = 0
        logger.debug("Session statistics reset")

    def get_session_boost(self, tool_name: str) -> float:
        """Calculate session-based score boost for a tool.

        Considers:
        - Recency of use (decays over turns)
        - Success rate
        - Call count (with diminishing returns)

        Args:
            tool_name: Name of the tool

        Returns:
            Boost multiplier (1.0 = no boost, >1.0 = boosted)
        """
        if tool_name not in self._session_stats:
            return 1.0

        stats = self._session_stats[tool_name]

        # Base boost for having been used at all
        boost = 1.0

        # Recency boost (decays with turns since last use)
        turns_since_use = self._current_turn - stats.last_used_turn
        if turns_since_use < self.BOOST_DECAY_TURNS:
            recency_factor = 1.0 - (turns_since_use / self.BOOST_DECAY_TURNS)
            boost += self.BOOST_RECENT_USE * recency_factor

        # Success rate boost
        if stats.call_count > 0:
            boost += self.BOOST_SUCCESS * stats.success_rate

        # Call count boost (logarithmic to avoid runaway boosting)
        if stats.success_count > 0:
            boost += self.BOOST_CALL_COUNT * math.log1p(stats.success_count)

        return boost

    def get_session_stats(self, tool_name: str) -> SessionToolStats | None:
        """Get session statistics for a tool.

        Args:
            tool_name: Name of the tool

        Returns:
            Session stats or None if tool hasn't been used
        """
        return self._session_stats.get(tool_name)

    def _build_search_index(self) -> None:
        """Build inverted index for fast searching."""
        if not self._tool_cache:
            self._search_index = {}
            return

        self._search_index = {}
        for tool in self._tool_cache:
            tool_name = getattr(tool, "name", "")
            tool_desc = get_tool_description(tool)
            tool_ns = getattr(tool, "namespace", "")
            tool_params = get_tool_parameters(tool)

            # Collect all searchable tokens for this tool
            tokens: set[str] = set()

            # Name tokens (with synonyms)
            name_tokens = tokenize(tool_name)
            tokens.update(name_tokens)
            tokens.update(expand_with_synonyms(name_tokens))

            # Description tokens (with synonyms)
            if tool_desc:
                desc_tokens = tokenize(tool_desc)
                tokens.update(desc_tokens)
                tokens.update(expand_with_synonyms(desc_tokens))

            # Namespace tokens
            tokens.update(tokenize(tool_ns))

            # Parameter names
            if tool_params and "properties" in tool_params:
                for param_name in tool_params["properties"]:
                    tokens.update(tokenize(param_name))

            # Name variants (aliases)
            tokens.update(normalize_tool_name(tool_name))

            self._search_index[tool_name] = tokens

    def search(
        self,
        query: str,
        tools: list[T] | None = None,
        limit: int = 10,
        min_score: float = 0.0,
        use_session_boost: bool = True,
    ) -> list[SearchResult[T]]:
        """Search for tools matching the query using two-stage search.

        Stage 1 (High Precision): Exact and prefix token matches only
        Stage 2 (Expanded): Synonym expansion and fuzzy matching

        Session boosting is applied to rank recently/successfully used tools higher.

        Args:
            query: Natural language search query
            tools: Tools to search (uses cache if None)
            limit: Maximum results to return
            min_score: Minimum score threshold (0 = return everything)
            use_session_boost: Whether to apply session-based boosting

        Returns:
            List of SearchResult sorted by score (highest first)
        """
        if tools is not None:
            search_tools = tools
        elif self._tool_cache is not None:
            search_tools = self._tool_cache
        else:
            return []

        if not search_tools:
            return []

        # Extract keywords from query
        keywords = extract_keywords(query)
        if not keywords:
            keywords = tokenize(query)

        if not keywords:
            return self._fallback_results(search_tools, limit, use_session_boost)

        logger.debug(f"Search query='{query}' -> keywords={keywords}")

        # Detect query domain for relevance filtering
        query_domain = detect_query_domain(keywords)
        if query_domain:
            logger.debug(f"Detected query domain: {query_domain}")

        # Stage 1: High precision search (no synonym expansion)
        stage1_results = self._stage1_search(keywords, search_tools, min_score)

        # If Stage 1 found good results, use them
        if stage1_results and stage1_results[0].score >= self.WEIGHT_NAME_EXACT:
            logger.debug(f"Stage 1 found {len(stage1_results)} high-quality results")
            results = stage1_results
        else:
            # Stage 2: Expanded search with synonyms
            query_tokens = expand_with_synonyms(keywords)
            logger.debug(f"Stage 2: expanding to {query_tokens}")
            results = self._stage2_search(query_tokens, search_tools, min_score, query_domain)

            # If Stage 2 fails, try fuzzy matching
            if not results:
                results = self._fuzzy_search(query, search_tools, limit)

        # If still no results, return fallback
        if not results:
            return self._fallback_results(search_tools, limit, use_session_boost)

        # Apply session boosting
        if use_session_boost:
            results = self._apply_session_boost(results)

        # Sort by final score
        results.sort(key=lambda r: r.score, reverse=True)

        return results[:limit]

    def _stage1_search(
        self,
        keywords: list[str],
        tools: list[T],
        min_score: float,
    ) -> list[SearchResult[T]]:
        """Stage 1: High precision search without synonym expansion.

        Only matches exact tokens and prefixes in tool names.
        """
        results: list[SearchResult[T]] = []
        keyword_set = set(keywords)

        for tool in tools:
            tool_name = getattr(tool, "name", "")
            name_tokens = set(tokenize(tool_name))
            score = 0.0
            reasons = []

            for kw in keyword_set:
                # Exact name match
                if kw in name_tokens:
                    score += self.WEIGHT_NAME_EXACT
                    reasons.append(f"name:'{kw}'")
                # Prefix match
                elif any(nt.startswith(kw) for nt in name_tokens):
                    score += self.WEIGHT_NAME_PREFIX
                    reasons.append(f"name_prefix:'{kw}'")

            if score > min_score:
                results.append(SearchResult(tool=tool, score=score, match_reasons=reasons))

        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def _stage2_search(
        self,
        query_tokens: set[str],
        tools: list[T],
        min_score: float,
        query_domain: str | None = None,
    ) -> list[SearchResult[T]]:
        """Stage 2: Expanded search with synonym expansion.

        Includes description, namespace, and parameter matching.
        Applies domain penalty for tools from mismatched domains.
        """
        results: list[SearchResult[T]] = []

        for tool in tools:
            tool_name = getattr(tool, "name", "")
            tool_desc = get_tool_description(tool)
            tool_ns = getattr(tool, "namespace", "")
            tool_params = get_tool_parameters(tool)

            param_names = None
            if tool_params and "properties" in tool_params:
                param_names = list(tool_params["properties"].keys())

            score, reasons = score_token_match(
                query_tokens,
                tool_name,
                tool_desc,
                tool_ns,
                param_names,
            )

            # Apply domain penalty for mismatched domains
            if query_domain is not None:
                tool_domain = detect_tool_domain(tool_name, tool_desc)
                penalty = compute_domain_penalty(query_domain, tool_domain)
                if penalty < 1.0:
                    score *= penalty
                    reasons.append(f"domain_penalty:{penalty:.1f}x({tool_domain})")

            if score > min_score:
                results.append(SearchResult(tool=tool, score=score, match_reasons=reasons))

        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def _apply_session_boost(self, results: list[SearchResult[T]]) -> list[SearchResult[T]]:
        """Apply session-based boosting to search results.

        Creates new SearchResult objects to avoid mutating the originals.
        """
        boosted = []
        for result in results:
            tool_name = getattr(result.tool, "name", "")
            boost = self.get_session_boost(tool_name)
            if boost > 1.0:
                # Create new SearchResult to avoid mutating original
                new_reasons = list(result.match_reasons) + [f"session_boost:{boost:.2f}x"]
                boosted.append(
                    SearchResult(
                        tool=result.tool,
                        score=result.score * boost,
                        match_reasons=new_reasons,
                    )
                )
            else:
                boosted.append(result)
        return boosted

    def _fuzzy_search(
        self,
        query: str,
        tools: list[T],
        limit: int,
    ) -> list[SearchResult[T]]:
        """Fuzzy search as fallback when token matching fails."""
        results: list[SearchResult[T]] = []

        query_lower = query.lower()

        for tool in tools:
            tool_name = getattr(tool, "name", "")
            tool_desc = get_tool_description(tool)

            # Check fuzzy match against name
            name_score = fuzzy_score(query_lower, tool_name.lower(), threshold=0.5)

            # Check fuzzy match against description words
            desc_score = 0.0
            if tool_desc:
                desc_words = tool_desc.lower().split()
                for word in desc_words:
                    word_score = fuzzy_score(query_lower, word, threshold=0.6)
                    if word_score > desc_score:
                        desc_score = word_score

            total_score = (name_score * 10) + (desc_score * 3)

            if total_score > 0:
                reasons = []
                if name_score > 0:
                    reasons.append(f"fuzzy_name:{name_score:.2f}")
                if desc_score > 0:
                    reasons.append(f"fuzzy_desc:{desc_score:.2f}")

                results.append(SearchResult(tool=tool, score=total_score, match_reasons=reasons))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def _fallback_results(
        self,
        tools: list[T],
        limit: int,
        use_session_boost: bool = True,
    ) -> list[SearchResult[T]]:
        """Return fallback results when no matches found.

        Returns tools sorted by:
        1. Session boost (if enabled) - recently used tools first
        2. Tools with shorter names (often more fundamental)
        3. Alphabetically as tiebreaker
        """
        results = [SearchResult(tool=t, score=0.1, match_reasons=["fallback"]) for t in tools]

        # Apply session boosting
        if use_session_boost:
            results = self._apply_session_boost(results)

        # Sort by score (with session boost), then by name length, then alphabetically
        results.sort(key=lambda r: (-r.score, len(getattr(r.tool, "name", "")), r.name))

        return results[:limit]

    def find_exact(
        self,
        name: str,
        tools: list[T] | None = None,
    ) -> T | None:
        """Find a tool by exact name or alias.

        Checks:
        1. Exact name match
        2. Name with namespace prefix
        3. Normalized aliases (snake_case, camelCase, etc.)

        Args:
            name: Tool name to find
            tools: Tools to search (uses cache if None)

        Returns:
            Matching tool or None
        """
        search_tools = tools if tools is not None else self._tool_cache
        if not search_tools:
            return None

        # Try exact match first
        for tool in search_tools:
            if getattr(tool, "name", "") == name:
                return tool

        # Try with namespace prefix
        for tool in search_tools:
            tool_name = getattr(tool, "name", "")
            tool_ns = getattr(tool, "namespace", "")
            if f"{tool_ns}.{tool_name}" == name:
                return tool

        # Try alias matching
        return find_tool_by_alias(name, search_tools)


# ============================================================================
# Convenience Functions
# ============================================================================

# Global search engine instance (untyped for convenience)
_search_engine: ToolSearchEngine[Any] | None = None


def get_search_engine() -> ToolSearchEngine[Any]:
    """Get or create the global search engine instance."""
    global _search_engine
    if _search_engine is None:
        _search_engine = ToolSearchEngine()
    return _search_engine


def search_tools(
    query: str,
    tools: list[Any],
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Search for tools matching the query.

    Convenience function that returns results in dict format.

    Args:
        query: Search query
        tools: List of tools to search
        limit: Maximum results

    Returns:
        List of dicts with name, description, namespace, score, match_reasons
    """
    engine = get_search_engine()
    results = engine.search(query, tools, limit)

    return [
        {
            "name": getattr(r.tool, "name", ""),
            "description": get_tool_description(r.tool) or "No description",
            "namespace": getattr(r.tool, "namespace", ""),
            "score": r.score,
            "match_reasons": r.match_reasons,
        }
        for r in results
    ]


def find_tool_exact(
    name: str,
    tools: list[Any],
) -> Any | None:
    """Find a tool by exact name or alias.

    Args:
        name: Tool name to find
        tools: Tools to search

    Returns:
        Matching tool or None
    """
    engine = get_search_engine()
    return engine.find_exact(name, tools)
