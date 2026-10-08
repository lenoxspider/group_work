"""Games slash command cogs: /event group and /move."""

import logging
from typing import Optional, Literal

import discord
from discord import app_commands
from discord.ext import commands, tasks

from src.domain.errors import AppError
from src.domain.interfaces.audio_deliverer import AudioDeliverer
from src.domain.interfaces.speech_synthesizer import SpeechSynthesizer
from src.interface.channel_router import ChannelRouter
from src.plugins.games.domain import (
    HOSTED_ENTRY_FEE,
    HOST_COOLDOWN_MINUTES,
    REGISTERING,
    REGISTRATION_TTL_MINUTES,
    utcnow,
)
from src.plugins.games.formatters import (
    build_elimination_embed,
    build_enrollment_embed,
    build_ephemeral_move_feedback,
    build_status_embed,
)
from src.plugins.games.move_view import MoveView
from src.plugins.games.runner import RedLightRunner
from src.plugins.games.service import ArenaService
from src.plugins.community.checks import requires_citizen

logger = logging.getLogger("plugins.games.cog")


class GamesCog(commands.GroupCog, group_name="event"):
    """Arena lifecycle commands: open, join, start, status, vote, conclude."""

    def __init__(
        self,
        bot: commands.Bot,
        arena: ArenaService,
        audio_deliverer: AudioDeliverer,
        synthesizer: Optional[SpeechSynthesizer] = None,
        channel_router: Optional[ChannelRouter] = None,
    ):
        self.bot = bot
        self.arena = arena
        self.audio_deliverer = audio_deliverer
        self.synthesizer = synthesizer
        self.channel_router = channel_router
        self.runner = RedLightRunner(bot, arena, audio_deliverer, synthesizer, channel_router=channel_router)
        self._running_tasks: dict = {}
        super().__init__()

    async def cog_load(self):
        self.bot.add_view(MoveView(self.arena, self.channel_router))
        self.arena.reset_all_games()
        self.host_loop.start()
        self.registration_sweep.start()

    def cog_unload(self):
        self.host_loop.cancel()
        self.registration_sweep.cancel()
        for task in self._running_tasks.values():
            task.cancel()

    async def _ensure_game_hub(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild or not self.channel_router:
            return True
        hub = await self.channel_router.resolve(interaction.guild, "game-hub")
        if hub and interaction.channel_id != hub.id:
            await interaction.followup.send(
                f"Wrong Arena: Games commands can only be used in {hub.mention}!", ephemeral=True
            )
            return False
        return True

    async def _swap_to_spectator(self, guild: discord.Guild, user_id: str) -> None:
        try:
            member = guild.get_member(int(user_id))
            if not member:
                return
            p_role = discord.utils.get(guild.roles, name="Player")
            s_role = discord.utils.get(guild.roles, name="Spectator")
            if p_role and p_role in member.roles:
                await member.remove_roles(p_role, reason="Eliminated in the games")
            if s_role and s_role not in member.roles:
                await member.add_roles(s_role, reason="Moved to Spectator deck")
        except Exception as e:
            logger.warning("Could not swap role to Spectator for %s: %s", user_id, e)

    # --- Bot-hosted rounds ---

    async def _game_hub(self, guild: discord.Guild):
        if self.channel_router:
            return await self.channel_router.resolve(guild, "game-hub")
        return discord.utils.get(guild.text_channels, name="game-hub")

    @tasks.loop(minutes=10)
    async def host_loop(self):
        """Open a free-entry round when there is an audience to play it.

        The arena had never been used: `/event open` is opt-in and nobody
        remembers to run it. Entry is free because a fee would exclude exactly
        the members this is meant to pull in - several citizens hold zero spi.
        """
        for guild in self.bot.guilds:
            gid = str(guild.id)
            try:
                if await self.arena.get_active_event(gid):
                    continue
                if not self.bot.presence.audience_present(gid):
                    continue
                since = await self.arena.seconds_since_last_event(gid)
                if since is not None and since < HOST_COOLDOWN_MINUTES * 60:
                    continue
                event = await self.arena.open_event(gid, HOSTED_ENTRY_FEE)
            except Exception as e:
                logger.warning("Could not host an arena round in %s: %s", gid, e)
                continue
            await self._announce_hosted_round(guild, event)

    @host_loop.before_loop
    async def before_host_loop(self):
        await self.bot.wait_until_ready()

    async def _announce_hosted_round(self, guild: discord.Guild, event) -> None:
        hub = await self._game_hub(guild)
        if not hub:
            return
        embed = discord.Embed(
            title="○ △ □ THE GAMES ARE OPEN",
            description=(
                f"The Front Man has opened round `{event.event_id}`. **Entry is free.**\n\n"
                "Run `/event join` to claim a player number, then `/event start` once "
                "enough of you have stepped forward.\n\n"
                "Red Light Green Light. Move on green, freeze on red.\n"
                f"Registration closes in {REGISTRATION_TTL_MINUTES} minutes if nobody joins."
            ),
            color=discord.Color.from_rgb(255, 0, 144),
        )
        try:
            # @here, not @everyone: the round only opens when an audience is
            # already present, so ping the people who are actually awake.
            await hub.send(
                content="@here",
                embed=embed,
                allowed_mentions=discord.AllowedMentions(everyone=True),
            )
        except Exception as e:
            logger.warning("Could not announce hosted round in %s: %s", guild.id, e)

    @tasks.loop(minutes=5)
    async def registration_sweep(self):
        """Cancel registrations nobody joined, so one empty round cannot wedge the arena.

        An event left in REGISTERING stays in ACTIVE_STATUSES forever and
        open_event() refuses to create another, so without this the first
        hosted round that nobody joined would close the arena for good.
        """
        for guild in self.bot.guilds:
            gid = str(guild.id)
            try:
                event = await self.arena.get_active_event(gid)
                if not event or event.status != REGISTERING or not event.opened_at:
                    continue
                age = (utcnow() - event.opened_at).total_seconds() / 60.0
                if age < REGISTRATION_TTL_MINUTES:
                    continue
                if await self.arena.registration_player_count(gid, event.event_id):
                    continue
                if not await self.arena.cancel_event(gid):
                    continue
            except Exception as e:
                logger.warning("Registration sweep failed in %s: %s", gid, e)
                continue
            logger.info("Cancelled empty registration %s in %s", event.event_id, gid)
            hub = await self._game_hub(guild)
            if hub:
                try:
                    await hub.send(
                        f"⌛ Registration for `{event.event_id}` closed - nobody stepped "
                        "forward. The arena is open again."
                    )
                except Exception:
                    pass

    @registration_sweep.before_loop
    async def before_registration_sweep(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="open", description="Open a new games event for registration")
    @app_commands.describe(entry_fee="spi to enter (default 100)")
    async def open(self, interaction: discord.Interaction, entry_fee: Optional[int] = None):
        try:
            await interaction.response.defer()
        except discord.NotFound:
            return

        guild_id = str(interaction.guild_id)
        try:
            event = await self.arena.open_event(guild_id, entry_fee)
            await interaction.followup.send(
                f"**REGISTRATION OPEN.** Entry fee: **{event.entry_fee} spi**. "
                f"Use `/event join` to claim a player number, then `/event start` to begin."
            )
        except AppError as e:
            await interaction.followup.send(f"{e.message}", ephemeral=True)

    @app_commands.command(name="join", description="Pay the entry fee and claim a player number")
    @requires_citizen()
    async def join(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
        except discord.NotFound:
            return

        if not await self._ensure_game_hub(interaction):
            return

        guild_id = str(interaction.guild_id)
        try:
            player = await self.arena.join_event(guild_id, str(interaction.user.id))
            if interaction.guild and isinstance(interaction.user, discord.Member):
                p_role = discord.utils.get(interaction.guild.roles, name="Player")
                s_role = discord.utils.get(interaction.guild.roles, name="Spectator")
                if s_role and s_role in interaction.user.roles:
                    await interaction.user.remove_roles(s_role)
                if p_role and p_role not in interaction.user.roles:
                    await interaction.user.add_roles(p_role)
            avatar_url = interaction.user.display_avatar.url if interaction.user else None
            embed = build_enrollment_embed(player, avatar_url=avatar_url)
            await interaction.followup.send(embed=embed)
        except AppError as e:
            await interaction.followup.send(f"{e.message}", ephemeral=True)

    @app_commands.command(name="start", description="Lock registration and begin Round 1 (Red Light Green Light)")
    async def start(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
        except discord.NotFound:
            return

        if not await self._ensure_game_hub(interaction):
            return

        guild_id = str(interaction.guild_id)
        if guild_id in self._running_tasks and not self._running_tasks[guild_id].done():
            await interaction.followup.send("A game is already in progress.", ephemeral=True)
            return

        try:
            event = await self.arena.start_event(guild_id)
        except AppError as e:
            await interaction.followup.send(f"{e.message}", ephemeral=True)
            return

        hub = await self.channel_router.resolve(interaction.guild, "game-hub") if self.channel_router and interaction.guild else interaction.channel
        await interaction.followup.send("**Round 1: Red Light Green Light.** The doll is watching. Use `/move` or the MOVE button.")
        task = self.bot.loop.create_task(
            self.runner.run(hub, guild_id, on_cleanup=lambda gid: self._running_tasks.pop(gid, None))
        )
        self._running_tasks[guild_id] = task

    @app_commands.command(name="status", description="View the arena pot, survivors, and current game")
    async def status(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
        except discord.NotFound:
            return

        guild_id = str(interaction.guild_id)
        try:
            status = await self.arena.get_status(guild_id)
            embed = build_status_embed(status)
            await interaction.followup.send(embed=embed)
        except AppError as e:
            await interaction.followup.send(f"{e.message}", ephemeral=True)

    @app_commands.command(name="vote", description="Vote to continue or stop the games")
    @app_commands.describe(choice="continue to the next round, or stop and split the pot")
    @requires_citizen()
    async def vote(self, interaction: discord.Interaction, choice: Literal["continue", "stop"]):
        try:
            await interaction.response.defer(ephemeral=True)
        except discord.NotFound:
            return

        guild_id = str(interaction.guild_id)
        try:
            await self.arena.vote(guild_id, str(interaction.user.id), choice)
            await interaction.followup.send(f"Vote recorded: **{choice.upper()}**.", ephemeral=True)
        except AppError as e:
            await interaction.followup.send(f"{e.message}", ephemeral=True)

    @app_commands.command(name="conclude", description="Front Man command: resolve the event and pay out the pot")
    async def conclude(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
        except discord.NotFound:
            return

        guild_id = str(interaction.guild_id)
        try:
            result = await self.arena.conclude_event(guild_id)
            if result.winner_id:
                await interaction.followup.send(
                    f"**WINNER:** <@{result.winner_id}> takes the pot of **{result.pot_formatted}**."
                )
            elif result.survivor_count > 0:
                await interaction.followup.send(
                    f"**EVENT CONCLUDED.** {result.survivor_count} survivor(s) split **{result.pot_formatted}**."
                )
            else:
                await interaction.followup.send("**TOTAL EXTINCTION.** The pot carries to the next event.")
        except AppError as e:
            await interaction.followup.send(f"{e.message}", ephemeral=True)


class MoveCog(commands.Cog, name="Movement"):
    """Top-level /move command for Red Light Green Light."""

    def __init__(self, bot: commands.Bot, arena: ArenaService, channel_router: Optional[ChannelRouter] = None):
        self.bot = bot
        self.arena = arena
        self.channel_router = channel_router

    @app_commands.command(name="move", description="Take steps in Red Light Green Light (safe only during Green Light!)")
    @app_commands.checks.cooldown(1, 0.5, key=lambda i: (i.guild_id, i.user.id))
    @requires_citizen()
    async def move(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
        except discord.NotFound:
            return

        if self.channel_router and interaction.guild:
            hub = await self.channel_router.resolve(interaction.guild, "game-hub")
            if hub and interaction.channel_id != hub.id:
                await interaction.followup.send(
                    f"Wrong Arena: You can only `/move` inside {hub.mention}!", ephemeral=True
                )
                return

        guild_id = str(interaction.guild_id)
        user_id = str(interaction.user.id)

        try:
            res = await self.arena.handle_move(guild_id, user_id)
            if not res.survived and interaction.guild and isinstance(interaction.user, discord.Member):
                p_role = discord.utils.get(interaction.guild.roles, name="Player")
                s_role = discord.utils.get(interaction.guild.roles, name="Spectator")
                if p_role and p_role in interaction.user.roles:
                    await interaction.user.remove_roles(p_role, reason="Eliminated in Red Light Green Light")
                if s_role and s_role not in interaction.user.roles:
                    await interaction.user.add_roles(s_role, reason="Moved to Spectators deck")
            feedback = build_ephemeral_move_feedback(res)
            await interaction.followup.send(feedback, ephemeral=True)
        except AppError as e:
            await interaction.followup.send(f"{e.message}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"{str(e)}", ephemeral=True)