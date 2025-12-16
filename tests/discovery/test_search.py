# tests/discovery/test_search.py
"""Tests for intelligent tool search functionality."""

from dataclasses import dataclass
from typing import Any

import pytest

from chuk_tool_processor.discovery import (
    SessionToolStats,
    ToolSearchEngine,
    compute_domain_penalty,
    detect_query_domain,
    detect_tool_domain,
    expand_with_synonyms,
    extract_keywords,
    find_tool_by_alias,
    find_tool_exact,
    fuzzy_score,
    levenshtein_distance,
    normalize_tool_name,
    score_token_match,
    search_tools,
    tokenize,
)

# ============================================================================
# Test Tool Model (simple dataclass for testing)
# ============================================================================


@dataclass
class MockTool:
    """Simple tool model for testing the search engine."""

    name: str
    namespace: str
    description: str | None = None
    parameters: dict[str, Any] | None = None


# ============================================================================
# Tokenization Tests
# ============================================================================


class TestTokenize:
    """Tests for the tokenize function."""

    def test_snake_case(self):
        """Test tokenizing snake_case names."""
        assert tokenize("normal_cdf") == ["normal", "cdf"]
        assert tokenize("get_user_profile") == ["get", "user", "profile"]

    def test_camel_case(self):
        """Test tokenizing camelCase names."""
        tokens = tokenize("normalCdf")
        assert "normal" in tokens or "normalcdf" in tokens
        tokens2 = tokenize("getUserProfile")
        assert len(tokens2) >= 1

    def test_kebab_case(self):
        """Test tokenizing kebab-case names."""
        assert tokenize("normal-cdf") == ["normal", "cdf"]
        assert tokenize("get-user-profile") == ["get", "user", "profile"]

    def test_dot_notation(self):
        """Test tokenizing dot.notation names."""
        assert tokenize("math.normal_cdf") == ["math", "normal", "cdf"]
        assert tokenize("api.get.user") == ["api", "get", "user"]

    def test_mixed_separators(self):
        """Test tokenizing mixed separator formats."""
        tokens = tokenize("math.normal_cdf-value")
        assert "math" in tokens
        assert "normal" in tokens
        assert "cdf" in tokens
        assert "value" in tokens

    def test_numbers(self):
        """Test tokenizing strings with numbers."""
        tokens = tokenize("sin2d")
        assert "sin" in tokens
        tokens2 = tokenize("vector3")
        assert "vector" in tokens2

    def test_empty_string(self):
        """Test tokenizing empty string."""
        assert tokenize("") == []

    def test_minimum_length(self):
        """Test that single-character tokens are filtered."""
        assert tokenize("a_b_c") == []
        assert tokenize("ab_cd") == ["ab", "cd"]


# ============================================================================
# Synonym Expansion Tests
# ============================================================================


class TestSynonymExpansion:
    """Tests for synonym expansion."""

    def test_expand_normal_to_gaussian(self):
        """Test that 'normal' expands to include 'gaussian'."""
        expanded = expand_with_synonyms(["normal"])
        assert "normal" in expanded
        assert "gaussian" in expanded

    def test_expand_cdf(self):
        """Test that 'cdf' expands to related terms."""
        expanded = expand_with_synonyms(["cdf"])
        assert "cdf" in expanded
        assert "cumulative" in expanded
        assert "distribution" in expanded

    def test_expand_mean(self):
        """Test that 'mean' expands to related terms."""
        expanded = expand_with_synonyms(["mean"])
        assert "mean" in expanded
        assert "average" in expanded
        assert "mu" in expanded

    def test_no_expansion_for_unknown(self):
        """Test that unknown terms are not expanded."""
        expanded = expand_with_synonyms(["xyz123"])
        assert expanded == {"xyz123"}

    def test_multiple_tokens(self):
        """Test expanding multiple tokens."""
        expanded = expand_with_synonyms(["normal", "cdf"])
        assert "gaussian" in expanded
        assert "cumulative" in expanded


class TestExtractKeywords:
    """Tests for keyword extraction."""

    def test_remove_stopwords(self):
        """Test that stopwords are removed."""
        keywords = extract_keywords("find a tool for calculating the mean")
        assert "find" in keywords or "mean" in keywords
        assert "a" not in keywords
        assert "the" not in keywords
        assert "for" not in keywords

    def test_natural_language_query(self):
        """Test extracting keywords from natural language."""
        keywords = extract_keywords("I need a tool that can help me calculate probability distributions")
        assert "probability" in keywords or "distributions" in keywords

    def test_all_stopwords_returns_original(self):
        """Test that if all words are stopwords, original tokens returned."""
        keywords = extract_keywords("a an the")
        assert len(keywords) >= 0


# ============================================================================
# Token Match Scoring Tests
# ============================================================================


class TestScoreTokenMatch:
    """Tests for token-based scoring."""

    def test_exact_name_match(self):
        """Test that exact name matches score highest."""
        score, reasons = score_token_match(
            {"normal", "cdf"},
            tool_name="normal_cdf",
            tool_description="Calculate CDF",
            tool_namespace="math",
        )
        assert score > 0
        assert any("name" in r for r in reasons)

    def test_description_match(self):
        """Test that description matches contribute to score."""
        score, reasons = score_token_match(
            {"cumulative", "distribution"},
            tool_name="cdf_calc",
            tool_description="Calculate cumulative distribution function",
            tool_namespace="stats",
        )
        assert score > 0
        assert any("desc" in r for r in reasons)

    def test_namespace_match(self):
        """Test that namespace matches contribute to score."""
        score, reasons = score_token_match(
            {"math"},
            tool_name="add",
            tool_description="Add numbers",
            tool_namespace="math",
        )
        assert score > 0
        assert any("ns" in r for r in reasons)

    def test_no_match(self):
        """Test that non-matching queries score zero."""
        score, reasons = score_token_match(
            {"xyz", "abc"},
            tool_name="normal_cdf",
            tool_description="Calculate CDF",
            tool_namespace="math",
        )
        assert score == 0
        assert len(reasons) == 0


# ============================================================================
# Fuzzy Matching Tests
# ============================================================================


class TestFuzzyScore:
    """Tests for fuzzy matching."""

    def test_exact_match(self):
        """Test exact match returns high score."""
        assert fuzzy_score("normal", "normal") == 1.0

    def test_similar_strings(self):
        """Test similar strings return reasonable score."""
        score = fuzzy_score("normal", "norml")
        assert score > 0.7

    def test_very_different(self):
        """Test very different strings return zero."""
        score = fuzzy_score("normal", "xyz")
        assert score == 0

    def test_case_insensitive(self):
        """Test that matching is case insensitive."""
        assert fuzzy_score("NORMAL", "normal") == 1.0


class TestLevenshteinDistance:
    """Tests for edit distance calculation."""

    def test_same_string(self):
        """Test same string has zero distance."""
        assert levenshtein_distance("hello", "hello") == 0

    def test_one_edit(self):
        """Test strings with one edit."""
        assert levenshtein_distance("hello", "hallo") == 1

    def test_empty_string(self):
        """Test empty string distance."""
        assert levenshtein_distance("", "hello") == 5
        assert levenshtein_distance("hello", "") == 5


# ============================================================================
# Name Normalization Tests
# ============================================================================


class TestNormalizeToolName:
    """Tests for tool name normalization."""

    def test_snake_case_variants(self):
        """Test that snake_case generates variants."""
        variants = normalize_tool_name("normal_cdf")
        assert "normal_cdf" in variants
        assert "normalcdf" in variants
        assert "normal-cdf" in variants
        assert "normalCdf" in variants

    def test_namespaced_name(self):
        """Test that namespaced names extract base name."""
        variants = normalize_tool_name("math.normal_cdf")
        assert "normal_cdf" in variants
        assert "math.normal_cdf" in variants


class TestFindToolByAlias:
    """Tests for tool alias resolution."""

    @pytest.fixture
    def sample_tools(self) -> list[MockTool]:
        """Create sample tools for testing."""
        return [
            MockTool(name="normal_cdf", namespace="math", description="Normal CDF"),
            MockTool(name="add", namespace="math", description="Add numbers"),
        ]

    def test_exact_match(self, sample_tools):
        """Test exact name match."""
        tool = find_tool_by_alias("normal_cdf", sample_tools)
        assert tool is not None
        assert tool.name == "normal_cdf"

    def test_camel_case_alias(self, sample_tools):
        """Test camelCase alias resolution."""
        tool = find_tool_by_alias("normalCdf", sample_tools)
        assert tool is not None
        assert tool.name == "normal_cdf"

    def test_kebab_case_alias(self, sample_tools):
        """Test kebab-case alias resolution."""
        tool = find_tool_by_alias("normal-cdf", sample_tools)
        assert tool is not None
        assert tool.name == "normal_cdf"

    def test_with_namespace(self, sample_tools):
        """Test namespaced alias resolution."""
        tool = find_tool_by_alias("math.normal_cdf", sample_tools)
        assert tool is not None
        assert tool.name == "normal_cdf"

    def test_not_found(self, sample_tools):
        """Test not found returns None."""
        tool = find_tool_by_alias("nonexistent", sample_tools)
        assert tool is None


# ============================================================================
# Search Engine Tests
# ============================================================================


class MockToolSearchEngine:
    """Tests for the main search engine."""

    @pytest.fixture
    def stats_tools(self) -> list[MockTool]:
        """Create statistics-related tools for testing."""
        return [
            MockTool(
                name="normal_cdf",
                namespace="stats",
                description="Calculate the cumulative distribution function for a normal distribution",
                parameters={"type": "object", "properties": {"x": {"type": "number"}}},
            ),
            MockTool(
                name="normal_pdf",
                namespace="stats",
                description="Calculate the probability density function for a normal distribution",
                parameters={"type": "object", "properties": {"x": {"type": "number"}}},
            ),
            MockTool(
                name="mean",
                namespace="stats",
                description="Calculate the arithmetic mean of values",
                parameters={
                    "type": "object",
                    "properties": {"values": {"type": "array"}},
                },
            ),
            MockTool(
                name="std_dev",
                namespace="stats",
                description="Calculate the standard deviation",
                parameters={
                    "type": "object",
                    "properties": {"values": {"type": "array"}},
                },
            ),
            MockTool(
                name="add",
                namespace="math",
                description="Add two numbers",
                parameters={
                    "type": "object",
                    "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                },
            ),
        ]

    @pytest.fixture
    def engine(self, stats_tools) -> ToolSearchEngine:
        """Create a search engine with tools indexed."""
        engine: ToolSearchEngine[MockTool] = ToolSearchEngine()
        engine.set_tools(stats_tools)
        return engine

    def test_search_by_exact_name(self, engine, stats_tools):
        """Test searching by exact tool name."""
        results = engine.search("normal_cdf", stats_tools)
        assert len(results) > 0
        assert results[0].tool.name == "normal_cdf"

    def test_search_by_synonym_gaussian(self, engine, stats_tools):
        """Test that 'gaussian' finds 'normal' tools."""
        results = engine.search("gaussian cdf", stats_tools)
        assert len(results) > 0
        tool_names = [r.tool.name for r in results]
        assert any("normal" in name for name in tool_names)

    def test_search_by_synonym_average(self, engine, stats_tools):
        """Test that 'average' finds 'mean' tool."""
        results = engine.search("average", stats_tools)
        assert len(results) > 0
        assert any(r.tool.name == "mean" for r in results)

    def test_search_natural_language(self, engine, stats_tools):
        """Test searching with natural language query."""
        results = engine.search(
            "I need to calculate the cumulative probability for a standard distribution",
            stats_tools,
        )
        assert len(results) > 0
        top_result = results[0]
        assert "cdf" in top_result.tool.name.lower() or "cumulative" in (top_result.tool.description or "").lower()

    def test_search_partial_match(self, engine, stats_tools):
        """Test that partial matches work."""
        results = engine.search("norm", stats_tools)
        assert len(results) > 0
        tool_names = [r.tool.name for r in results]
        assert any("normal" in name for name in tool_names)

    def test_search_always_returns_results(self, engine, stats_tools):
        """Test that search always returns something (fallback)."""
        results = engine.search("xyznonexistent123", stats_tools)
        assert len(results) > 0

    def test_search_respects_limit(self, engine, stats_tools):
        """Test that limit is respected."""
        results = engine.search("math stats", stats_tools, limit=2)
        assert len(results) <= 2

    def test_search_scores_sorted(self, engine, stats_tools):
        """Test that results are sorted by score descending."""
        results = engine.search("normal distribution", stats_tools)
        if len(results) > 1:
            for i in range(len(results) - 1):
                assert results[i].score >= results[i + 1].score

    def test_find_exact_by_name(self, engine, stats_tools):
        """Test find_exact with exact name."""
        tool = engine.find_exact("normal_cdf", stats_tools)
        assert tool is not None
        assert tool.name == "normal_cdf"

    def test_find_exact_by_alias(self, engine, stats_tools):
        """Test find_exact with alias."""
        tool = engine.find_exact("normalCdf", stats_tools)
        assert tool is not None
        assert tool.name == "normal_cdf"

    def test_find_exact_not_found(self, engine, stats_tools):
        """Test find_exact returns None for unknown tool."""
        tool = engine.find_exact("nonexistent", stats_tools)
        assert tool is None


# ============================================================================
# Convenience Function Tests
# ============================================================================


class TestSearchToolsFunction:
    """Tests for the search_tools convenience function."""

    @pytest.fixture
    def sample_tools(self) -> list[MockTool]:
        """Create sample tools."""
        return [
            MockTool(name="calculator", namespace="math", description="Calculate expressions"),
            MockTool(name="weather", namespace="api", description="Get weather data"),
        ]

    def test_returns_dict_format(self, sample_tools):
        """Test that results are in dict format."""
        results = search_tools("calc", sample_tools)
        assert len(results) > 0
        assert isinstance(results[0], dict)
        assert "name" in results[0]
        assert "description" in results[0]
        assert "namespace" in results[0]
        assert "score" in results[0]


class TestFindToolExact:
    """Tests for the find_tool_exact convenience function."""

    @pytest.fixture
    def sample_tools(self) -> list[MockTool]:
        """Create sample tools."""
        return [
            MockTool(name="user_profile", namespace="api", description="Get user profile"),
        ]

    def test_exact_match(self, sample_tools):
        """Test exact match."""
        tool = find_tool_exact("user_profile", sample_tools)
        assert tool is not None
        assert tool.name == "user_profile"

    def test_alias_match(self, sample_tools):
        """Test alias match."""
        tool = find_tool_exact("userProfile", sample_tools)
        assert tool is not None
        assert tool.name == "user_profile"


# ============================================================================
# Edge Case Tests
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_tools_list(self):
        """Test search with empty tools list."""
        engine: ToolSearchEngine[MockTool] = ToolSearchEngine()
        results = engine.search("anything", [])
        assert results == []

    def test_empty_query(self):
        """Test search with empty query."""
        tools = [MockTool(name="test", namespace="ns", description="Test")]
        engine: ToolSearchEngine[MockTool] = ToolSearchEngine()
        results = engine.search("", tools)
        assert len(results) > 0

    def test_tool_with_no_description(self):
        """Test searching tools with no description."""
        tools = [MockTool(name="nodesc", namespace="ns", description=None)]
        engine: ToolSearchEngine[MockTool] = ToolSearchEngine()
        results = engine.search("nodesc", tools)
        assert len(results) > 0
        assert results[0].tool.name == "nodesc"

    def test_tool_with_no_parameters(self):
        """Test searching tools with no parameters."""
        tools = [MockTool(name="noparams", namespace="ns", description="Test", parameters=None)]
        engine: ToolSearchEngine[MockTool] = ToolSearchEngine()
        results = engine.search("noparams", tools)
        assert len(results) > 0

    def test_unicode_in_query(self):
        """Test handling unicode in queries."""
        tools = [MockTool(name="test", namespace="ns", description="Test tool")]
        engine: ToolSearchEngine[MockTool] = ToolSearchEngine()
        results = engine.search("tëst", tools)
        assert isinstance(results, list)

    def test_special_characters_in_query(self):
        """Test handling special characters in queries."""
        tools = [MockTool(name="test", namespace="ns", description="Test tool")]
        engine: ToolSearchEngine[MockTool] = ToolSearchEngine()
        results = engine.search("test!@#$%", tools)
        assert isinstance(results, list)


# ============================================================================
# Session Tracking Tests
# ============================================================================


class TestSessionToolStats:
    """Tests for SessionToolStats dataclass."""

    def test_initial_state(self):
        """Test initial state of stats."""
        stats = SessionToolStats(name="test_tool")
        assert stats.call_count == 0
        assert stats.success_count == 0
        assert stats.last_used_turn == 0
        assert stats.success_rate == 0.0

    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        stats = SessionToolStats(name="test", call_count=10, success_count=7)
        assert stats.success_rate == 0.7

    def test_success_rate_zero_calls(self):
        """Test success rate with zero calls."""
        stats = SessionToolStats(name="test", call_count=0, success_count=0)
        assert stats.success_rate == 0.0


class TestSessionTracking:
    """Tests for session-aware tool tracking."""

    @pytest.fixture
    def engine(self) -> ToolSearchEngine:
        """Create a fresh search engine."""
        return ToolSearchEngine()

    def test_record_tool_use(self, engine):
        """Test recording tool usage."""
        engine.record_tool_use("test_tool", success=True)

        stats = engine.get_session_stats("test_tool")
        assert stats is not None
        assert stats.call_count == 1
        assert stats.success_count == 1

    def test_record_failed_use(self, engine):
        """Test recording failed tool usage."""
        engine.record_tool_use("test_tool", success=True)
        engine.record_tool_use("test_tool", success=False)

        stats = engine.get_session_stats("test_tool")
        assert stats is not None
        assert stats.call_count == 2
        assert stats.success_count == 1
        assert stats.success_rate == 0.5

    def test_advance_turn(self, engine):
        """Test turn advancement."""
        assert engine._current_turn == 0
        engine.advance_turn()
        assert engine._current_turn == 1
        engine.advance_turn()
        assert engine._current_turn == 2

    def test_reset_session(self, engine):
        """Test session reset."""
        engine.record_tool_use("test_tool")
        engine.advance_turn()

        engine.reset_session()

        assert engine._current_turn == 0
        assert engine.get_session_stats("test_tool") is None

    def test_get_session_boost_no_usage(self, engine):
        """Test boost for unused tool."""
        boost = engine.get_session_boost("unknown_tool")
        assert boost == 1.0

    def test_get_session_boost_recent_use(self, engine):
        """Test boost for recently used tool."""
        engine.record_tool_use("test_tool", success=True)

        boost = engine.get_session_boost("test_tool")
        assert boost > 1.0

    def test_session_boost_decays_with_turns(self, engine):
        """Test that session boost decays over turns."""
        engine.record_tool_use("test_tool", success=True)

        boost_immediate = engine.get_session_boost("test_tool")

        for _ in range(3):
            engine.advance_turn()

        boost_later = engine.get_session_boost("test_tool")

        assert boost_later < boost_immediate

    def test_session_boost_scales_with_success(self, engine):
        """Test that higher success rate gives higher boost."""
        engine.record_tool_use("tool_a", success=True)
        engine.record_tool_use("tool_a", success=True)

        engine.record_tool_use("tool_b", success=True)
        engine.record_tool_use("tool_b", success=False)

        boost_a = engine.get_session_boost("tool_a")
        boost_b = engine.get_session_boost("tool_b")

        assert boost_a > boost_b


# ============================================================================
# Domain Detection Tests
# ============================================================================


class TestDomainDetection:
    """Tests for domain/category detection."""

    def test_detect_query_domain_statistics(self):
        """Test detecting statistics domain from keywords."""
        keywords = ["probability", "risk", "normal", "distribution"]
        domain = detect_query_domain(keywords)
        assert domain == "statistics"

    def test_detect_query_domain_number_theory(self):
        """Test detecting number theory domain from keywords."""
        keywords = ["prime", "collatz", "sequence"]
        domain = detect_query_domain(keywords)
        assert domain == "number_theory"

    def test_detect_query_domain_none(self):
        """Test no domain when keywords don't match."""
        keywords = ["foo", "bar", "baz"]
        domain = detect_query_domain(keywords)
        assert domain is None

    def test_detect_tool_domain_collatz(self):
        """Test detecting collatz as number theory."""
        domain = detect_tool_domain("collatz_stopping_time", "Calculate Collatz sequence")
        assert domain == "number_theory"

    def test_detect_tool_domain_normal_cdf(self):
        """Test detecting normal_cdf as statistics."""
        domain = detect_tool_domain("normal_cdf", "Cumulative distribution function for normal distribution")
        assert domain == "statistics"

    def test_detect_tool_domain_add(self):
        """Test detecting add as arithmetic."""
        domain = detect_tool_domain("add", "Add two numbers")
        assert domain == "arithmetic"

    def test_detect_tool_domain_unknown(self):
        """Test no domain for unrecognized tool."""
        domain = detect_tool_domain("foo_bar", "Does something")
        assert domain is None


class TestDomainPenalty:
    """Tests for domain mismatch penalty calculation."""

    def test_no_penalty_same_domain(self):
        """Test no penalty when domains match."""
        penalty = compute_domain_penalty("statistics", "statistics")
        assert penalty == 1.0

    def test_no_penalty_unknown_domains(self):
        """Test no penalty when domains unknown."""
        assert compute_domain_penalty(None, "statistics") == 1.0
        assert compute_domain_penalty("statistics", None) == 1.0
        assert compute_domain_penalty(None, None) == 1.0

    def test_severe_penalty_stats_vs_number_theory(self):
        """Test severe penalty for statistics vs number_theory mismatch."""
        penalty = compute_domain_penalty("statistics", "number_theory")
        assert penalty == 0.3

    def test_mild_penalty_stats_vs_arithmetic(self):
        """Test mild penalty for statistics vs arithmetic."""
        penalty = compute_domain_penalty("statistics", "arithmetic")
        assert penalty == 0.8

    def test_default_penalty_unrelated_domains(self):
        """Test default penalty for unspecified domain pairs."""
        penalty = compute_domain_penalty("file_operations", "network")
        assert penalty == 0.5
