"""Poetry plugin that silently overrides dependencies to use local workspace packages."""

import os
import logging
from pathlib import Path
from typing import Dict, Optional

from cleo.io.io import IO
from poetry.console.application import Application
from poetry.plugins.application_plugin import ApplicationPlugin
from poetry.core.packages.directory_dependency import DirectoryDependency
from poetry.core.packages.dependency import Dependency

logger = logging.getLogger(__name__)


class LocalResolverPlugin(ApplicationPlugin):
    """A Poetry plugin that silently overrides to use local workspace packages."""
    
    def activate(self, application: Application, io: Optional[IO] = None) -> None:
        """Activate the plugin and patch Poetry's dependency creation."""
        
        try:
            if not hasattr(application, 'poetry') or not application.poetry:
                return
                
            project_dir = Path.cwd()
            
            # Scan workspace for local packages
            workspace_packages = self._scan_workspace(project_dir)
            
            if not workspace_packages:
                return
            
            # Monkey-patch the dependency factory to use local paths
            original_create_dependency = Dependency.create_from_pep_508
            
            def create_dependency_with_local_override(name, constraint=None, **kwargs):
                """Override dependency creation to use local paths when available."""
                
                # Parse the dependency name (might have extras like "package[extra]")
                dep_name = name.split("[")[0] if "[" in name else name
                
                # Check if we have this package locally
                if dep_name in workspace_packages:
                    local_path = workspace_packages[dep_name]
                    logger.info(f"Silently using local path for {dep_name}: {local_path}")
                    
                    # Create a directory dependency instead
                    return DirectoryDependency(
                        name=dep_name,
                        path=local_path,
                        develop=True  # Use develop mode for live changes
                    )
                
                # Otherwise use the original method
                return original_create_dependency(name, constraint, **kwargs)
            
            # Apply the monkey patch
            Dependency.create_from_pep_508 = staticmethod(create_dependency_with_local_override)
            
            # Also patch the Package's add_dependency method
            if hasattr(application.poetry, 'package'):
                package = application.poetry.package
                original_add_dependency = package.add_dependency
                
                def add_dependency_with_override(dep):
                    """Override add_dependency to use local paths."""
                    if isinstance(dep, Dependency) and not isinstance(dep, DirectoryDependency):
                        if dep.name in workspace_packages:
                            local_path = workspace_packages[dep.name]
                            logger.info(f"Overriding {dep.name} to use local path: {local_path}")
                            dep = DirectoryDependency(
                                name=dep.name,
                                path=local_path,
                                develop=True
                            )
                    return original_add_dependency(dep)
                
                package.add_dependency = add_dependency_with_override
            
            # Log what we're doing (only if verbose)
            if workspace_packages and logger.isEnabledFor(logging.INFO):
                logger.info(f"Local resolver active for: {', '.join(workspace_packages.keys())}")
                
        except Exception as e:
            logger.error(f"Failed to activate local resolver: {e}")
    
    def _scan_workspace(self, project_dir: Path) -> Dict[str, Path]:
        """Scan the parent workspace directory for Python packages."""
        
        workspace_packages = {}
        workspace_dir = project_dir.parent
        
        # Patterns to exclude
        exclude_patterns = [
            "__pycache__", ".git", ".venv", "venv", 
            "node_modules", ".tox", "dist", "build", 
            ".Trash", ".cache", "Library"
        ]
        
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
                        # Get project dependencies to only override what's needed
                        if self._is_project_dependency(project_dir, package_name):
                            workspace_packages[package_name] = item
                            logger.debug(f"Will override {package_name} with local path: {item}")
                        
        except Exception as e:
            logger.debug(f"Error scanning workspace: {e}")
            
        return workspace_packages
    
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
    
    def _is_project_dependency(self, project_dir: Path, package_name: str) -> bool:
        """Check if a package is a dependency of the current project."""
        try:
            pyproject_path = project_dir / "pyproject.toml"
            if not pyproject_path.exists():
                return False
                
            import toml
            data = toml.load(pyproject_path)
            poetry_section = data.get("tool", {}).get("poetry", {})
            
            # Check main dependencies
            deps = poetry_section.get("dependencies", {})
            if package_name in deps:
                return True
            
            # Check all dependency groups
            groups = poetry_section.get("group", {})
            for group_name, group_data in groups.items():
                if package_name in group_data.get("dependencies", {}):
                    return True
                    
            # Check legacy dev-dependencies
            if package_name in poetry_section.get("dev-dependencies", {}):
                return True
                
        except Exception as e:
            logger.debug(f"Error checking dependencies: {e}")
            
        return False