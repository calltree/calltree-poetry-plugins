"""Poetry plugin that dynamically resolves CodeArtifact URLs based on AWS_REGION."""

import os
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from poetry.plugins.plugin import Plugin
from poetry.repositories.legacy_repository import LegacyRepository
from poetry.repositories.repository_pool import Priority

if TYPE_CHECKING:
    from cleo.io.io import IO
    from poetry.poetry import Poetry

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)


class CodeArtifactResolverPlugin(Plugin):
    """
    Resolves codeartifact:// URLs to region-specific CodeArtifact URLs.
    Works with either CODEARTIFACT_AUTH_TOKEN (CI/Docker) or Poetry's stored credentials (local).
    """
    
    def _detect_region(self) -> str:
        """Determine AWS region with robust precedence.

        Precedence:
          1) CALLTREE_REGION
          2) AWS_REGION
          3) AWS_DEFAULT_REGION
          4) Calltree CLI config current customer region (~/.config/calltree/config.json)
          5) us-west-2 (safer default for Calltree)
        """
        # Direct overrides first
        for key in ("CALLTREE_REGION", "AWS_REGION", "AWS_DEFAULT_REGION"):
            v = os.environ.get(key)
            if v:
                return v

        # Fall back to Calltree CLI config if available
        try:
            config_path_env = os.environ.get("CALLTREE_CONFIG_PATH", "")
            if config_path_env:
                cfg_path = Path(config_path_env).expanduser()
            else:
                cfg_path = Path.home() / ".config" / "calltree" / "config.json"
            
            logger.debug(f"Checking config path: {cfg_path}")
            logger.debug(f"Config exists: {cfg_path.exists()}")
            
            if cfg_path.exists():
                with cfg_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                
                logger.debug(f"Config data: {data}")
                cur = data.get("current_customer")
                customers = data.get("customers") or {}
                logger.debug(f"Current customer: {cur}")
                logger.debug(f"Customers: {customers}")
                
                if cur and isinstance(customers, dict):
                    cc = customers.get(cur) or {}
                    region = cc.get("region")
                    logger.debug(f"Customer config: {cc}")
                    logger.debug(f"Region found: {region}")
                    
                    if isinstance(region, str) and region:
                        return region
        except Exception as e:
            logger.debug(f"Config reading failed: {e}")
            pass

        raise RuntimeError(
            "CodeArtifact region could not be determined. Set CALLTREE_REGION or AWS_REGION or ensure ~/.config/calltree/config.json contains a current customer with a region."
        )

    def activate(self, poetry: "Poetry", io: "IO") -> None:
        """Transform codeartifact:// URLs in repository sources."""

        # Get configuration from environment / config
        aws_region = self._detect_region()
        account_id = "831926607337"  # Fixed for Calltree
        auth_token = os.environ.get("CODEARTIFACT_AUTH_TOKEN")
        
        # Read pyproject.toml to find codeartifact:// sources
        pyproject_data = poetry.pyproject.file.read()
        sources = pyproject_data.get("tool", {}).get("poetry", {}).get("source", [])
        
        for source in sources:
            if isinstance(source, dict) and "url" in source:
                url = source["url"]
                name = source.get("name", "unknown")
                
                if isinstance(url, str) and url.startswith("codeartifact://"):
                    # Parse the custom URL scheme
                    # Format: codeartifact://domain/repository/path
                    parts = url.replace("codeartifact://", "").split("/", 2)
                    
                    if len(parts) >= 2:
                        domain = parts[0]
                        repository = parts[1]
                        path = parts[2] if len(parts) > 2 else "simple"
                        
                        # Build the actual CodeArtifact URL
                        actual_url = (
                            f"https://{domain}-{account_id}.d.codeartifact."
                            f"{aws_region}.amazonaws.com/pypi/{repository}/{path}/"
                        )
                        
                        # Create repository with resolved URL
                        repo = LegacyRepository(name, actual_url)
                        
                        # Determine priority
                        priority_map = {
                            "primary": Priority.PRIMARY,
                            "supplemental": Priority.SUPPLEMENTAL,
                            "explicit": Priority.EXPLICIT,
                        }
                        priority = priority_map.get(source.get("priority", "primary"), Priority.PRIMARY)
                        
                        # Remove any existing repository with the same name
                        if poetry.pool.has_repository(name):
                            poetry.pool.remove_repository(name)
                        
                        # Add the new repository
                        poetry.pool.add_repository(repo, priority=priority)
                        
                        if io.is_verbose():
                            io.write_line(
                                f"<info>CodeArtifact: Resolved {name} to {aws_region} "
                                f"({actual_url})</info>"
                            )
