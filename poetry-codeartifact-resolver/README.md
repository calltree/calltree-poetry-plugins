# poetry-codeartifact-resolver

A Poetry plugin that dynamically resolves CodeArtifact repository URLs based on the `AWS_REGION` environment variable.

## Overview

This plugin allows you to use a special URL scheme in your `pyproject.toml` files that gets dynamically resolved to the correct AWS CodeArtifact URL based on your current region. This eliminates the need to hardcode specific regions or use `sed` commands in Docker builds.

## Installation

Install the plugin globally for all Poetry projects:

```bash
poetry self add poetry-codeartifact-resolver
```

## Authentication

The plugin supports different authentication methods:

### Local Development
```bash
calltree auth
```
This configures Poetry directly and is recommended for local development.

### CI/Docker
Set environment variables:
- `CODEARTIFACT_AUTH_TOKEN` - Authentication token for CodeArtifact
- `AWS_REGION` - AWS region (defaults to us-east-1)

The plugin focuses solely on URL resolution. Authentication is handled by Poetry's built-in system.

## Usage

### In your pyproject.toml

Use the special `codeartifact://` URL scheme instead of hardcoded URLs:

```toml
[[tool.poetry.source]]
name = "codeartifact"
url = "codeartifact://calltree/python-packages/simple"
priority = "primary"
```

### URL Format

The URL format is: `codeartifact://{domain}/{repository}/{path}`

- `domain` - The CodeArtifact domain (e.g., "calltree")
- `repository` - The repository name (e.g., "python-packages")
- `path` - Optional path (defaults to "simple")

### Automatic Resolution

The plugin automatically converts these URLs to the full CodeArtifact URL:

```
codeartifact://calltree/python-packages/simple
↓
https://calltree-831926607337.d.codeartifact.{AWS_REGION}.amazonaws.com/pypi/python-packages/simple/
```

### Region Switching

Simply change your region and Poetry will use the correct CodeArtifact endpoint:

```bash
export AWS_REGION=us-west-2
poetry install  # Uses us-west-2 CodeArtifact

export AWS_REGION=us-east-1
poetry install  # Uses us-east-1 CodeArtifact
```

## Error Handling

The plugin will fail with a clear error message if:
- The URL format is invalid

Authentication errors are handled by Poetry's built-in authentication system.

## Verbose Output

Use Poetry's verbose flag to see URL resolution in action:

```bash
poetry install -vv
# Output: CodeArtifact: Resolved to us-west-2 (https://calltree-831926607337.d.codeartifact.us-west-2.amazonaws.com/...)
```

## Benefits

- **Clean pyproject.toml** - No hardcoded regions
- **Docker-friendly** - Works in containers without sed commands  
- **Multi-region** - Easy switching between regions
- **Fail-fast** - Clear errors if not configured properly
- **Zero-config** - Works automatically once installed