"""
Plugin base class and lifecycle contract.

A plugin is a self-contained feature (bank, radio, society, groupwork)
that owns its schema, services, and cogs, and registers itself against
the shared bot runtime.

What a plugin does NOT do:
- import another plugin's internals directly
- touch global shared tables outside its own schema
"""

from typing import List


class Plugin:
    """Base contract every feature module implements."""

    name: str = "unnamed"
    schema: List[str] = []

    def build_cogs(self, bot) -> List[object]:
        """Return a list of discord.py Cog instances to mount."""
        return []