"""Games feature plugin - arena-driven Squid Game with spi economy.

Self-contained: owns its schema, repository, service, and cogs. Wires the
bank's ledger for the entry-fee pot escrow. The arena is game-agnostic and
currently registers a single game: Red Light Green Light.
"""

from src.interface.channel_manager import ChannelDecl
from src.plugins.base import Plugin
from src.plugins.games.cog import GamesCog, MoveCog
from src.plugins.games.repository import SQLiteGamesRepository
from src.plugins.games.schema import GAMES_MIGRATIONS, GAMES_SCHEMA
from src.plugins.games.service import ArenaService


class GamesPlugin(Plugin):
    name = "games"
    title = "🎮 Games Arena"
    summary = (
        "Squid Game events. The bot hosts free-entry Glass Bridge rounds when an "
        "audience is present; Red Light Green Light is also playable. Survive and split the pot."
    )
    guide = [
        ("/event open [entry_fee] [game]", "Open an event. game = redlight (default) or bridge; entry fee defaults to 100 spi"),
        ("/event join", "Pay the entry fee and claim a player number (001-456)"),
        ("/event start", "Lock registration and begin the round"),
        ("/event status", "Arena pot, survivor count, and current game"),
        ("/event vote <continue|stop>", "Surviving players vote between rounds"),
        ("/event conclude", "Resolve the event and pay out the pot"),
        ("/move", "Advance in Red Light Green Light (safe on green only)"),
    ]
    schema = GAMES_SCHEMA
    migrations = GAMES_MIGRATIONS

    def __init__(self, bot):
        self.bot = bot
        self.repo = SQLiteGamesRepository(bot.settings.database_path)
        self.service = ArenaService(self.repo, bot.speech_synthesizer)

        self.channels = [
            ChannelDecl(
                "game-hub",
                "🎮 Games Arena. Only active Players can execute commands.",
                "arena",
                welcome="○ △ □ GAMES ARENA • INITIALIZED\n\n"
                        "**How to play:**\n"
                        "• Run `/event open` to start a new event.\n"
                        "• `/event join` pays the entry fee and claims your player tag (`001`-`456`).\n"
                        "• `/event start` locks registration and begins Round 1.\n"
                        "• Eliminated players are moved to the <#spectators> lounge.\n"
                        "• Obey all directives from the Masked Guards.",
            ),
            ChannelDecl("spectators", "💀 Observation deck for eliminated contestants.", "spectators"),
        ]

    def wire(self, registry) -> None:
        bank_plugin = registry.get("bank")
        if bank_plugin:
            self.service.attach_bank(bank_plugin.service)

    def build_cogs(self, bot) -> list:
        cogs = []
        if bot.audio_deliverer:
            cogs.append(
                GamesCog(
                    bot,
                    self.service,
                    bot.audio_deliverer,
                    bot.speech_synthesizer,
                    channel_router=bot.channel_router,
                )
            )
            cogs.append(MoveCog(bot, self.service, channel_router=bot.channel_router))
        return cogs

    async def on_setup(self, bot) -> None:
        self.service.reset_all_games()
        if bot.speech_synthesizer:
            try:
                await self.service.preload_audio_cache()
            except Exception:
                pass