# Release Process

This document describes how to create a new release of `chuk-tool-processor`.

## Automated Release Workflow

The project uses GitHub Actions to automate the release process. When you create a new tag, it will:

1. Create a GitHub release with auto-generated changelog
2. Run tests across all supported platforms and Python versions
3. Build the package
4. Publish to PyPI

## Prerequisites

Before creating a release, ensure:

- [ ] All tests pass locally: `uv run pytest`
- [ ] Linting passes: `uv run ruff check . && uv run ruff format --check .`
- [ ] Type checking passes: `uv run mypy src`
- [ ] `pyproject.toml` version has been updated
- [ ] All changes are committed and pushed to the main branch

## Creating a Release

### Step 1: Update Version

Edit `pyproject.toml` and update the version number:

```toml
[project]
version = "X.Y.Z"
```

Commit and push this change:

```bash
git add pyproject.toml
git commit -m "version X.Y.Z"
git push origin main
```

### Step 2: Create and Push a Tag

Create a git tag matching the version in `pyproject.toml`:

```bash
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin vX.Y.Z
```

**Important**: The tag must:
- Start with `v` (e.g., `v0.9.3`)
- Match the version in `pyproject.toml` exactly (the release workflow will verify this)

### Step 3: Automated Process

Once you push the tag, GitHub Actions will automatically:

1. **Create GitHub Release** (`.github/workflows/release.yml`)
   - Generate a changelog from commits since the last tag
   - Create a GitHub release with the changelog
   - Mark the release as published

2. **Publish to PyPI** (`.github/workflows/publish.yml`)
   - Triggered by the GitHub release being published
   - Run the full test suite across all platforms and Python versions (3.11, 3.12, 3.13)
   - Build the package using `uv build`
   - Publish to PyPI using trusted publishing (no API tokens needed)

### Step 4: Verify Release

After the workflows complete:

1. Check the GitHub Releases page for the new release
2. Verify the package on [PyPI](https://pypi.org/project/chuk-tool-processor/)
3. Test installation: `pip install chuk-tool-processor==X.Y.Z`

## Manual Release (Emergency Use Only)

If you need to manually trigger a release:

### Manual GitHub Release

Go to the Actions tab in GitHub and click "Run workflow" on `release.yml`, then enter the tag name (e.g., `v0.9.3`).

### Manual PyPI Publish

Go to the Actions tab in GitHub and click "Run workflow" on `publish.yml`. You can optionally skip tests (not recommended).

## Troubleshooting

### Tag Already Exists

If you need to move a tag:

```bash
git tag -d vX.Y.Z                    # Delete locally
git push origin :refs/tags/vX.Y.Z    # Delete remotely
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin vX.Y.Z
```

### Version Mismatch

If the tag doesn't match `pyproject.toml`, the release workflow will fail. Update `pyproject.toml` and create a new tag.

### Failed PyPI Publish

If publishing fails:

1. Check the workflow logs for `publish.yml` in GitHub Actions
2. Verify the PyPI environment is configured in GitHub repository settings
3. Ensure PyPI trusted publishing is set up correctly

### Failed Tests

If tests fail during publishing:

1. Fix the issues locally
2. Increment the version patch number
3. Create a new tag and release

## Versioning Guidelines

Follow [Semantic Versioning](https://semver.org/):

- **Major version** (X.0.0): Breaking changes
- **Minor version** (0.X.0): New features, backwards compatible
- **Patch version** (0.0.X): Bug fixes, backwards compatible

## PyPI Trusted Publishing Setup

The project uses [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/) for secure, tokenless publishing:

1. No API tokens are stored in GitHub secrets
2. GitHub Actions authenticates directly with PyPI
3. Publishing is restricted to the specific workflow and repository

If you need to set this up for a new project:

1. Go to PyPI project settings
2. Add a trusted publisher with:
   - Repository: `chuk-tool-processor`
   - Workflow: `publish.yml`
   - Environment: `pypi`
