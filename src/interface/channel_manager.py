"""
Shared channel declaration and provisioner.

Plugins declare the channels they own via ChannelDecl. The ChannelManager
creates/repairs them, applies permission policies, and persists bindings.
This replaces the old hardcoded channel matrix that lived inside admin_cog.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import discord

from src.interface.channel_router import ChannelRouter

logger = logging.getLogger("interface.channel_manager")


@dataclass(frozen=True)
class ChannelDecl:
    """A plugin's declared channel: name, topic, permission policy, optional welcome text."""

    name: str
    topic: str
    policy: str = "ledger"
    welcome: Optional[str] = None


def _read_only(guild: discord.Guild) -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(
        view_channel=True,
        read_message_history=True,
        send_messages=False,
        send_messages_in_threads=False,
        create_public_threads=False,
        create_private_threads=False,
        add_reactions=False,
        manage_webhooks=False,
        use_application_commands=False,
    )


def _bot_full() -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(
        view_channel=True,
        send_messages=True,
        manage_messages=True,
        embed_links=True,
        attach_files=True,
        read_message_history=True,
        manage_webhooks=True,
    )


def _private() -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(view_channel=False)


def _policy_ledger(guild: discord.Guild) -> Dict:
    return {guild.default_role: _read_only(guild), guild.me: _bot_full()}


def _policy_arena(guild: discord.Guild) -> Dict:
    ow = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=True, read_message_history=True, send_messages=False, use_application_commands=True
        ),
        guild.me: _bot_full(),
    }
    player = discord.utils.get(guild.roles, name="Player")
    if player:
        ow[player] = discord.PermissionOverwrite(
            view_channel=True, read_message_history=True, send_messages=True,
            use_application_commands=True, add_reactions=True
        )
    spectator = discord.utils.get(guild.roles, name="Spectator")
    if spectator:
        ow[spectator] = discord.PermissionOverwrite(
            view_channel=True, read_message_history=True, send_messages=False, use_application_commands=False
        )
    return ow


def _policy_spectators(guild: discord.Guild) -> Dict:
    ow = {guild.default_role: _private(), guild.me: _bot_full()}
    spectator = discord.utils.get(guild.roles, name="Spectator")
    if spectator:
        ow[spectator] = discord.PermissionOverwrite(
            view_channel=True, read_message_history=True, send_messages=True
        )
    return ow


def _policy_bot_log(guild: discord.Guild) -> Dict:
    return {guild.default_role: _private(), guild.me: _bot_full()}


def _policy_pulse(guild: discord.Guild) -> Dict:
    """#pulse: everyone can see, react, and send (reflex pulses need both)."""
    return {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=True,
            read_message_history=True,
            send_messages=True,
            add_reactions=True,
            use_application_commands=True,
        ),
        guild.me: _bot_full(),
    }


def _policy_court(guild: discord.Guild) -> Dict:
    """#tribunal: public read + react (jury votes), no free chat, commands allowed."""
    return {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=True,
            read_message_history=True,
            send_messages=False,
            add_reactions=True,
            use_application_commands=True,
        ),
        guild.me: _bot_full(),
    }


def _policy_recruits(guild: discord.Guild) -> Dict:
    """#new-recruits: private to the Catizen role (un-signed recruits) + bot."""
    ow = {guild.default_role: _private(), guild.me: _bot_full()}
    catizen = discord.utils.get(guild.roles, name="Catizen")
    if catizen:
        ow[catizen] = discord.PermissionOverwrite(
            view_channel=True,
            read_message_history=True,
            send_messages=True,
            use_application_commands=True,
        )
    return ow


POLICIES = {
    "ledger": _policy_ledger,
    "arena": _policy_arena,
    "spectators": _policy_spectators,
    "bot-log": _policy_bot_log,
    "recruits": _policy_recruits,
    "court": _policy_court,
    "pulse": _policy_pulse,
}


class ChannelManager:
    """Creates/repairs every plugin's declared channels and persists bindings."""

    CATEGORY_NAME = "TOVARISHCH"

    def __init__(self, bot: discord.Client, channel_router: ChannelRouter):
        self.bot = bot
        self.channel_router = channel_router

    async def _ensure_category(self, guild: discord.Guild) -> Optional[discord.CategoryChannel]:
        category = discord.utils.get(guild.categories, name=self.CATEGORY_NAME)
        if not category and guild.me.guild_permissions.manage_channels:
            try:
                category = await guild.create_category(name=self.CATEGORY_NAME)
            except Exception as e:
                logger.warning("Could not create %s category in guild %s: %s", self.CATEGORY_NAME, guild.id, e)
        return category

    def _overwrites(self, guild: discord.Guild, policy: str) -> Dict:
        builder = POLICIES.get(policy, _policy_ledger)
        return builder(guild)

    async def provision_all(
        self, guild: discord.Guild, repair: bool = False
    ) -> Tuple[List[discord.TextChannel], Dict[str, str]]:
        """Provision declared channels for all plugins, returning (channels, key->id bindings)."""
        category = await self._ensure_category(guild)
        channels: List[discord.TextChannel] = []
        bindings: Dict[str, str] = {}

        for plugin in self.bot._plugin_defs:
            for decl in plugin.channels:
                ch = await self._provision_one(guild, decl, category, repair)
                if ch:
                    channels.append(ch)
                    bindings[decl.name] = str(ch.id)

        await self.channel_router.bind_all(str(guild.id), bindings)
        return channels, bindings

    async def _provision_one(
        self,
        guild: discord.Guild,
        decl: ChannelDecl,
        category: Optional[discord.CategoryChannel],
        repair: bool,
    ) -> Optional[discord.TextChannel]:
        ch = discord.utils.get(guild.text_channels, name=decl.name)
        is_new = False

        if not ch and guild.me.guild_permissions.manage_channels:
            try:
                ch = await guild.create_text_channel(
                    name=decl.name,
                    topic=decl.topic,
                    category=category,
                    overwrites=self._overwrites(guild, decl.policy),
                )
                is_new = True
            except Exception as e:
                logger.warning("Could not auto-create #%s in guild %s: %s", decl.name, guild.name, e)
        elif ch and repair and guild.me.guild_permissions.manage_channels:
            try:
                await ch.edit(
                    topic=decl.topic,
                    category=category,
                    overwrites=self._overwrites(guild, decl.policy),
                )
            except Exception as e:
                logger.warning("Could not repair #%s: %s", decl.name, e)

        if ch and is_new and decl.welcome:
            try:
                await ch.send(decl.welcome)
            except Exception:
                pass

        return ch