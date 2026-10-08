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
    from src.plugins.chronicle.plugin import ChroniclePlugin
    from src.plugins.community.plugin import CommunityPlugin
    from src.plugins.games.plugin import GamesPlugin
    from src.plugins.groupwork.plugin import GroupworkPlugin
    from src.plugins.pulse.plugin import PulsePlugin
    from src.plugins.radio.plugin import RadioPlugin
    from src.plugins.shop.plugin import ShopPlugin
    from src.plugins.society.plugin import SocietyPlugin

    return [
        GroupworkPlugin(bot),
        BankPlugin(bot),
        ChroniclePlugin(bot),
        CommunityPlugin(bot),
        GamesPlugin(bot),
        PulsePlugin(bot),
        RadioPlugin(bot),
        ShopPlugin(bot),
        SocietyPlugin(bot),
    ]
