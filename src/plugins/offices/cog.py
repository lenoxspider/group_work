"""Offices Cog - appoint, vacate, and list the offices of state."""

import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from src.plugins.offices.domain import OFFICES, OFFICE_DUTY, OFFICE_LABELS, OFFICE_ROLE
from src.plugins.offices.service import OfficeError, OfficesService

logger = logging.getLogger("plugins.offices.cog")

PINK = discord.Color.from_rgb(255, 0, 144)
_OFFICE_CHOICES = [app_commands.Choice(name=OFFICE_LABELS[o], value=o) for o in OFFICES]


class OfficesCog(commands.Cog, name="Offices"):
    office = app_commands.Group(name="office", description="The offices of state - who holds them")

    def __init__(self, bot: commands.Bot, service: OfficesService):
        self.bot = bot
        self.service = service
        self.reconcile_loop.start()

    def cog_unload(self):
        self.reconcile_loop.cancel()

    @tasks.loop(hours=6)
    async def reconcile_loop(self):
        for guild in self.bot.guilds:
            try:
                await self.reconcile_office_roles(guild)
            except Exception as e:
                logger.warning("Office role reconcile failed in %s: %s", guild.id, e)

    @reconcile_loop.before_loop
    async def before_reconcile_loop(self):
        await self.bot.wait_until_ready()

    async def reconcile_office_roles(self, guild: discord.Guild) -> None:
        """Keep the office roles in step with the registry, both directions.

        Citizenship already had this and offices did not: a role removed by hand,
        or a holder who left and rejoined, would leave the member list publicly
        disagreeing with who actually holds the office. The database is the
        source of truth; the role is only its visible marker.
        """
        gid = str(guild.id)
        roles = {}
        for office in OFFICES:
            role = discord.utils.get(guild.roles, name=OFFICE_ROLE[office])
            if role:
                roles[office] = role
        if not roles:
            return  # roles not created yet - /setup provisions them

        wanted: dict = {}
        for office in roles:
            holder = await self.service.holder(gid, office)
            if holder:
                wanted.setdefault(holder, set()).add(office)

        for member in guild.members:
            if member.bot:
                continue
            holds = wanted.get(str(member.id), set())
            for office, role in roles.items():
                has = role in member.roles
                want = office in holds
                if has == want:
                    continue
                try:
                    if want:
                        await member.add_roles(role, reason=f"Holds the office of {OFFICE_LABELS[office]}")
                    else:
                        await member.remove_roles(role, reason=f"No longer {OFFICE_LABELS[office]}")
                except Exception as e:
                    logger.warning("Could not reconcile %s role for %s: %s", role.name, member.id, e)

    async def _sync_role(self, guild: discord.Guild, office: str, user_id: str, grant: bool) -> None:
        """Mirror an appointment onto the Discord role. Best effort - a missing
        role or a member the bot cannot manage must not fail the appointment."""
        role = discord.utils.get(guild.roles, name=OFFICE_ROLE[office])
        if not role:
            logger.info("Office role %s does not exist yet; run /setup.", OFFICE_ROLE[office])
            return
        member = guild.get_member(int(user_id))
        if not member:
            return
        try:
            if grant and role not in member.roles:
                await member.add_roles(role, reason=f"Appointed {OFFICE_LABELS[office]}")
            elif not grant and role in member.roles:
                await member.remove_roles(role, reason=f"No longer {OFFICE_LABELS[office]}")
        except Exception as e:
            logger.warning("Could not sync %s role for %s: %s", office, user_id, e)

    @office.command(name="appoint", description="[Admin] Appoint a citizen to an office")
    @app_commands.describe(office="which office", member="who holds it")
    @app_commands.choices(office=_OFFICE_CHOICES)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def appoint(self, interaction: discord.Interaction, office: str, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("Offices only exist inside the server.", ephemeral=True)
            return
        guild_id = str(interaction.guild.id)
        try:
            previous = await self.service.appoint(guild_id, office, str(member.id), str(interaction.user.id))
        except OfficeError as e:
            await interaction.followup.send(str(e), ephemeral=True)
            return
        if previous and previous != str(member.id):
            await self._sync_role(interaction.guild, office, previous, grant=False)
        await self._sync_role(interaction.guild, office, str(member.id), grant=True)
        label = OFFICE_LABELS[office]
        note = f" (relieves <@{previous}>)" if previous and previous != str(member.id) else ""
        await interaction.followup.send(
            f"🎖️ **{member.display_name}** is appointed **{label}**{note}. "
            "Recorded in the chronicle.", ephemeral=True,
        )

    @office.command(name="vacate", description="[Admin] Vacate an office")
    @app_commands.describe(office="which office to empty")
    @app_commands.choices(office=_OFFICE_CHOICES)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def vacate(self, interaction: discord.Interaction, office: str):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("Offices only exist inside the server.", ephemeral=True)
            return
        try:
            previous = await self.service.vacate(str(interaction.guild.id), office)
        except OfficeError as e:
            await interaction.followup.send(str(e), ephemeral=True)
            return
        if previous:
            await self._sync_role(interaction.guild, office, previous, grant=False)
        label = OFFICE_LABELS[office]
        msg = f"🎖️ The office of **{label}** is vacated." if previous else f"**{label}** was already empty."
        await interaction.followup.send(msg, ephemeral=True)

    @office.command(name="list", description="Who holds which office, and what each does")
    async def list_offices(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        rows = {r["office"]: r["user_id"] for r in await self.service.all_offices(str(interaction.guild_id))}
        embed = discord.Embed(title="🎖️ THE OFFICES OF STATE", color=PINK)
        for office in OFFICES:
            holder = rows.get(office)
            who = f"<@{holder}>" if holder else "*vacant*"
            embed.add_field(
                name=f"{OFFICE_LABELS[office]} - {who}",
                value=OFFICE_DUTY[office],
                inline=False,
            )
        embed.set_footer(text="Appointed by the founder; elective once there is a quorum.")
        await interaction.followup.send(embed=embed, ephemeral=True)
