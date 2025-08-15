"""Poetry plugin that adds --local flag to use workspace packages."""

import os
import logging
from pathlib import Path
from typing import Dict, Optional

from cleo.io.io import IO
from poetry.console.application import Application
from poetry.console.commands.install import InstallCommand
from poetry.plugins.application_plugin import ApplicationPlugin
from poetry.core.packages.directory_dependency import DirectoryDependency
from poetry.factory import Factory
from cleo.helpers import option

logger = logging.getLogger(__name__)


class LocalInstallCommand(InstallCommand):
    """Extended install command with --local flag."""
    
    name = "install"
    options = InstallCommand.options + [
        option("local", "L", "Use local workspace packages when available"),
    ]
    
    def handle(self) -> int:
        """Handle the install command with local workspace discovery."""
        use_local = self.option("local")
        
        if use_local:
            # Discover and apply local packages WITHOUT modifying pyproject.toml
            workspace_packages = self._discover_workspace_packages()
            if workspace_packages:
                self.line("")
                self.line("<comment>Using local workspace packages:</comment>")
                for name, path in workspace_packages.items():
                    rel_path = os.path.relpath(path, Path.cwd())
                    self.line(f"  • {name} → {rel_path}")
                self.line("")
                
                # Override the installer to use local packages
                self._configure_local_packages(workspace_packages)
        
        # Run the normal install
        return super().handle()
    
    def _discover_workspace_packages(self) -> Dict[str, Path]:
        """Discover packages in the workspace that match project dependencies."""
        workspace_packages = {}
        project_dir = Path.cwd()
        workspace_dir = project_dir.parent
        
        # Get project dependencies
        project_deps = set()
        if self.poetry and self.poetry.package:
            for dep in self.poetry.package.all_requires:
                project_deps.add(dep.name)
        
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
                    package_name = self._get_package_name(pyproject)
                    # Only include if it's a dependency of this project
                    if package_name and package_name in project_deps:
                        workspace_packages[package_name] = item
                        
        except Exception as e:
            logger.debug(f"Error discovering workspace packages: {e}")
            
        return workspace_packages
    
    def _get_package_name(self, pyproject_path: Path) -> Optional[str]:
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
        except Exception:
            pass
        return None
    
    def _configure_local_packages(self, workspace_packages: Dict[str, Path]):
        """Configure the installer to use local packages."""
        try:
            if not self.poetry:
                return
            
            # Get the locker and modify it to use local paths
            locker = self.poetry.locker
            if locker and hasattr(locker, "_lock_data") and locker._lock_data:
                # Modify lock data to point to local paths
                packages = locker._lock_data.get("package", [])
                for pkg in packages:
                    if pkg.get("name") in workspace_packages:
                        # Convert to directory source
                        local_path = workspace_packages[pkg["name"]]
                        pkg["source"] = {
                            "type": "directory",
                            "url": str(local_path)
                        }
                        pkg["develop"] = True
                        logger.info(f"Configured {pkg['name']} to use local path")
            
            # Also modify the pool to prioritize local packages
            pool = self.poetry.pool
            if pool and workspace_packages:
                # Create a mock repository for local packages
                from poetry.repositories.repository import Repository
                local_repo = Repository("local-workspace")
                
                # Add it with high priority
                pool.add_repository(local_repo, priority="primary")
                
        except Exception as e:
            logger.error(f"Failed to configure local packages: {e}")


class LocalResolverPlugin(ApplicationPlugin):
    """Plugin that adds --local flag for workspace package discovery."""
    
    def activate(self, application: Application, io: Optional[IO] = None) -> None:
        """Activate the plugin and replace the install command."""
        
        try:
            # Replace the install command with our extended version
            factory = application.command_loader
            if factory and hasattr(factory, "_factories"):
                # Override the install command factory
                factory._factories["install"] = lambda: LocalInstallCommand()
                logger.info("Local resolver plugin activated - use 'poetry install --local'")
                
        except Exception as e:
            logger.debug(f"Failed to activate local resolver: {e}")