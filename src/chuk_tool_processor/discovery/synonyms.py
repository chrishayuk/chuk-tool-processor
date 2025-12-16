# chuk_tool_processor/discovery/synonyms.py
"""Synonym dictionaries and domain detection for intelligent tool search.

This module provides:
- Bidirectional synonym mappings for natural language queries
- Domain/category detection for relevance scoring
- Stopword filtering for query processing
"""

from __future__ import annotations

import re

# ============================================================================
# Synonym Dictionary
# ============================================================================

# Bidirectional synonyms - each key maps to related terms
# When searching, we expand the query to include synonyms
SYNONYMS: dict[str, set[str]] = {
    # Statistics / Probability
    "normal": {"gaussian", "bell", "standard"},
    "gaussian": {"normal", "bell", "standard"},
    "cdf": {"cumulative", "distribution", "probability"},
    "cumulative": {"cdf"},
    "pdf": {"probability", "density", "distribution"},
    "mean": {"average", "expected", "mu", "expectation"},
    "average": {"mean", "avg"},
    "std": {"standard", "deviation", "sigma", "stddev"},
    "deviation": {"std", "sigma", "variance"},
    "sigma": {"std", "deviation", "standard"},
    "variance": {"var", "deviation"},
    "median": {"middle", "percentile"},
    "percentile": {"quantile", "quartile"},
    "quantile": {"percentile"},
    "correlation": {"corr", "covariance"},
    "covariance": {"cov", "correlation"},
    "regression": {"linear", "fit", "model"},
    "hypothesis": {"test", "significance", "pvalue"},
    "pvalue": {"significance", "hypothesis", "test"},
    "confidence": {"interval", "ci"},
    "tail": {"probability", "risk"},
    # Math operations
    "add": {"sum", "plus", "addition"},
    "sum": {"add", "total", "aggregate"},
    "subtract": {"minus", "difference", "sub"},
    "multiply": {"times", "product", "mult"},
    "divide": {"division", "quotient", "div"},
    "power": {"exponent", "pow", "exp"},
    "sqrt": {"square", "root"},
    "log": {"logarithm", "ln", "natural", "print", "trace", "debug"},
    "sin": {"sine", "trig", "trigonometric"},
    "cos": {"cosine", "trig", "trigonometric"},
    "tan": {"tangent", "trig", "trigonometric"},
    "factorial": {"gamma", "permutation"},
    "combination": {"choose", "binomial", "nCr"},
    "permutation": {"nPr", "arrangement"},
    "abs": {"absolute", "magnitude"},
    "min": {"minimum", "smallest", "least"},
    "max": {"maximum", "largest", "greatest"},
    "round": {"truncate", "floor", "ceil"},
    # Linear algebra
    "matrix": {"matrices", "array", "tensor"},
    "vector": {"array", "list", "tuple"},
    "transpose": {"flip", "swap"},
    "inverse": {"invert", "reciprocal"},
    "determinant": {"det"},
    "eigenvalue": {"eigen", "eigenvalues"},
    "dot": {"inner", "scalar"},
    "cross": {"outer", "vector"},
    # Geometry
    "circle": {"ellipse", "oval", "round"},
    "triangle": {"polygon", "shape"},
    "rectangle": {"square", "quad", "polygon"},
    "area": {"surface", "size"},
    "perimeter": {"circumference", "boundary"},
    "volume": {"capacity", "space", "gain", "amplitude", "level"},
    "distance": {"length", "magnitude", "norm"},
    "angle": {"degree", "radian", "rotation"},
    # File operations
    "read": {"get", "load", "fetch", "retrieve", "open"},
    "write": {"save", "store", "put", "create"},
    "delete": {"remove", "rm", "erase", "unlink"},
    "list": {"ls", "dir", "enumerate", "show"},
    "search": {"find", "query", "lookup", "grep"},
    "find": {"search", "locate", "query"},
    "copy": {"duplicate", "clone", "cp"},
    "move": {"rename", "mv", "relocate"},
    "append": {"concat", "add", "extend"},
    # Data types
    "string": {"text", "str", "char"},
    "number": {"int", "integer", "float", "numeric"},
    "array": {"list", "vector", "sequence"},
    "object": {"dict", "map", "hash", "dictionary"},
    "boolean": {"bool", "flag", "true", "false"},
    # String operations
    "concat": {"concatenate", "join", "merge", "combine"},
    "split": {"separate", "divide", "tokenize"},
    "trim": {"strip", "clean"},
    "upper": {"uppercase", "capitalize"},
    "lower": {"lowercase", "downcase"},
    "replace": {"substitute", "swap"},
    "substring": {"slice", "substr", "extract"},
    "length": {"len", "size", "count"},
    "contains": {"includes", "has", "match"},
    # Network / API
    "http": {"request", "api", "fetch", "web"},
    "get": {"fetch", "retrieve", "request"},
    "post": {"send", "submit", "create"},
    "json": {"parse", "serialize", "data"},
    "url": {"uri", "link", "endpoint"},
    "download": {"fetch", "retrieve", "get"},
    "upload": {"send", "post", "submit"},
    "connect": {"open", "establish", "dial"},
    "disconnect": {"close", "terminate", "hangup"},
    # Time / Date
    "date": {"time", "datetime", "timestamp"},
    "now": {"current", "today", "present"},
    "format": {"parse", "convert", "transform"},
    "duration": {"interval", "period", "span"},
    "schedule": {"cron", "timer", "recurring"},
    # Database
    "query": {"select", "sql", "search"},
    "insert": {"add", "create", "put"},
    "update": {"modify", "change", "set"},
    "database": {"db", "sql", "store"},
    "table": {"collection", "entity", "relation"},
    "index": {"key", "lookup"},
    "transaction": {"commit", "rollback", "atomic"},
    # Data structures
    "stack": {"lifo", "push", "pop"},
    "queue": {"fifo", "enqueue", "dequeue"},
    "heap": {"priority", "minheap", "maxheap"},
    "tree": {"node", "branch", "leaf"},
    "graph": {"node", "edge", "vertex"},
    "set": {"unique", "distinct", "collection"},
    # Sorting and ordering
    "sort": {"order", "arrange", "rank"},
    "ascending": {"asc", "increasing", "up"},
    "descending": {"desc", "decreasing", "down"},
    "reverse": {"invert", "flip", "backward"},
    "shuffle": {"randomize", "mix"},
    # Comparison
    "equal": {"equals", "same", "identical", "eq"},
    "greater": {"more", "larger", "bigger", "gt"},
    "less": {"fewer", "smaller", "lt"},
    "compare": {"diff", "contrast", "versus"},
    # Cryptography / Security
    "encrypt": {"encode", "cipher", "secure"},
    "decrypt": {"decode", "decipher", "unlock"},
    "hash": {"digest", "checksum", "fingerprint"},
    "sign": {"signature", "verify", "authenticate"},
    "key": {"secret", "password", "credential"},
    "token": {"jwt", "bearer", "auth"},
    "certificate": {"cert", "ssl", "tls"},
    # Encoding / Compression
    "base64": {"encode", "decode"},
    "compress": {"zip", "gzip", "deflate"},
    "decompress": {"unzip", "inflate", "extract"},
    "encode": {"serialize", "marshal"},
    "decode": {"deserialize", "unmarshal", "parse"},
    "utf8": {"unicode", "encoding", "charset"},
    # Concurrency
    "async": {"asynchronous", "await", "nonblocking"},
    "parallel": {"concurrent", "multithread", "simultaneous"},
    "lock": {"mutex", "semaphore", "synchronize"},
    "thread": {"worker", "task", "process"},
    "spawn": {"fork", "start", "launch"},
    # ML / AI
    "train": {"fit", "learn", "optimize"},
    "predict": {"infer", "forecast", "estimate"},
    "model": {"network", "classifier", "regressor"},
    "accuracy": {"precision", "recall", "score"},
    "feature": {"attribute", "column", "variable"},
    "label": {"target", "class", "category"},
    "embedding": {"vector", "representation", "encoding"},
    "cluster": {"group", "segment", "partition"},
    # NLP / Text
    "tokenize": {"split", "segment", "parse"},
    "stem": {"lemma", "root", "base"},
    "entity": {"ner", "named", "extract"},
    "sentiment": {"emotion", "opinion", "polarity"},
    "classify": {"categorize", "label", "tag"},
    "summarize": {"abstract", "condense", "shorten"},
    # Image / Graphics
    "image": {"picture", "photo", "graphic"},
    "resize": {"scale", "transform", "shrink"},
    "crop": {"trim", "cut", "clip"},
    "rotate": {"turn", "spin", "flip"},
    "filter": {"effect", "transform", "process"},
    "pixel": {"point", "dot"},
    "render": {"draw", "display", "paint"},
    # Audio
    "audio": {"sound", "music", "wav"},
    "play": {"start", "resume"},
    "pause": {"stop", "halt"},
    "record": {"capture", "mic"},
    # Error handling
    "error": {"exception", "failure", "fault"},
    "retry": {"repeat", "again", "reattempt"},
    "fallback": {"default", "backup", "alternative"},
    "validate": {"check", "verify", "assert"},
    "sanitize": {"clean", "escape", "filter"},
    # Logging / Debugging
    "info": {"information", "detail", "message"},
    "warn": {"warning", "alert", "caution"},
    "debug": {"trace", "inspect", "diagnose"},
    # System / Environment
    "env": {"environment", "config", "setting"},
    "path": {"directory", "folder", "location"},
    "process": {"pid", "program", "application"},
    "memory": {"ram", "heap", "allocation"},
    "cpu": {"processor", "core", "compute"},
}

# ============================================================================
# Domain/Category Detection (for relevance scoring)
# ============================================================================

# Domain indicators - keywords that suggest a tool belongs to a category
# Used to detect domain mismatch and apply penalties
DOMAIN_INDICATORS: dict[str, set[str]] = {
    "statistics": {
        "normal",
        "gaussian",
        "cdf",
        "pdf",
        "probability",
        "distribution",
        "mean",
        "variance",
        "std",
        "deviation",
        "correlation",
        "regression",
        "hypothesis",
        "test",
        "confidence",
        "percentile",
        "quantile",
        "statistical",
        "sample",
        "population",
        "expected",
        "random",
    },
    "number_theory": {
        "prime",
        "collatz",
        "fibonacci",
        "factorial",
        "gcd",
        "lcm",
        "divisor",
        "modulo",
        "congruence",
        "euler",
        "fermat",
        "integer",
        "sequence",
        "series",
        "recursive",
    },
    "arithmetic": {
        "add",
        "subtract",
        "multiply",
        "divide",
        "sum",
        "product",
        "sqrt",
        "power",
        "root",
        "log",
        "exp",
        "abs",
        "round",
    },
    "trigonometry": {
        "sin",
        "cos",
        "tan",
        "asin",
        "acos",
        "atan",
        "radians",
        "degrees",
        "angle",
        "trigonometric",
        "trig",
        "hyperbolic",
    },
    "linear_algebra": {
        "matrix",
        "vector",
        "transpose",
        "inverse",
        "determinant",
        "eigenvalue",
        "eigenvector",
        "dot",
        "cross",
        "norm",
        "tensor",
    },
    "geometry": {
        "circle",
        "triangle",
        "rectangle",
        "polygon",
        "area",
        "perimeter",
        "volume",
        "distance",
        "angle",
        "coordinate",
        "point",
        "line",
    },
    "file_operations": {
        "read",
        "write",
        "file",
        "directory",
        "path",
        "open",
        "close",
        "save",
        "load",
        "delete",
        "create",
        "copy",
        "move",
    },
    "string_operations": {
        "string",
        "text",
        "concat",
        "split",
        "trim",
        "replace",
        "substring",
        "upper",
        "lower",
        "regex",
        "pattern",
        "match",
    },
    "network": {
        "http",
        "request",
        "response",
        "api",
        "url",
        "fetch",
        "post",
        "get",
        "endpoint",
        "server",
        "client",
        "socket",
    },
    "database": {
        "query",
        "sql",
        "select",
        "insert",
        "update",
        "delete",
        "table",
        "database",
        "record",
        "row",
        "column",
        "join",
    },
    "cryptography": {
        "encrypt",
        "decrypt",
        "hash",
        "sign",
        "verify",
        "key",
        "certificate",
        "ssl",
        "tls",
        "cipher",
        "aes",
        "rsa",
    },
    "encoding": {
        "base64",
        "encode",
        "decode",
        "compress",
        "decompress",
        "utf8",
        "unicode",
        "json",
        "xml",
        "serialize",
    },
    "machine_learning": {
        "train",
        "predict",
        "model",
        "accuracy",
        "precision",
        "recall",
        "feature",
        "label",
        "classification",
        "regression",
        "cluster",
        "embedding",
    },
    "nlp": {
        "tokenize",
        "stem",
        "lemma",
        "entity",
        "sentiment",
        "classify",
        "summarize",
        "translate",
        "parse",
        "grammar",
    },
    "image_processing": {
        "image",
        "pixel",
        "resize",
        "crop",
        "rotate",
        "filter",
        "render",
        "draw",
        "color",
        "rgb",
        "grayscale",
    },
    "audio_processing": {
        "audio",
        "sound",
        "sample",
        "frequency",
        "pitch",
        "amplitude",
        "wave",
        "play",
        "record",
        "volume",
    },
    "concurrency": {
        "async",
        "await",
        "parallel",
        "concurrent",
        "thread",
        "process",
        "lock",
        "mutex",
        "semaphore",
        "spawn",
    },
}

# Query domain detection patterns
QUERY_DOMAIN_PATTERNS: dict[str, set[str]] = {
    "statistics": {
        "risk",
        "probability",
        "stock",
        "inventory",
        "forecast",
        "normal",
        "gaussian",
        "distribution",
        "confidence",
        "interval",
        "hypothesis",
        "significance",
        "variance",
        "deviation",
        "mean",
        "expected",
        "random",
        "sample",
    },
    "number_theory": {
        "prime",
        "collatz",
        "fibonacci",
        "sequence",
        "integer",
        "divisibility",
        "factorization",
    },
}


def detect_query_domain(keywords: list[str]) -> str | None:
    """Detect the likely domain of a query from its keywords.

    Args:
        keywords: List of keywords extracted from query

    Returns:
        Domain name if confidently detected, None otherwise.
    """
    keyword_set = {k.lower() for k in keywords}

    best_domain = None
    best_score = 0

    for domain, patterns in QUERY_DOMAIN_PATTERNS.items():
        overlap = keyword_set & patterns
        if len(overlap) > best_score:
            best_score = len(overlap)
            best_domain = domain

    # Require at least 1 match to claim a domain
    return best_domain if best_score >= 1 else None


def detect_tool_domain(tool_name: str, description: str | None) -> str | None:
    """Detect the likely domain of a tool from its name and description.

    Args:
        tool_name: Name of the tool
        description: Tool description (optional)

    Returns:
        Domain name if confidently detected, None otherwise.
    """
    # Combine name and description tokens
    text = f"{tool_name} {description or ''}".lower()
    tokens = set(re.split(r"[_\-.\s]+", text))

    best_domain = None
    best_score = 0

    for domain, indicators in DOMAIN_INDICATORS.items():
        overlap = tokens & indicators
        if len(overlap) > best_score:
            best_score = len(overlap)
            best_domain = domain

    # Require at least 1 match to claim a domain
    return best_domain if best_score >= 1 else None


def compute_domain_penalty(
    query_domain: str | None,
    tool_domain: str | None,
) -> float:
    """Compute penalty for domain mismatch.

    Args:
        query_domain: Detected domain of the query
        tool_domain: Detected domain of the tool

    Returns:
        Multiplier (1.0 = no penalty, <1.0 = penalized).
    """
    if query_domain is None or tool_domain is None:
        return 1.0  # Can't determine, no penalty

    if query_domain == tool_domain:
        return 1.0  # Same domain, no penalty

    # Different domains - apply penalty
    # Some domains are more "distant" than others
    DOMAIN_DISTANCE: dict[tuple[str, str], float] = {
        # Statistics vs number_theory is a big mismatch
        ("statistics", "number_theory"): 0.3,
        ("number_theory", "statistics"): 0.3,
        # Statistics vs arithmetic is reasonable
        ("statistics", "arithmetic"): 0.8,
        ("arithmetic", "statistics"): 0.8,
    }

    pair = (query_domain, tool_domain)
    return DOMAIN_DISTANCE.get(pair, 0.5)  # Default 50% penalty


# Common stopwords to filter from queries
STOPWORDS: set[str] = {
    "a",
    "an",
    "the",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "must",
    "shall",
    "can",
    "need",
    "dare",
    "to",
    "of",
    "in",
    "for",
    "on",
    "with",
    "at",
    "by",
    "from",
    "as",
    "into",
    "through",
    "during",
    "before",
    "after",
    "above",
    "below",
    "between",
    "under",
    "again",
    "further",
    "then",
    "once",
    "here",
    "there",
    "when",
    "where",
    "why",
    "how",
    "all",
    "each",
    "few",
    "more",
    "most",
    "other",
    "some",
    "such",
    "no",
    "nor",
    "not",
    "only",
    "own",
    "same",
    "so",
    "than",
    "too",
    "very",
    "just",
    "and",
    "but",
    "if",
    "or",
    "because",
    "until",
    "while",
    "although",
    "though",
    "even",
    "that",
    "which",
    "who",
    "whom",
    "this",
    "these",
    "those",
    "what",
    "i",
    "me",
    "my",
    "myself",
    "we",
    "our",
    "ours",
    "ourselves",
    "you",
    "your",
    "yours",
    "yourself",
    "yourselves",
    "he",
    "him",
    "his",
    "himself",
    "she",
    "her",
    "hers",
    "herself",
    "it",
    "its",
    "itself",
    "they",
    "them",
    "their",
    "theirs",
    "themselves",
    "tool",
    "tools",
    "function",
    "functions",
    "help",
    "helps",
    "use",
    "using",
    "used",
    "want",
    "wants",
    "wanted",
    "please",
    "like",
    "something",
    "anything",
    "everything",
    "nothing",
    "calculate",
    "calculation",
    "calculations",
    "computing",
    "compute",
}


def expand_with_synonyms(tokens: list[str]) -> set[str]:
    """Expand tokens with synonyms for broader matching.

    Args:
        tokens: List of tokens to expand

    Returns:
        Set of original tokens plus their synonyms
    """
    expanded = set(tokens)

    for token in tokens:
        if token in SYNONYMS:
            expanded.update(SYNONYMS[token])

    return expanded
