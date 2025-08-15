# Poetry Local Resolver Plugin

A Poetry plugin that automatically resolves packages locally first before checking remote repositories. This is particularly useful for monorepo setups or when working with multiple interdependent packages in the same workspace.

## Features

- Automatically scans workspace for local packages
- Resolves dependencies to local paths when available
- Falls back to remote repositories when local packages aren't found
- Configurable search paths and exclusion patterns
- Compatible with AWS CodeArtifact and other remote repositories

## Installation

### From AWS CodeArtifact

First, configure Poetry to use your CodeArtifact repository:

```bash
# Configure CodeArtifact repository
aws codeartifact login --tool pip --repository your-repo --domain your-domain --domain-owner your-account-id

# Get repository URL
export CODEARTIFACT_URL=$(aws codeartifact get-repository-endpoint --domain your-domain --repository your-repo --format pypi --query repositoryEndpoint --output text)

# Configure Poetry
poetry config repositories.codeartifact $CODEARTIFACT_URL
poetry config http-basic.codeartifact aws $(aws codeartifact get-authorization-token --domain your-domain --query authorizationToken --output text)
```

Then install the plugin:

```bash
poetry self add poetry-local-resolver --source codeartifact
```

### From PyPI (when available)

```bash
poetry self add poetry-local-resolver
```

### From Source

```bash
# Clone the repository
git clone https://github.com/yourusername/poetry-local-resolver.git
cd poetry-local-resolver

# Build the package
poetry build

# Install the plugin
poetry self add dist/poetry_local_resolver-*.whl
```

## Usage

Once installed, the plugin automatically activates and scans for local packages when you run Poetry commands.

### Basic Usage

The plugin works transparently. When you have dependencies in your `pyproject.toml`:

```toml
[tool.poetry.dependencies]
python = "^3.8"
calltree-common-lib = "^0.1.0"
calltree-utils = "^0.2.0"
```

If these packages exist locally in your workspace, they'll be resolved to local paths automatically. Otherwise, Poetry will fetch them from configured remote repositories.

### Configuration

You can configure the plugin behavior in your project's `pyproject.toml`:

```toml
[tool.poetry-local-resolver]
# Additional paths to search for packages (relative or absolute)
search_paths = [
    "../",           # Parent directory
    "../../libs",    # Custom library directory
    "/opt/packages"  # Absolute path
]

# Patterns to exclude when scanning directories
exclude = [
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    "node_modules",
    ".tox",
    "dist",
    "build",
    "*.egg-info"
]

# Packages to never resolve locally (always use remote)
disable_for = [
    "numpy",
    "pandas",
    "requests"
]
```

### Checking Local Resolution Status

Use the provided command to see which packages are available locally:

```bash
poetry local-resolver
```

This will show:
```
Local packages found in workspace:
  calltree-common-lib: /Users/you/workspace/calltree-common-lib
  calltree-utils: /Users/you/workspace/calltree-utils
```

## How It Works

1. **Workspace Scanning**: The plugin scans the workspace (parent directories and configured paths) for Python packages
2. **Package Detection**: It identifies packages by looking for `pyproject.toml` or `setup.py` files
3. **Dependency Resolution**: When Poetry resolves dependencies, the plugin intercepts and checks if a local version exists
4. **Path Substitution**: If found locally, it converts the dependency to a path dependency
5. **Fallback**: If not found locally, normal remote resolution continues

## Publishing to AWS CodeArtifact

To publish this plugin to your CodeArtifact repository:

```bash
# Build the package
poetry build

# Configure CodeArtifact credentials
aws codeartifact login --tool twine --repository your-repo --domain your-domain --domain-owner your-account-id

# Publish to CodeArtifact
poetry publish --repository codeartifact
```

## Development

### Setting Up Development Environment

```bash
# Clone the repository
git clone https://github.com/yourusername/poetry-local-resolver.git
cd poetry-local-resolver

# Install dependencies
poetry install

# Run tests
poetry run pytest

# Format code
poetry run black src tests
poetry run ruff check src tests

# Type checking
poetry run mypy src
```

### Running Tests

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=poetry_local_resolver

# Run specific test
poetry run pytest tests/test_plugin.py::test_workspace_scanning
```

## Workspace Structure Example

```
workspace/
├── calltree-api/
│   └── pyproject.toml
├── calltree-common-lib/
│   └── pyproject.toml
├── calltree-utils/
│   └── pyproject.toml
├── calltree-web/
│   └── pyproject.toml (with poetry-local-resolver config)
└── poetry-local-resolver/
    └── pyproject.toml
```

When you run `poetry install` in `calltree-web`, the plugin will:
1. Find `calltree-common-lib` and `calltree-utils` locally
2. Use those local versions instead of downloading from CodeArtifact
3. Any other dependencies not found locally will be fetched from CodeArtifact

## Troubleshooting

### Plugin Not Detecting Local Packages

1. Check that the packages have valid `pyproject.toml` files with a `name` field
2. Ensure the search paths are configured correctly
3. Verify packages aren't in excluded directories
4. Run `poetry local-resolver` to see what's detected

### Local Package Changes Not Reflected

Poetry caches dependency resolution. To force a refresh:

```bash
poetry lock --no-update
poetry install
```

### Conflicts with Remote Versions

If you need to force remote resolution for specific packages, add them to the `disable_for` list in your configuration.

## License

MIT License - see LICENSE file for details

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Support

For issues and questions, please use the GitHub issue tracker.