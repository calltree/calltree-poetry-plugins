"""Main plugin implementation for Poetry Local Resolver."""

import os
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from cleo.io.io import IO
from poetry.core.packages.dependency import Dependency
from poetry.core.packages.path_dependency import PathDependency
from poetry.core.packages.directory_dependency import DirectoryDependency
from poetry.plugins.application_plugin import ApplicationPlugin
from poetry.console.application import Application
from poetry.console.commands.installer_command import InstallerCommand
from poetry.installation.installer import Installer
from poetry.repositories.repository_pool import RepositoryPool
from poetry.core.packages.package import Package
from poetry.repositories.installed_repository import InstalledRepository

logger = logging.getLogger(__name__)


class LocalResolverPlugin(ApplicationPlugin):
    """Plugin that resolves packages locally first before checking remote repositories."""
    
    def __init__(self):
        self._workspace_packages: Dict[str, Path] = {}
        self._config: Dict[str, Any] = {}
        
    def activate(self, application: Application, io: Optional[IO] = None) -> None:
        """Activate the plugin and hook into Poetry's dependency resolution."""
        
        # Get the current project's directory
        if hasattr(application, 'poetry') and application.poetry:
            project_dir = application.poetry.file.parent
            self._load_config(project_dir)
            self._scan_workspace(project_dir)
            
            # Hook into the dependency resolution process
            self._patch_dependency_resolution(application)
            
            if io:
                io.write_line(
                    f"<info>Poetry Local Resolver: Found {len(self._workspace_packages)} "
                    f"local packages in workspace</info>"
                )
    
    def _load_config(self, project_dir: Path) -> None:
        """Load plugin configuration from pyproject.toml."""
        try:
            import toml
            config_file = project_dir / "pyproject.toml"
            if config_file.exists():
                data = toml.load(config_file)
                self._config = data.get("tool", {}).get("poetry-local-resolver", {})
        except Exception as e:
            logger.warning(f"Failed to load plugin config: {e}")
            self._config = {}
    
    def _scan_workspace(self, project_dir: Path) -> None:
        """Scan the workspace for available packages."""
        # Default search paths
        search_paths = [
            project_dir.parent,  # Parent directory (workspace root)
            project_dir.parent.parent,  # Grandparent directory
        ]
        
        # Add custom search paths from config
        custom_paths = self._config.get("search_paths", [])
        for path_str in custom_paths:
            path = Path(path_str)
            if not path.is_absolute():
                path = project_dir / path
            if path.exists():
                search_paths.append(path.resolve())
        
        # Exclude patterns
        exclude_patterns = self._config.get("exclude", [
            "__pycache__", ".git", ".venv", "venv", 
            "node_modules", ".tox", "dist", "build"
        ])
        
        for search_path in search_paths:
            if not search_path.exists():
                continue
                
            # Look for Python packages (directories with pyproject.toml or setup.py)
            for item in search_path.iterdir():
                if not item.is_dir():
                    continue
                    
                # Skip excluded directories
                if any(pattern in item.name for pattern in exclude_patterns):
                    continue
                
                # Skip the current project directory
                if item.resolve() == project_dir.resolve():
                    continue
                    
                # Check for package markers
                pyproject = item / "pyproject.toml"
                setup_py = item / "setup.py"
                
                if pyproject.exists():
                    package_name = self._get_package_name_from_pyproject(pyproject)
                    if package_name:
                        self._workspace_packages[package_name] = item
                        logger.debug(f"Found local package: {package_name} at {item}")
                elif setup_py.exists():
                    package_name = item.name
                    self._workspace_packages[package_name] = item
                    logger.debug(f"Found local package: {package_name} at {item}")
    
    def _get_package_name_from_pyproject(self, pyproject_path: Path) -> Optional[str]:
        """Extract package name from pyproject.toml."""
        try:
            import toml
            data = toml.load(pyproject_path)
            
            # Try Poetry section first
            poetry_section = data.get("tool", {}).get("poetry", {})
            if "name" in poetry_section:
                return poetry_section["name"]
            
            # Try PEP 621 project section
            project_section = data.get("project", {})
            if "name" in project_section:
                return project_section["name"]
                
        except Exception as e:
            logger.warning(f"Failed to parse {pyproject_path}: {e}")
        
        return None
    
    def _patch_dependency_resolution(self, application: Application) -> None:
        """Patch Poetry's dependency resolution to use local packages first."""
        
        # Store original poetry instance
        poetry = application.poetry
        if not poetry:
            return
            
        # Get the original pool
        original_pool = poetry.pool
        
        # Create a custom resolver that checks local packages first
        def resolve_dependency(dependency: Dependency) -> Optional[Dependency]:
            """Resolve a dependency to a local package if available."""
            
            # Skip if already a path dependency
            if isinstance(dependency, (PathDependency, DirectoryDependency)):
                return dependency
            
            # Check if we have this package locally
            if dependency.name in self._workspace_packages:
                local_path = self._workspace_packages[dependency.name]
                
                # Check if local resolver is disabled for this package
                disabled_packages = self._config.get("disable_for", [])
                if dependency.name in disabled_packages:
                    logger.debug(f"Local resolution disabled for {dependency.name}")
                    return dependency
                
                # Create a path dependency
                logger.info(f"Resolving {dependency.name} to local path: {local_path}")
                
                # Create a new path dependency with the same constraints
                path_dep = Dependency(
                    name=dependency.name,
                    constraint="*",  # Path dependencies don't use version constraints
                    optional=dependency.is_optional(),
                    groups=dependency.groups,
                    allows_prereleases=dependency.allows_prereleases(),
                    extras=dependency.extras,
                    source_type="directory",
                    source_url=str(local_path)
                )
                
                # Set the path
                path_dep._source_type = "directory"
                path_dep._source_url = str(local_path)
                
                return path_dep
            
            return dependency
        
        # Patch the dependency factory
        original_create_dependency = poetry.package.dependency_group._create_dependency
        
        def patched_create_dependency(name: str, constraint: Any, **kwargs) -> Dependency:
            """Create dependency with local resolution."""
            dep = original_create_dependency(name, constraint, **kwargs)
            resolved = resolve_dependency(dep)
            return resolved if resolved else dep
        
        # Apply the patch
        for group in poetry.package.dependency_groups:
            poetry.package.dependency_group(group)._create_dependency = patched_create_dependency


class LocalResolverCommand(InstallerCommand):
    """Command to show local package resolution status."""
    
    name = "local-resolver"
    description = "Show local package resolution status"
    
    def handle(self) -> int:
        """Handle the command."""
        plugin = LocalResolverPlugin()
        plugin._scan_workspace(self.poetry.file.parent)
        
        if not plugin._workspace_packages:
            self.line("<comment>No local packages found in workspace</comment>")
            return 0
        
        self.line("<info>Local packages found in workspace:</info>")
        for name, path in sorted(plugin._workspace_packages.items()):
            self.line(f"  <comment>{name}</comment>: {path}")
        
        return 0