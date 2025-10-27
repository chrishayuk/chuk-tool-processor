.PHONY: clean clean-pyc clean-build clean-test clean-all test run build publish help install dev-install version bump-patch bump-minor bump-major release

# Default target
help:
	@echo "Available targets:"
	@echo "  clean          - Remove Python bytecode and basic artifacts"
	@echo "  clean-all      - Deep clean everything (pyc, build, test, cache)"
	@echo "  clean-pyc      - Remove Python bytecode files"
	@echo "  clean-build    - Remove build artifacts"
	@echo "  clean-test     - Remove test artifacts"
	@echo "  install        - Install package in current environment"
	@echo "  dev-install    - Install package in development mode"
	@echo "  test           - Run tests"
	@echo "  test-cov       - Run tests with coverage report"
	@echo "  coverage-report - Show current coverage report"
	@echo "  lint           - Run code linters"
	@echo "  format         - Auto-format code"
	@echo "  typecheck      - Run type checking"
	@echo "  security       - Run security checks"
	@echo "  check          - Run all checks (lint, typecheck, security, test)"
	@echo "  run            - Run the server"
	@echo "  build          - Build the project"
	@echo ""
	@echo "Release targets:"
	@echo "  version        - Show current version"
	@echo "  bump-patch     - Bump patch version (0.0.X)"
	@echo "  bump-minor     - Bump minor version (0.X.0)"
	@echo "  bump-major     - Bump major version (X.0.0)"
	@echo "  publish        - Create tag and trigger automated release"
	@echo "  release        - Alias for publish"

# Basic clean - Python bytecode and common artifacts
clean: clean-pyc clean-build
	@echo "Basic clean complete."

# Remove Python bytecode files and __pycache__ directories
clean-pyc:
	@echo "Cleaning Python bytecode files..."
	@find . -type f -name '*.pyc' -delete 2>/dev/null || true
	@find . -type f -name '*.pyo' -delete 2>/dev/null || true
	@find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name '*.egg-info' -exec rm -rf {} + 2>/dev/null || true

# Remove build artifacts
clean-build:
	@echo "Cleaning build artifacts..."
	@rm -rf build/ dist/ *.egg-info 2>/dev/null || true
	@rm -rf .eggs/ 2>/dev/null || true
	@find . -name '*.egg' -exec rm -f {} + 2>/dev/null || true

# Remove test artifacts
clean-test:
	@echo "Cleaning test artifacts..."
	@rm -rf .pytest_cache/ 2>/dev/null || true
	@rm -rf .coverage 2>/dev/null || true
	@rm -rf htmlcov/ 2>/dev/null || true
	@rm -rf .tox/ 2>/dev/null || true
	@rm -rf .cache/ 2>/dev/null || true
	@find . -name '.coverage.*' -delete 2>/dev/null || true

# Deep clean - everything
clean-all: clean-pyc clean-build clean-test
	@echo "Deep cleaning..."
	@rm -rf .mypy_cache/ 2>/dev/null || true
	@rm -rf .ruff_cache/ 2>/dev/null || true
	@rm -rf .uv/ 2>/dev/null || true
	@rm -rf node_modules/ 2>/dev/null || true
	@find . -name '.DS_Store' -delete 2>/dev/null || true
	@find . -name 'Thumbs.db' -delete 2>/dev/null || true
	@find . -name '*.log' -delete 2>/dev/null || true
	@find . -name '*.tmp' -delete 2>/dev/null || true
	@find . -name '*~' -delete 2>/dev/null || true
	@echo "Deep clean complete."

# Install package
install:
	@echo "Installing package..."
	pip install .

# Install package in development mode
dev-install:
	@echo "Installing package in development mode..."
	pip install -e .

# Run tests
test:
	@echo "Running tests..."
	@if command -v uv >/dev/null 2>&1; then \
		uv run pytest; \
	elif command -v pytest >/dev/null 2>&1; then \
		pytest; \
	else \
		python -m pytest; \
	fi

# Show current coverage report
coverage-report:
	@echo "Coverage Report:"
	@echo "================"
	@if command -v uv >/dev/null 2>&1; then \
		uv run coverage report --omit="tests/*" || echo "No coverage data found. Run 'make test-cov' first."; \
	else \
		coverage report --omit="tests/*" || echo "No coverage data found. Run 'make test-cov' first."; \
	fi

# Run tests with coverage
test-cov coverage:
	@echo "Running tests with coverage..."
	@if command -v uv >/dev/null 2>&1; then \
		uv run pytest --cov=src --cov-report=html --cov-report=term --cov-report=term-missing:skip-covered; \
		exit_code=$$?; \
		echo ""; \
		echo "=========================="; \
		echo "Coverage Summary:"; \
		echo "=========================="; \
		uv run coverage report --omit="tests/*" | tail -5; \
		echo ""; \
		echo "HTML coverage report saved to: htmlcov/index.html"; \
		exit $$exit_code; \
	else \
		pytest --cov=src --cov-report=html --cov-report=term --cov-report=term-missing:skip-covered; \
		exit_code=$$?; \
		echo ""; \
		echo "=========================="; \
		echo "Coverage Summary:"; \
		echo "=========================="; \
		coverage report --omit="tests/*" | tail -5; \
		echo ""; \
		echo "HTML coverage report saved to: htmlcov/index.html"; \
		exit $$exit_code; \
	fi

# Run the server launcher
run:
	@echo "Running server..."
	@if command -v uv >/dev/null 2>&1; then \
		PYTHONPATH=src uv run python -m chuk_protocol_server.server_launcher; \
	else \
		PYTHONPATH=src python3 -m chuk_protocol_server.server_launcher; \
	fi

# Build the project using the pyproject.toml configuration
build: clean-build
	@echo "Building project..."
	@if command -v uv >/dev/null 2>&1; then \
		uv build; \
	else \
		python3 -m build; \
	fi
	@echo "Build complete. Distributions are in the 'dist' folder."

# ============================================================================
# Version Management and Release Targets
# ============================================================================

# Show current version
version:
	@version=$$(grep '^version = ' pyproject.toml | cut -d'"' -f2); \
	echo "Current version: $$version"

# Bump patch version (0.0.X)
bump-patch:
	@echo "Bumping patch version..."
	@current=$$(grep '^version = ' pyproject.toml | cut -d'"' -f2); \
	major=$$(echo $$current | cut -d. -f1); \
	minor=$$(echo $$current | cut -d. -f2); \
	patch=$$(echo $$current | cut -d. -f3); \
	new_patch=$$(($$patch + 1)); \
	new_version="$$major.$$minor.$$new_patch"; \
	sed -i.bak "s/^version = \"$$current\"/version = \"$$new_version\"/" pyproject.toml && rm pyproject.toml.bak; \
	echo "Version bumped: $$current -> $$new_version"; \
	echo "Review the change, then run 'make publish' to release"

# Bump minor version (0.X.0)
bump-minor:
	@echo "Bumping minor version..."
	@current=$$(grep '^version = ' pyproject.toml | cut -d'"' -f2); \
	major=$$(echo $$current | cut -d. -f1); \
	minor=$$(echo $$current | cut -d. -f2); \
	new_minor=$$(($$minor + 1)); \
	new_version="$$major.$$new_minor.0"; \
	sed -i.bak "s/^version = \"$$current\"/version = \"$$new_version\"/" pyproject.toml && rm pyproject.toml.bak; \
	echo "Version bumped: $$current -> $$new_version"; \
	echo "Review the change, then run 'make publish' to release"

# Bump major version (X.0.0)
bump-major:
	@echo "Bumping major version..."
	@current=$$(grep '^version = ' pyproject.toml | cut -d'"' -f2); \
	major=$$(echo $$current | cut -d. -f1); \
	new_major=$$(($$major + 1)); \
	new_version="$$new_major.0.0"; \
	sed -i.bak "s/^version = \"$$current\"/version = \"$$new_version\"/" pyproject.toml && rm pyproject.toml.bak; \
	echo "Version bumped: $$current -> $$new_version"; \
	echo "Review the change, then run 'make publish' to release"

# Automated release - creates tag and pushes to trigger GitHub Actions
publish:
	@echo "Starting automated release process..."
	@echo ""
	@# Get current version
	@version=$$(grep '^version = ' pyproject.toml | cut -d'"' -f2); \
	tag="v$$version"; \
	echo "Version: $$version"; \
	echo "Tag: $$tag"; \
	echo ""; \
	\
	echo "Pre-flight checks:"; \
	echo "=================="; \
	\
	if git diff --quiet && git diff --cached --quiet; then \
		echo "✓ Working directory is clean"; \
	else \
		echo "✗ Working directory has uncommitted changes"; \
		echo ""; \
		git status --short; \
		echo ""; \
		echo "Please commit or stash your changes before releasing."; \
		exit 1; \
	fi; \
	\
	if git tag -l | grep -q "^$$tag$$"; then \
		echo "✗ Tag $$tag already exists"; \
		echo ""; \
		echo "To delete and recreate:"; \
		echo "  git tag -d $$tag"; \
		echo "  git push origin :refs/tags/$$tag"; \
		exit 1; \
	else \
		echo "✓ Tag $$tag does not exist yet"; \
	fi; \
	\
	current_branch=$$(git rev-parse --abbrev-ref HEAD); \
	echo "✓ Current branch: $$current_branch"; \
	echo ""; \
	\
	echo "This will:"; \
	echo "  1. Create and push tag $$tag"; \
	echo "  2. Trigger GitHub Actions to:"; \
	echo "     - Create a GitHub release with changelog"; \
	echo "     - Run tests on all platforms"; \
	echo "     - Build and publish to PyPI"; \
	echo ""; \
	read -p "Continue? (y/N) " -n 1 -r; \
	echo ""; \
	if [[ ! $$REPLY =~ ^[Yy]$$ ]]; then \
		echo "Aborted."; \
		exit 1; \
	fi; \
	\
	echo ""; \
	echo "Creating and pushing tag..."; \
	git tag -a "$$tag" -m "Release $$tag" && \
	git push origin "$$tag" && \
	echo "" && \
	echo "✓ Tag pushed successfully!" && \
	echo "" && \
	repo_path=$$(git config --get remote.origin.url | sed 's|^https://github.com/||;s|^git@github.com:||;s|\.git$$||'); \
	echo "GitHub Actions workflows triggered:" && \
	echo "  - Release creation: https://github.com/$$repo_path/actions/workflows/release.yml" && \
	echo "  - PyPI publishing: https://github.com/$$repo_path/actions/workflows/publish.yml" && \
	echo "" && \
	echo "Monitor progress at: https://github.com/$$repo_path/actions"

# Alias for publish
release: publish

# Check code quality
lint:
	@echo "Running linters..."
	@if command -v uv >/dev/null 2>&1; then \
		uv run ruff check .; \
		uv run ruff format --check .; \
	elif command -v ruff >/dev/null 2>&1; then \
		ruff check .; \
		ruff format --check .; \
	else \
		echo "Ruff not found. Install with: pip install ruff"; \
	fi

# Fix code formatting
format:
	@echo "Formatting code..."
	@if command -v uv >/dev/null 2>&1; then \
		uv run ruff format .; \
		uv run ruff check --fix .; \
	elif command -v ruff >/dev/null 2>&1; then \
		ruff format .; \
		ruff check --fix .; \
	else \
		echo "Ruff not found. Install with: pip install ruff"; \
	fi

# Type checking
typecheck:
	@echo "Running type checker..."
	@if command -v uv >/dev/null 2>&1; then \
		uv run mypy src; \
	elif command -v mypy >/dev/null 2>&1; then \
		mypy src; \
	else \
		echo "MyPy not found. Install with: pip install mypy"; \
	fi

# Security checks
security:
	@echo "Running security checks..."
	@if command -v uv >/dev/null 2>&1; then \
		uv run bandit -r src -ll; \
	elif command -v bandit >/dev/null 2>&1; then \
		bandit -r src -ll; \
	else \
		echo "Bandit not found. Install with: pip install bandit"; \
	fi

# Run all checks
check: lint typecheck security test
	@echo "All checks completed."

# Show project info
info:
	@echo "Project Information:"
	@echo "==================="
	@if [ -f "pyproject.toml" ]; then \
		echo "pyproject.toml found"; \
		if command -v uv >/dev/null 2>&1; then \
			echo "UV version: $$(uv --version)"; \
		fi; \
		if command -v python >/dev/null 2>&1; then \
			echo "Python version: $$(python --version)"; \
		fi; \
	else \
		echo "No pyproject.toml found"; \
	fi
	@echo "Current directory: $$(pwd)"
	@echo "Git status:"
	@git status --porcelain 2>/dev/null || echo "Not a git repository"