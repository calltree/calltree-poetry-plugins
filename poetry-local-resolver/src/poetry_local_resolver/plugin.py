"""Simplified plugin for Poetry Local Resolver - only looks in parent workspace."""

import os
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from cleo.io.io import IO
from poetry.console.application import Application
from poetry.plugins.application_plugin import ApplicationPlugin

logger = logging.getLogger(__name__)


class LocalResolverPlugin(ApplicationPlugin):
    """A Poetry plugin that resolves packages from the parent workspace directory."""
    
    def __init__(self):
        self._workspace_packages: Dict[str, Path] = {}
        
    def activate(self, application: Application, io: Optional[IO] = None) -> None:
        """Activate the plugin and scan for local packages."""
        
        # Get the current project's directory
        try:
            if hasattr(application, 'poetry') and application.poetry:
                # Get the path from the TOMLFile object
                if hasattr(application.poetry.file, 'path'):
                    project_dir = Path(application.poetry.file.path).parent
                else:
                    # Fallback to current directory
                    project_dir = Path.cwd()
                    
                # Scan the parent workspace for packages
                self._scan_workspace(project_dir)
                
                if io and self._workspace_packages:
                    io.write_line(
                        f"<info>Poetry Local Resolver: Found {len(self._workspace_packages)} "
                        f"local packages in workspace</info>"
                    )
        except Exception as e:
            logger.debug(f"Error activating local resolver plugin: {e}")
    
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
                        logger.info(f"Found local package: {package_name} at {item}")
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