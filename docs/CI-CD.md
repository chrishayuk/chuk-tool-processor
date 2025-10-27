# CI/CD Pipeline Documentation

This document provides comprehensive documentation for the CI/CD workflows in the `chuk-tool-processor` project.

## Overview

The project uses GitHub Actions for continuous integration and continuous deployment. The pipeline is fully automated and consists of three main workflows:

1. **Test Workflow** - Runs on every push and pull request
2. **Release Workflow** - Creates GitHub releases when tags are pushed
3. **Publish Workflow** - Publishes to PyPI after releases are created

## Table of Contents

- [Workflows](#workflows)
  - [Test Workflow](#test-workflow)
  - [Release Workflow](#release-workflow)
  - [Publish Workflow](#publish-workflow)
- [Release Process](#release-process)
  - [Quick Start](#quick-start)
  - [Detailed Steps](#detailed-steps)
- [Version Management](#version-management)
- [Troubleshooting](#troubleshooting)
- [Configuration](#configuration)

## Workflows

### Test Workflow

**File**: `.github/workflows/test.yml`

**Triggers**:
- Push to `main` or `develop` branches
- Pull requests to `main` branch
- Manual trigger via workflow dispatch

**What it does**:
1. Runs tests across multiple platforms and Python versions:
   - **Platforms**: Ubuntu, Windows, macOS
   - **Python versions**: 3.11, 3.12, 3.13
2. Executes quality checks:
   - Code linting with `ruff`
   - Code formatting validation
   - Type checking with `mypy`
   - Test suite with `pytest`
3. Generates coverage reports (uploaded to Codecov)
4. Enforces 70% minimum coverage threshold

**Matrix Strategy**: Tests run in parallel across 9 combinations (3 platforms × 3 Python versions)

### Release Workflow

**File**: `.github/workflows/release.yml`

**Triggers**:
- Push of version tags matching `v*.*.*` pattern (e.g., `v0.9.3`)
- Manual trigger via workflow dispatch (with tag input)

**What it does**:
1. **Version Validation**:
   - Extracts version from the tag
   - Verifies it matches the version in `pyproject.toml`
   - Fails if versions don't match

2. **Changelog Generation**:
   - Finds the previous tag
   - Generates changelog from commit messages since last release
   - Formats commits as bulleted list
   - Includes "Full Changelog" link comparing tags

3. **GitHub Release Creation**:
   - Creates a new GitHub release
   - Attaches the auto-generated changelog
   - Marks release as published (not draft)

**Example Changelog Output**:
```markdown
## What's Changed

* Add new feature for async tool execution (a1b2c3d)
* Fix bug in error handling (d4e5f6g)
* Update documentation (h7i8j9k)

**Full Changelog**: https://github.com/owner/repo/compare/v0.9.2...v0.9.3
```

### Publish Workflow

**File**: `.github/workflows/publish.yml`

**Triggers**:
- GitHub release published event (triggered automatically by release workflow)
- Manual trigger via workflow dispatch

**What it does**:
1. **Test Job** (optional):
   - Calls the test workflow as a reusable workflow
   - Runs full test suite across all platforms
   - Can be skipped via workflow dispatch input (emergency use only)

2. **Build Job**:
   - Checks out code
   - Sets up Python 3.12 with `uv`
   - Builds source distribution (`.tar.gz`) and wheel (`.whl`)
   - Uploads build artifacts

3. **Publish Job**:
   - Downloads build artifacts
   - Publishes to PyPI using trusted publishing
   - No API tokens required (uses OIDC authentication)

**Security**: Uses PyPI's [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) for tokenless, secure authentication.

## Release Process

### Quick Start

The fastest way to create a release:

```bash
# 1. Bump version
make bump-patch    # or bump-minor, bump-major

# 2. Commit the version change
git add pyproject.toml
git commit -m "version X.Y.Z"
git push

# 3. Trigger automated release
make publish
```

That's it! The automation handles the rest.

### Detailed Steps

#### Step 1: Update Version

Choose the appropriate version bump based on [Semantic Versioning](https://semver.org/):

```bash
# Bug fixes and patches
make bump-patch    # 0.9.2 -> 0.9.3

# New features (backwards compatible)
make bump-minor    # 0.9.2 -> 0.10.0

# Breaking changes
make bump-major    # 0.9.2 -> 1.0.0
```

Or manually edit `pyproject.toml`:
```toml
[project]
version = "X.Y.Z"
```

#### Step 2: Commit and Push

```bash
git add pyproject.toml
git commit -m "version X.Y.Z"
git push origin main
```

#### Step 3: Run Pre-Release Checks (Optional)

```bash
# Run all quality checks locally
make check

# Or individual checks
make lint          # Code quality
make typecheck     # Type checking
make test          # Run tests
make test-cov      # Tests with coverage
```

#### Step 4: Trigger Release

```bash
make publish
```

This command will:
1. Show current version and tag name
2. Run pre-flight checks:
   - Verify working directory is clean
   - Check tag doesn't already exist
   - Display current branch
3. Ask for confirmation
4. Create and push the version tag
5. Display links to monitor GitHub Actions

**Example Output**:
```
Starting automated release process...

Version: 0.9.3
Tag: v0.9.3

Pre-flight checks:
==================
✓ Working directory is clean
✓ Tag v0.9.3 does not exist yet
✓ Current branch: main

This will:
  1. Create and push tag v0.9.3
  2. Trigger GitHub Actions to:
     - Create a GitHub release with changelog
     - Run tests on all platforms
     - Build and publish to PyPI

Continue? (y/N)
```

#### Step 5: Monitor Progress

After confirming, you'll receive links to monitor the workflows:
- **Release creation**: Watch the changelog being generated
- **PyPI publishing**: Monitor tests, build, and publish

The entire process typically takes 10-15 minutes.

#### Step 6: Verify Release

Once workflows complete:

1. **Check GitHub Release**: Visit the [releases page](../../releases)
2. **Verify PyPI**: Check [PyPI project page](https://pypi.org/project/chuk-tool-processor/)
3. **Test Installation**:
   ```bash
   pip install --upgrade chuk-tool-processor
   pip show chuk-tool-processor  # Verify version
   ```

## Version Management

### Versioning Strategy

We follow [Semantic Versioning 2.0.0](https://semver.org/):

```
MAJOR.MINOR.PATCH

1.2.3
│ │ │
│ │ └─── Patch: Bug fixes, backwards compatible
│ └───── Minor: New features, backwards compatible
└─────── Major: Breaking changes
```

### Version Bump Guidelines

**Patch Version** (`0.0.X`):
- Bug fixes
- Documentation updates
- Internal refactoring
- Performance improvements (non-breaking)

**Minor Version** (`0.X.0`):
- New features
- New APIs (backwards compatible)
- Deprecation warnings
- Significant internal improvements

**Major Version** (`X.0.0`):
- Breaking API changes
- Removal of deprecated features
- Major architectural changes
- Python version requirement changes

### Pre-Release Versions

For alpha/beta releases, manually edit `pyproject.toml`:
```toml
version = "1.0.0a1"  # Alpha
version = "1.0.0b1"  # Beta
version = "1.0.0rc1" # Release candidate
```

Then follow the normal release process. The publish workflow will correctly handle pre-release versions.

## Troubleshooting

### Common Issues

#### Issue: Tag Already Exists

**Error**: `✗ Tag v0.9.3 already exists`

**Solution**:
```bash
# Delete tag locally and remotely
git tag -d v0.9.3
git push origin :refs/tags/v0.9.3

# Then retry
make publish
```

#### Issue: Version Mismatch

**Error**: `Tag version does not match pyproject.toml version`

**Solution**:
1. Check `pyproject.toml` version
2. Ensure the version matches what you expect
3. Delete the incorrect tag if needed
4. Create new tag with correct version

#### Issue: Uncommitted Changes

**Error**: `✗ Working directory has uncommitted changes`

**Solution**:
```bash
# Option 1: Commit changes
git add .
git commit -m "Your commit message"

# Option 2: Stash changes
git stash

# Then retry
make publish
```

#### Issue: Tests Failing

**Error**: Tests fail during publish workflow

**Solution**:
1. Check [workflow logs](../../actions/workflows/publish.yml)
2. Fix failing tests locally
3. Increment patch version
4. Create new release

**Emergency Override** (not recommended):
```bash
# Manually trigger publish workflow and skip tests
# Go to Actions > Publish to PyPI > Run workflow
# Check "Skip test job"
```

#### Issue: PyPI Publish Fails

**Error**: Publishing to PyPI fails

**Common Causes**:
1. **Version already exists on PyPI**: Increment version and retry
2. **Trusted publishing not configured**: See [Configuration](#pypi-trusted-publishing)
3. **Network issues**: Wait and retry via workflow dispatch

**Check**:
1. View [workflow logs](../../actions/workflows/publish.yml)
2. Verify PyPI environment is configured
3. Check PyPI project settings

### Debug Checklist

Before reporting issues, verify:

- [ ] Working directory is clean (`git status`)
- [ ] Version in `pyproject.toml` is correct
- [ ] Tests pass locally (`make test`)
- [ ] Linting passes (`make lint`)
- [ ] Tag doesn't already exist (`git tag -l`)
- [ ] You have push permissions to the repository
- [ ] GitHub Actions are enabled for the repository

## Configuration

### GitHub Repository Settings

#### Required Settings

1. **Actions Permissions**:
   - Go to: Settings > Actions > General
   - Enable: "Allow all actions and reusable workflows"
   - Workflow permissions: "Read and write permissions"
   - Enable: "Allow GitHub Actions to create and approve pull requests"

2. **Environments**:
   - Go to: Settings > Environments
   - Create environment: `pypi`
   - Configure PyPI trusted publishing (see below)

#### PyPI Trusted Publishing

Set up tokenless publishing with PyPI:

1. **On PyPI**:
   - Go to your project settings: https://pypi.org/manage/project/chuk-tool-processor/settings/
   - Navigate to "Publishing" section
   - Click "Add a new publisher"
   - Fill in:
     - **Owner**: `chrishayuk` (your GitHub username/org)
     - **Repository**: `chuk-tool-processor`
     - **Workflow name**: `publish.yml`
     - **Environment name**: `pypi`
   - Click "Add"

2. **On GitHub**:
   - No additional configuration needed
   - The workflow uses OIDC to authenticate with PyPI
   - No API tokens stored in GitHub secrets

**Benefits**:
- No API tokens to manage or rotate
- More secure (tokens can't leak)
- Automatic authentication
- Scoped to specific workflow and repository

### Workflow Customization

#### Modify Test Matrix

Edit `.github/workflows/test.yml`:

```yaml
matrix:
  os: [ubuntu-latest, windows-latest, macos-latest]
  python-version: ["3.11", "3.12", "3.13"]
```

Add or remove platforms/versions as needed.

#### Change Coverage Threshold

Edit `.github/workflows/test.yml`:

```yaml
- name: Check coverage threshold
  run: |
    # Change 70 to your desired threshold
    if coverage < 70:
```

#### Customize Changelog Format

Edit `.github/workflows/release.yml`:

```yaml
- name: Generate changelog
  run: |
    # Customize the git log format
    git log --pretty=format:"* %s (%h)" --no-merges
```

### Local Development Setup

Install development dependencies:

```bash
# Using uv (recommended)
uv sync --dev

# Using pip
pip install -e ".[dev]"
```

Install pre-commit hooks:

```bash
pre-commit install
```

This ensures code quality checks run before each commit.

## Workflow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Developer                                │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         │ make bump-patch
                         │ git commit & push
                         │ make publish
                         ▼
                   ┌───────────┐
                   │  Git Tag  │
                   │  v0.9.3   │
                   └─────┬─────┘
                         │
          ┌──────────────┴──────────────┐
          │                             │
          ▼                             ▼
┌───────────────────┐         ┌──────────────────┐
│ Release Workflow  │         │  Test Workflow   │
│                   │         │                  │
│ 1. Validate tag   │         │ 1. Lint          │
│ 2. Generate       │         │ 2. Typecheck     │
│    changelog      │         │ 3. Run tests     │
│ 3. Create release │         │ 4. Coverage      │
└────────┬──────────┘         └────────┬─────────┘
         │                             │
         │ Triggers on publish         │
         ▼                             │
┌──────────────────────────────────────┼─────────┐
│         Publish Workflow             │         │
│                                      │         │
│ ┌──────────────┐     Calls          │         │
│ │  Test Job    │◄────────────────────┘         │
│ └──────┬───────┘                               │
│        │ Success                               │
│        ▼                                       │
│ ┌──────────────┐                               │
│ │  Build Job   │                               │
│ │              │                               │
│ │ - Build dist │                               │
│ │ - Build wheel│                               │
│ └──────┬───────┘                               │
│        │                                       │
│        ▼                                       │
│ ┌──────────────┐                               │
│ │ Publish Job  │                               │
│ │              │                               │
│ │ - Upload to  │                               │
│ │   PyPI       │                               │
│ └──────────────┘                               │
└───────────────────────────────────────────────┘
         │
         │
         ▼
  ┌────────────┐
  │   PyPI     │
  │  Released  │
  └────────────┘
```

## Additional Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [PyPI Trusted Publishing Guide](https://docs.pypi.org/trusted-publishers/)
- [Semantic Versioning Specification](https://semver.org/)
- [UV Documentation](https://docs.astral.sh/uv/)
- [RELEASING.md](../RELEASING.md) - Detailed release process guide

## Support

If you encounter issues with the CI/CD pipeline:

1. Check this documentation
2. Review [RELEASING.md](../RELEASING.md) troubleshooting section
3. Check [GitHub Actions logs](../../actions)
4. Open an issue on GitHub

---

**Last Updated**: 2025-10-27
**Maintained By**: CHUK Team
