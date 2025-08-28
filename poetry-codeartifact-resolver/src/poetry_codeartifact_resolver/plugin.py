"""Poetry plugin that dynamically resolves CodeArtifact URLs based on AWS_REGION."""

import os
import logging
from typing import TYPE_CHECKING

from poetry.plugins.plugin import Plugin
from poetry.repositories.legacy_repository import LegacyRepository
from poetry.repositories.repository_pool import Priority

if TYPE_CHECKING:
    from cleo.io.io import IO
    from poetry.poetry import Poetry

logger = logging.getLogger(__name__)


class CodeArtifactResolverPlugin(Plugin):
    """
    Resolves codeartifact:// URLs to region-specific CodeArtifact URLs.
    Works with either CODEARTIFACT_AUTH_TOKEN (CI/Docker) or Poetry's stored credentials (local).
    """
    
    def activate(self, poetry: "Poetry", io: "IO") -> None:
        """Transform codeartifact:// URLs in repository sources."""
        
        # Get configuration from environment
        aws_region = os.environ.get("AWS_REGION", "us-east-1")
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