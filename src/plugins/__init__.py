"""
Plugin registry. This is the single edit point for adding a new
feature module. Each plugin self-registers its schema and cogs on boot.

Add a feature by:
1. Creating a package under src/plugins/<name>/
2. Adding one import + one entry to get_plugins()
"""

from src.plugins.base import Plugin


def get_plugins(bot) -> list[Plugin]:
    """Instantiate and return every plugin in load order."""
    from src.plugins.bank.plugin import BankPlugin

    return [
        BankPlugin(bot),
    ]