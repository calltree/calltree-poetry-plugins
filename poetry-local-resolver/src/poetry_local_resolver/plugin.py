"""Poetry plugin that adds --local flag to use workspace packages."""

import os
import sys
import shutil
import logging
from pathlib import Path
from typing import Dict, Optional

from cleo.io.io import IO
from poetry.console.application import Application
from poetry.console.commands.install import InstallCommand
from poetry.plugins.application_plugin import ApplicationPlugin
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
        
        # First run the normal install
        result = super().handle()
        
        if use_local and result == 0:
            # After successful install, replace with local packages
            workspace_packages = self._discover_workspace_packages()
            if workspace_packages:
                self.line("")
                self.line("<comment>Linking local workspace packages:</comment>")
                
                for name, path in workspace_packages.items():
                    rel_path = os.path.relpath(path, Path.cwd())
                    if self._link_local_package(name, path):
                        self.line(f"  <info>✓ {name} → {rel_path}</info>")
                    else:
                        self.line(f"  <error>✗ {name} (failed to link)</error>")
                
                self.line("")
                self.line("<comment>Local packages are now active. Changes will be reflected immediately.</comment>")
        
        return result
    
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
    
    def _link_local_package(self, package_name: str, local_path: Path) -> bool:
        """Replace installed package with symlink to local version."""
        try:
            # Get the virtualenv path
            venv_path = self.env.path if self.env else None
            if not venv_path:
                return False
            
            # Find the installed package location
            # Use the environment's Python version, not the current interpreter's
            python_version = f"python{self.env.version_info[0]}.{self.env.version_info[1]}" if hasattr(self.env, 'version_info') else f"python{sys.version_info.major}.{sys.version_info.minor}"
            site_packages = venv_path / "lib" / python_version / "site-packages"
            if not site_packages.exists():
                # Try alternative path for Windows or non-standard layouts
                site_packages = venv_path / "site-packages"
                if not site_packages.exists():
                    logger.error(f"Could not find site-packages in {venv_path}")
                    return False
            
            # Convert package name to module name (e.g., calltree-common-lib -> calltree_common_lib)
            module_name = package_name.replace("-", "_")
            installed_path = site_packages / module_name
            
            # Find the source directory in the local package
            # Try common source locations
            source_candidates = [
                local_path / "src" / module_name,
                local_path / module_name,
                local_path / "lib" / module_name,
            ]
            
            source_path = None
            for candidate in source_candidates:
                if candidate.exists() and candidate.is_dir():
                    source_path = candidate
                    break
            
            if not source_path:
                logger.warning(f"Could not find source directory for {package_name} in {local_path}")
                logger.warning(f"Tried: {[str(c) for c in source_candidates]}")
                return False
            
            # First, use pip to install in editable mode instead of symlinking
            # This creates proper metadata that Poetry can work with
            try:
                pip_cmd = [sys.executable, "-m", "pip", "install", "-e", str(local_path), "--no-deps"]
                import subprocess
                result = subprocess.run(pip_cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    logger.info(f"Installed {package_name} in editable mode from {local_path}")
                    
                    # Mark as locally developed
                    for info_dir in site_packages.glob(f"{module_name}*.dist-info"):
                        marker_file = info_dir / "LOCAL_DEVELOPMENT"
                        marker_file.write_text(f"Editable install from: {local_path}\n")
                    
                    return True
                else:
                    logger.warning(f"Failed to install {package_name} in editable mode: {result.stderr}")
                    # Fall back to symlink method
                    
            except Exception as e:
                logger.debug(f"Could not use pip for editable install: {e}")
            
            # Fallback: Remove existing installation and create symlink
            if installed_path.exists():
                if installed_path.is_symlink():
                    installed_path.unlink()
                elif installed_path.is_dir():
                    shutil.rmtree(installed_path)
                else:
                    installed_path.unlink()
            
            # Create symlink to local version
            installed_path.symlink_to(source_path)
            logger.info(f"Linked {package_name}: {installed_path} -> {source_path}")
            
            # Create a minimal dist-info directory with RECORD file
            # to prevent Poetry/pip uninstall errors
            dist_info_name = f"{module_name}-0.0.0.dist-info"
            dist_info_path = site_packages / dist_info_name
            dist_info_path.mkdir(exist_ok=True)
            
            # Create METADATA file
            metadata_content = f"""Metadata-Version: 2.1
Name: {package_name}
Version: 0.0.0
Summary: Local development version
Home-page: {local_path}
"""
            (dist_info_path / "METADATA").write_text(metadata_content)
            
            # Create RECORD file listing the symlink
            record_content = f"{module_name},,\n{dist_info_name}/METADATA,,\n{dist_info_name}/RECORD,,\n{dist_info_name}/LOCAL_DEVELOPMENT,,\n"
            (dist_info_path / "RECORD").write_text(record_content)
            
            # Mark as local development
            (dist_info_path / "LOCAL_DEVELOPMENT").write_text(f"Symlinked to: {source_path}\n")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to link {package_name}: {e}")
            return False


class LocalResolverPlugin(ApplicationPlugin):
    """Plugin that adds --local flag for workspace package discovery."""
    
    def activate(self, application: Application, io: Optional[IO] = None) -> None:
        """Activate the plugin and replace the install command."""
        
        try:
            # Configure logging
            logging.basicConfig(
                level=logging.INFO,
                format='[%(name)s] %(message)s'
            )
            
            # Replace the install command with our extended version
            factory = application.command_loader
            if factory and hasattr(factory, "_factories"):
                # Override the install command factory
                factory._factories["install"] = lambda: LocalInstallCommand()
                logger.info("Local resolver plugin activated - use 'poetry install --local'")
                
        except Exception as e:
            logger.debug(f"Failed to activate local resolver: {e}")