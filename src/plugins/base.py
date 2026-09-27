"""
Plugin base class and lifecycle contract.

A plugin is a self-contained feature (bank, groupwork, radio, society)
that owns its schema, services, and cogs, and registers itself against
the shared bot runtime.

Lifecycle (driven by the bot's composition root):
1. __init__(bot)   - build repositories and services
2. register        - schema + migrations are handed to DatabaseManager
3. initialize_schema
4. wire(registry)  - grab references to other plugins' services
5. build_cogs(bot) - return Cog instances to mount
6. on_setup(bot)   - async post-cog-mount hook (e.g. preload caches)
"""

from typing import List


class Plugin:
    """Base contract every feature module implements."""

    name: str = "unnamed"
    schema: List[str] = []
    migrations: List[tuple] = []

    def build_cogs(self, bot) -> List[object]:
        """Return a list of discord.py Cog instances to mount."""
        return []

    def wire(self, registry) -> None:
        """Called after all plugins are constructed. Resolve cross-plugin services."""
        pass

    async def on_setup(self, bot) -> None:
        """Async hook run after this plugin's cogs are mounted."""
        pass