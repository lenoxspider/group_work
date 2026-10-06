"""Shop feature plugin - the collective's spi sink."""

from src.plugins.base import Plugin
from src.plugins.shop.cog import ShopCog
from src.plugins.shop.repository import SQLiteShopRepository
from src.plugins.shop.schema import SHOP_SCHEMA
from src.plugins.shop.service import ShopService


class ShopPlugin(Plugin):
    name = "shop"
    title = "🛍️ The Shop"
    summary = "The only place spi goes to die - colours, marks and titles, burned on purchase."
    guide = [
        ("/shop view", "The catalogue, the prices, and what you can afford"),
        ("/shop buy item:<id>", "Buy a cosmetic. The spi is burned, not taxed."),
        ("/shop inventory", "What you own"),
    ]
    schema = SHOP_SCHEMA
    migrations = []

    def __init__(self, bot):
        self.bot = bot
        self.repo = SQLiteShopRepository(bot.settings.database_path)
        self.service = ShopService(self.repo)

    def wire(self, registry) -> None:
        bank = registry.get("bank")
        if bank:
            self.service.attach_bank(bank.service)

    def build_cogs(self, bot) -> list:
        return [ShopCog(bot, self.service)]
