"""Poetry Local Resolver Plugin

A Poetry plugin that automatically resolves packages locally first,
then falls back to remote repositories if not found.
"""

__version__ = "0.1.0"

from poetry_local_resolver.plugin import LocalResolverPlugin

__all__ = ["LocalResolverPlugin"]