"""Poetry plugin that automatically resolves workspace packages to local paths."""

import os
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Set

from cleo.io.io import IO
from poetry.console.application import Application
from poetry.plugins.application_plugin import ApplicationPlugin
from poetry.repositories.repository import Repository
from poetry.core.packages.package import Package

logger = logging.getLogger(__name__)


class LocalWorkspaceRepository(Repository):
    """A repository that provides local workspace packages."""
    
    def __init__(self, name: str, packages: Dict[str, Path], project_dependencies: Set[str]):
        super().__init__(name)
        self._local_packages = packages
        self._project_dependencies = project_dependencies
        
    def find_packages(self, dependency):
        """Find packages matching the dependency in local workspace."""
        packages = []
        
        # Only resolve if this package is:
        # 1. In our local workspace
        # 2. Actually a dependency of the current project
        if (dependency.name in self._local_packages and 
            dependency.name in self._project_dependencies):
            local_path = self._local_packages[dependency.name]
            logger.info(f"Resolving {dependency.name} to local path: {local_path}")
            
            # Create a package that points to the local path
            # This will make Poetry use the local version instead of remote
            package = Package(
                name=dependency.name,
                version="0.0.0",  # Local packages bypass version checks
                source_type="directory",
                source_url=str(local_path),
                source_reference=str(local_path),
                source_resolved_reference=str(local_path)
            )
            packages.append(package)
            
        return packages
    
    def has_package(self, package):
        """Check if we have this package locally and it's a project dependency."""
        return (package.name in self._local_packages and 
                package.name in self._project_dependencies)


class LocalResolverPlugin(ApplicationPlugin):
    """A Poetry plugin that resolves packages from the parent workspace directory."""
    
    def __init__(self):
        self._workspace_packages: Dict[str, Path] = {}
        self._project_dependencies: Set[str] = set()
        
    def activate(self, application: Application, io: Optional[IO] = None) -> None:
        """Activate the plugin and hook into Poetry's dependency resolution."""
        
        # Get the current project's directory
        try:
            if hasattr(application, 'poetry') and application.poetry:
                # Get the path from the TOMLFile object
                if hasattr(application.poetry.file, 'path'):
                    project_dir = Path(application.poetry.file.path).parent
                else:
                    # Fallback to current directory
                    project_dir = Path.cwd()
                
                # Get the project's dependencies
                self._get_project_dependencies(application.poetry)
                
                # Scan the parent workspace for packages
                self._scan_workspace(project_dir)
                
                # Find which local packages are actually used by this project
                used_packages = self._workspace_packages.keys() & self._project_dependencies
                
                if used_packages:
                    # Add our local repository to Poetry's repository pool
                    self._inject_local_repository(application)
                    
                    if io:
                        io.write_line(
                            f"<info>Poetry Local Resolver: Will use local versions for: "
                            f"{', '.join(sorted(used_packages))}</info>"
                        )
                elif self._workspace_packages and io:
                    io.write_line(
                        f"<info>Poetry Local Resolver: Found {len(self._workspace_packages)} "
                        f"local packages, but none are dependencies of this project</info>"
                    )
        except Exception as e:
            logger.debug(f"Error activating local resolver plugin: {e}")
    
    def _get_project_dependencies(self, poetry) -> None:
        """Get all dependencies declared in the project's pyproject.toml."""
        try:
            # Get dependencies from the poetry package
            package = poetry.package
            
            # Get all dependencies (including dev dependencies)
            for dep in package.all_requires:
                self._project_dependencies.add(dep.name)
            
            logger.debug(f"Project has {len(self._project_dependencies)} dependencies")
        except Exception as e:
            logger.debug(f"Error getting project dependencies: {e}")
    
    def _scan_workspace(self, project_dir: Path) -> None:
        """Scan the parent workspace directory for Python packages."""
        
        # Get the parent directory (workspace)
        workspace_dir = project_dir.parent
        
        # Patterns to exclude
        exclude_patterns = [
            "__pycache__", ".git", ".venv", "venv", 
            "node_modules", ".tox", "dist", "build", 
            ".Trash", ".cache", "Library"
        ]
        
        # Look for Python packages in the workspace
        try:
            for item in workspace_dir.iterdir():
                if not item.is_dir():
                    continue
                    
                # Skip excluded directories
                if any(pattern in item.name for pattern in exclude_patterns):
                    continue
                
                # Skip the current project directory
                if item.resolve() == project_dir.resolve():
                    continue
                    
                # Check for pyproject.toml
                pyproject = item / "pyproject.toml"
                if pyproject.exists() and os.access(pyproject, os.R_OK):
                    package_name = self._get_package_name_from_pyproject(pyproject)
                    if package_name:
                        self._workspace_packages[package_name] = item
                        logger.debug(f"Found local package: {package_name} at {item}")
        except Exception as e:
            logger.debug(f"Error scanning workspace: {e}")
    
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
            logger.debug(f"Failed to parse {pyproject_path}: {e}")
        
        return None
    
    def _inject_local_repository(self, application: Application) -> None:
        """Inject our local repository into Poetry's repository pool."""
        try:
            if hasattr(application, 'poetry') and application.poetry:
                poetry = application.poetry
                
                # Create our local repository with project dependencies filter
                local_repo = LocalWorkspaceRepository(
                    name="local-workspace",
                    packages=self._workspace_packages,
                    project_dependencies=self._project_dependencies
                )
                
                # Add it to the repository pool with highest priority
                if hasattr(poetry, 'pool'):
                    pool = poetry.pool
                    # Add with primary priority (before all others)
                    # Priority.PRIMARY = "primary" in Poetry 2.x
                    pool.add_repository(local_repo, priority="primary")
                    
                    # Log which packages will be resolved locally
                    used_packages = self._workspace_packages.keys() & self._project_dependencies
                    logger.info(f"Added local workspace repository for: {', '.join(sorted(used_packages))}")
        except Exception as e:
            logger.error(f"Failed to inject local repository: {e}")