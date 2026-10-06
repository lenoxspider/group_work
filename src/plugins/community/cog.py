"""Community Cog - onboarding, the constitution, and the tribunal."""

import logging
from typing import Literal, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from src.domain.errors import AppError
from src.interface.channel_router import ChannelRouter
from src.plugins.community.checks import requires_citizen
from src.plugins.community.domain import (
    CASE_ACQUITTED,
    CASE_CONVICTED,
    CASE_LAPSED,
    CASE_OPEN,
    CATIZEN,
    CITIZEN,
    CITIZEN_STIPEND_SPI,
    Case,
)
from src.plugins.community.intro import (
    IntroSession,
    SignConstitutionView,
    StartIntroView,
    intro_embed,
    intro_view,
)
from src.plugins.community.service import CommunityService

logger = logging.getLogger("plugins.community.cog")

PINK = discord.Color.from_rgb(255, 0, 144)
GUILTY_EMOJI = "✅"
INNOCENT_EMOJI = "❌"

_STATUS_LABEL = {
    CASE_OPEN: "⚖️ OPEN",
    CASE_CONVICTED: "🔨 CONVICTED",
    CASE_ACQUITTED: "🕊️ ACQUITTED",
    CASE_LAPSED: "⌛ LAPSED (no quorum)",
}


def _case_embed(case: Case, law_title: str, law_fine: int) -> discord.Embed:
    round_note = " · APPEAL ROUND" if case.round >= 2 else ""
    embed = discord.Embed(title=f"⚖️ CASE {case.case_id}{round_note}", color=PINK)
    embed.add_field(name="Accused", value=f"<@{case.accused_id}>", inline=True)
    embed.add_field(name="Accuser", value=f"<@{case.accuser_id}>", inline=True)
    embed.add_field(
        name="Law",
        value=f"`{case.law_id}` {law_title}" + (f" · fine {law_fine} spi" if law_fine else ""),
        inline=False,
    )
    embed.add_field(name="Evidence", value=(case.evidence[:1000] or "*none presented*"), inline=False)
    if case.defense:
        embed.add_field(name="Defense", value=case.defense[:1000], inline=False)
    embed.add_field(name="Verdict", value=_STATUS_LABEL.get(case.status, case.status), inline=True)
    embed.add_field(
        name="Jury",
        value=f"🔨 {len(case.guilty())} guilty · 🕊️ {len(case.innocent())} innocent",
        inline=True,
    )
    embed.set_footer(text=f"Vote ✅ guilty / ❌ innocent, or /court vote {case.case_id} <guilty|innocent>")
    return embed


class CommunityCog(commands.Cog, name="Community"):
    def __init__(
        self,
        bot: commands.Bot,
        service: CommunityService,
        channel_router: Optional[ChannelRouter] = None,
    ):
        self.bot = bot
        self.service = service
        self.channel_router = channel_router
        self._intro = {}
        self.court_loop.start()
        self.nudge_loop.start()

    citizens = app_commands.Group(name="citizens", description="Membership administration")
    court = app_commands.Group(name="court", description="The tribunal - citizens judge the law")

    def cog_unload(self):
        self.court_loop.cancel()
        self.nudge_loop.cancel()

    async def cog_load(self):
        self.bot.add_view(StartIntroView(self))
        self.bot.add_view(SignConstitutionView(self))

    # --- Channel helpers ---

    async def _channel(self, guild: discord.Guild, name: str):
        if self.channel_router:
            return await self.channel_router.resolve(guild, name)
        return discord.utils.get(guild.text_channels, name=name)

    async def _new_recruits_channel(self, guild):
        return await self._channel(guild, "new-recruits")

    async def _town_hall_channel(self, guild):
        return await self._channel(guild, "town-hall")

    async def _tribunal_channel(self, guild):
        return await self._channel(guild, "tribunal")

    async def _law(self, law_id: str):
        if not self.service.society:
            return None
        try:
            return await self.service.society.get_law(law_id)
        except Exception:
            return None

    def _role(self, guild: discord.Guild, name: str):
        return discord.utils.get(guild.roles, name=name)

    # --- Onboarding ---

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        guild_id = str(member.guild.id)
        user_id = str(member.id)
        await self.service.on_join(guild_id, user_id)

        try:
            catizen_role = self._role(member.guild, "Catizen")
            if catizen_role and catizen_role not in member.roles:
                await member.add_roles(catizen_role, reason="New recruit - access to #new-recruits")
        except Exception as e:
            logger.warning("Could not grant Catizen role to %s: %s", user_id, e)

        ch = await self._new_recruits_channel(member.guild)
        embed = discord.Embed(
            title="🐱 A catizen has wandered in",
            description=(
                f"**{member.display_name}**, you've joined the collective as a **catizen**.\n\n"
                "**Two steps to become a citizen:**\n"
                "1. Press **Begin your introduction** below - four quick questions, and that's "
                "Task #1 (pays **50 spi**)\n"
                "2. Run `/join` to sign the constitution and unlock voting"
            ),
            color=PINK,
        )
        if ch:
            try:
                await ch.send(content=member.mention, embed=embed, view=StartIntroView(self))
            except Exception as e:
                logger.warning("Could not welcome %s: %s", user_id, e)

        try:
            await member.send(
                "Welcome to the collective, catizen 🐱\n\n"
                "**Two steps to become a citizen:**\n"
                "1. In #new-recruits, press **Begin your introduction** - four quick questions, "
                "and Task #1 is done (pays 50 spi).\n"
                "2. Run `/join` to sign the constitution and unlock voting.\n\n"
                "`/guide` lists every command. `/me` shows your standing."
            )
        except Exception:
            pass

    # --- Prompted introduction ---

    async def begin_intro(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Introduce yourself inside the server.", ephemeral=True)
            return
        guild_id = str(interaction.guild_id)
        user_id = str(interaction.user.id)
        member = await self.service.get_member(guild_id, user_id)
        done_msg = "You've already introduced yourself. Welcome, comrade."
        if member.intro_done or not member.intro_task_id:
            if interaction.response.is_done():
                await interaction.followup.send(done_msg, ephemeral=True)
            else:
                await interaction.response.send_message(done_msg, ephemeral=True)
            return

        session = IntroSession(user_id, interaction.user.display_name)
        self._intro[user_id] = session
        embed = intro_embed(session)
        view = intro_view(self, session)
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def intro_advance(self, interaction: discord.Interaction, session: IntroSession, from_modal: bool = False):
        if session.done:
            await self.intro_finish(interaction, session, from_modal)
            return
        embed = intro_embed(session)
        view = intro_view(self, session)
        if from_modal:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.response.edit_message(embed=embed, view=view)

    async def intro_finish(self, interaction: discord.Interaction, session: IntroSession, from_modal: bool):
        guild = interaction.guild
        user_id = session.user_id
        try:
            completed = await self.service.complete_intro(str(guild.id), user_id)
        except Exception as e:
            logger.warning("Intro completion failed for %s: %s", user_id, e)
            completed = None
        self._intro.pop(user_id, None)

        answers = session.answers + [""] * (4 - len(session.answers))
        nr = await self._new_recruits_channel(guild)
        if nr:
            embed = discord.Embed(title="🎖️ A comrade presents themselves", color=PINK)
            embed.description = f"<@{user_id}> has introduced themselves to the collective."
            embed.add_field(name="Known as", value=answers[0] or "—", inline=True)
            embed.add_field(name="Brings", value=answers[1] or "—", inline=True)
            embed.add_field(name="Came to", value=answers[2] or "—", inline=True)
            embed.add_field(name="Bears the mark", value=answers[3] or "—", inline=True)
            embed.set_footer(text="Task #1 complete · +50 spi" if completed else "Introduction recorded.")
            try:
                await nr.send(content=f"<@{user_id}>", embed=embed, view=SignConstitutionView(self))
            except Exception as e:
                logger.warning("Could not post compiled intro: %s", e)

        hall = await self._town_hall_channel(guild)
        if hall:
            try:
                await hall.send(embed=discord.Embed(
                    description=f"🎖️ Everyone welcome <@{user_id}> - a new comrade has presented themselves.",
                    color=PINK,
                ))
            except Exception:
                pass

        final = (
            "✅ **Introduction complete.** Task #1 cleared"
            + (" (+50 spi)" if completed else "")
            + ". One step left - sign below to become a **citizen**."
        )
        sign_view = SignConstitutionView(self)
        if from_modal:
            await interaction.response.send_message(final, ephemeral=True, view=sign_view)
        else:
            try:
                await interaction.response.edit_message(content=final, embed=None, view=sign_view)
            except Exception:
                await interaction.response.edit_message(content=final, view=sign_view)

    @app_commands.command(name="intro", description="Introduce yourself to the collective (catizens)")
    async def intro_cmd(self, interaction: discord.Interaction):
        await self.begin_intro(interaction)

    # --- Tribunal reaction voting ---

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if self.bot.user and payload.user_id == self.bot.user.id:
            return
        emoji = str(payload.emoji)
        if emoji not in (GUILTY_EMOJI, INNOCENT_EMOJI):
            return
        try:
            case = await self.service.get_case_by_message(str(payload.message_id))
        except Exception:
            return
        if not case or case.status != CASE_OPEN:
            return
        decision = "guilty" if emoji == GUILTY_EMOJI else "innocent"
        try:
            updated = await self.service.court_vote(case.guild_id, case.case_id, str(payload.user_id), decision)
            await self._refresh_case_card(updated)
        except Exception:
            # invalid voter (catizen / conflicted) - strip their reaction
            try:
                channel = self.bot.get_channel(payload.channel_id)
                if channel:
                    msg = await channel.fetch_message(payload.message_id)
                    await msg.remove_reaction(payload.emoji, discord.Object(id=payload.user_id))
            except Exception:
                pass

    async def _refresh_case_card(self, case: Case):
        if case.message_id and case.channel_id:
            try:
                channel = self.bot.get_channel(int(case.channel_id))
                if channel:
                    msg = await channel.fetch_message(int(case.message_id))
                    law = await self._law(case.law_id)
                    await msg.edit(embed=_case_embed(case, law.title if law else case.law_id, law.fine_amount if law else 0))
            except Exception as e:
                logger.warning("Could not refresh case card %s: %s", case.case_id, e)

    @tasks.loop(minutes=5)
    async def court_loop(self):
        for guild in self.bot.guilds:
            try:
                result = await self.service.sweep_court(str(guild.id))
            except Exception as e:
                logger.warning("Court sweep failed for %s: %s", guild.id, e)
                continue
            tribunal = await self._tribunal_channel(guild)
            for closed in result["closed"]:
                case = closed["case"]
                await self._refresh_case_card(case)
                if tribunal:
                    try:
                        await tribunal.send(embed=_verdict_embed(closed))
                    except Exception:
                        pass
            for sentence in result["sentenced"]:
                await self._post_sentence(guild, sentence)

    @court_loop.before_loop
    async def before_court_loop(self):
        await self.bot.wait_until_ready()

    # --- Stranded catizens: did the work, never signed ---

    @tasks.loop(hours=6)
    async def nudge_loop(self):
        """DM anyone who finished their introduction but never signed.

        The sign prompt used to live only on an old #new-recruits message, so
        members who did the work stayed catizens forever without seeing it.
        """
        for guild in self.bot.guilds:
            try:
                pending = await self.service.list_pending_signers(str(guild.id))
            except Exception as e:
                logger.warning("Could not list pending signers in %s: %s", guild.id, e)
                continue
            for member in pending:
                await self._dm_sign_nudge(guild, member)

    @nudge_loop.before_loop
    async def before_nudge_loop(self):
        await self.bot.wait_until_ready()

    async def _dm_sign_nudge(self, guild: discord.Guild, member) -> None:
        try:
            user = self.bot.get_user(int(member.user_id))
            if not user:
                user = await self.bot.fetch_user(int(member.user_id))
        except Exception:
            return
        embed = discord.Embed(
            title="○ △ □ ONE STEP LEFT",
            description=(
                f"You introduced yourself to **{guild.name}** and cleared Task #1 - but you never "
                "signed the constitution, so you are still a **catizen**.\n\n"
                "Citizens vote in `/society`, sit on juries in `/court`, and can spend spi in "
                f"`/shop`. Signing pays **{CITIZEN_STIPEND_SPI} spi** on the spot.\n\n"
                "One click below and it is done."
            ),
            color=PINK,
        )
        try:
            await user.send(embed=embed, view=SignConstitutionView(self))
        except Exception as e:
            # DMs closed - leave them unmarked so we retry on a later pass.
            logger.info("Sign nudge DM refused for %s: %s", member.user_id, e)
            return
        try:
            await self.service.mark_sign_nudged(str(guild.id), member.user_id)
            logger.info("Sent sign nudge DM to %s", member.user_id)
        except Exception as e:
            logger.warning("Could not record sign nudge for %s: %s", member.user_id, e)

    # --- Membership commands ---

    @app_commands.command(name="join", description="Sign the constitution and become a citizen")
    async def join(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self._perform_sign(interaction)

    async def sign_from_button(self, interaction: discord.Interaction) -> None:
        """Handler for the persistent 'Sign the constitution' button."""
        await interaction.response.defer()
        await self._perform_sign(interaction)

    async def _perform_sign(self, interaction: discord.Interaction) -> None:
        # Signing can also happen from a DM nudge, where guild_id is absent.
        guild_id = self._resolve_guild_id(interaction)
        if not guild_id:
            await interaction.followup.send(
                "I could not work out which server to sign you into. Run `/join` there instead.",
                ephemeral=True,
            )
            return
        user_id = str(interaction.user.id)
        guild = self.bot.get_guild(int(guild_id))
        name = getattr(interaction.user, "display_name", None) or interaction.user.name

        laws = await self.service.list_laws(guild_id)
        before = await self.service.get_member(guild_id, user_id)
        already = before.status == CITIZEN
        member = await self.service.sign(guild_id, user_id)

        if guild:
            try:
                catizen_role = self._role(guild, "Catizen")
                gm = guild.get_member(int(user_id))
                if catizen_role and gm and catizen_role in gm.roles:
                    await gm.remove_roles(catizen_role, reason="Signed the constitution")
            except Exception as e:
                logger.warning("Could not remove Catizen role: %s", e)

        if already:
            embed = discord.Embed(
                title="Already a citizen",
                description="You've already signed the constitution.",
                color=PINK,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if member.status == CITIZEN:
            law_lines = (
                "\n".join(f"• {law.title}" for law in laws[:10])
                if laws
                else "• (no laws on the books yet)"
            )
            embed = discord.Embed(
                title="○ △ □ CONSTITUTION ACCEPTED",
                description=(
                    f"**{name}**, you are now a **citizen**. 🗳️\n\n"
                    f"You start with **{CITIZEN_STIPEND_SPI} spi** so you can play, not just be fined. "
                    "Voting in `/society` and the `/court` are unlocked. You accept the current constitution:\n"
                    + law_lines
                ),
                color=PINK,
            )
            embed.set_footer(text="Welcome, comrade. Earn rank via /report.")
        else:
            embed = discord.Embed(
                title="Signing failed",
                description="The collective could not record your signature. Try `/join`.",
                color=PINK,
            )
        await interaction.followup.send(embed=embed)

        # Citizenship is a public moment - let the hall see it happen.
        if member.status == CITIZEN and guild:
            hall = await self._town_hall_channel(guild)
            if hall:
                try:
                    await hall.send(embed=discord.Embed(
                        description=(
                            f"🗳️ **<@{user_id}> has signed the constitution.** "
                            "A new citizen of the collective."
                        ),
                        color=PINK,
                    ))
                except Exception:
                    pass

    def _resolve_guild_id(self, interaction: discord.Interaction) -> Optional[str]:
        """Guild id for an interaction, falling back for DM-originated buttons."""
        if interaction.guild_id:
            return str(interaction.guild_id)
        configured = getattr(self.bot.settings, "guild_id", None)
        if configured:
            return str(configured)
        if self.bot.guilds:
            return str(self.bot.guilds[0].id)
        return None

    @app_commands.command(name="me", description="Your membership status, intro task, and wallet")
    async def me(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild_id = str(interaction.guild_id)
        user_id = str(interaction.user.id)

        member = await self.service.get_member(guild_id, user_id)
        balance = 0
        if self.service.bank:
            try:
                balance = await self.service.bank.balance(guild_id, user_id)
            except Exception:
                pass

        status_display = "🐱 Catizen" if member.status == CATIZEN else "🗳️ Citizen"
        if member.intro_done:
            intro = "✅ done"
        elif member.intro_task_id:
            intro = "⏳ pending (/intro)"
        else:
            intro = "—"

        embed = discord.Embed(title=f"Identity of {interaction.user.display_name}", color=PINK)
        embed.add_field(name="Membership", value=f"**{status_display}**", inline=True)
        embed.add_field(name="Intro task", value=intro, inline=True)
        embed.add_field(name="Wallet", value=f"`{balance:,} spi`", inline=True)
        view = None
        if member.status == CATIZEN:
            embed.set_footer(text="Sign below (or run /join) to become a citizen.")
            view = SignConstitutionView(self)
        await interaction.followup.send(embed=embed, view=view)

    @citizens.command(name="setup", description="[Admin] Enroll existing members into the community system")
    @app_commands.describe(mode="grandfather = full citizens now; recruit = they must sign + post an intro")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def citizens_setup(self, interaction: discord.Interaction, mode: Literal["grandfather", "recruit"]):
        await interaction.response.defer()
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("This must be run inside the server.", ephemeral=True)
            return

        member_ids = []
        try:
            async for member in guild.fetch_members(limit=None):
                if not member.bot:
                    member_ids.append(str(member.id))
        except Exception as e:
            await interaction.followup.send(f"Could not fetch members: {e}", ephemeral=True)
            return

        enrolled = await self.service.enroll_existing(
            str(guild.id), member_ids, as_citizen=(mode == "grandfather")
        )
        label = "citizens (grandfathered)" if mode == "grandfather" else "catizens (must sign + intro)"
        await interaction.followup.send(
            f"✅ Enrolled **{enrolled}** existing members as {label}. "
            f"(Members already registered were left untouched.)"
        )

    @citizens.command(name="announce", description="[Admin] Post the founding proclamation to #town-hall")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def citizens_announce(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("This must be run inside the server.", ephemeral=True)
            return

        hall = await self._town_hall_channel(guild)
        if not hall:
            await interaction.followup.send("Could not find #town-hall.", ephemeral=True)
            return

        recruits = await self._new_recruits_channel(guild)
        recruits_ref = recruits.mention if recruits else "#new-recruits"

        laws = await self.service.list_laws(str(guild.id))
        law_line = (
            f"**{len(laws)} law(s)** are already on the books - read them with `/law list`."
            if laws
            else "No laws yet - the first ones will be written soon."
        )

        embed = discord.Embed(
            title="○ △ □ A CONSTITUTION IS BORN",
            description=(
                "**Comrades - the collective has a new order.**\n\n"
                "This server now runs on a **constitution**. Membership is no longer "
                "automatic; it is *earned*.\n\n"
                "🐱 **Catizen** - a newcomer who has not signed. They can read, but cannot spend "
                "spi, take tasks, join the games, or vote.\n"
                "🗳️ **Citizen** - one who has signed the constitution. Full rights, including a "
                "vote in `/society` and the judgement seat in `/court`.\n\n"
                "**Already here? You are already a citizen** - veterans keep their standing, "
                "nothing changes for you.\n\n"
                "**New arrivals must:**\n"
                f"1. Post an intro in {recruits_ref} - Task #1, pays **50 spi**\n"
                "2. Run `/join` to sign the constitution\n\n"
                f"{law_line}\n"
                "`/me` shows your standing anytime."
            ),
            color=PINK,
        )
        embed.set_footer(text="Tovarishch • the collective endures")
        await hall.send(
            content="@everyone",
            embed=embed,
            allowed_mentions=discord.AllowedMentions(everyone=True),
        )
        await interaction.followup.send(f"📢 Proclamation posted to {hall.mention}.", ephemeral=True)

    # --- Tribunal commands ---

    @court.command(name="accuse", description="Bring a charge against a comrade under a specific law")
    @app_commands.describe(member="The accused", law_id="Law being broken (e.g. LAW-6BC282)", evidence="Your evidence against them")
    @requires_citizen()
    async def court_accuse(self, interaction: discord.Interaction, member: discord.Member, law_id: str, evidence: str):
        await interaction.response.defer()
        guild_id = str(interaction.guild_id)
        try:
            case = await self.service.file_case(
                guild_id, str(interaction.user.id), str(member.id), law_id.strip().upper(), evidence
            )
        except AppError as e:
            await interaction.followup.send(f"❌ {e.message}", ephemeral=True)
            return

        tribunal = await self._tribunal_channel(interaction.guild)
        if tribunal:
            law = await self._law(case.law_id)
            embed = _case_embed(case, law.title if law else case.law_id, law.fine_amount if law else 0)
            try:
                msg = await tribunal.send(embed=embed)
                case.message_id = str(msg.id)
                case.channel_id = str(tribunal.id)
                await self.service.repo.save_case(case)
                await msg.add_reaction(GUILTY_EMOJI)
                await msg.add_reaction(INNOCENT_EMOJI)
            except Exception as e:
                logger.warning("Could not post case card: %s", e)

        await interaction.followup.send(
            f"⚖️ **Case {case.case_id} opened** against {member.mention} under `{case.law_id}`. The jury will judge."
        )

    @court.command(name="vote", description="Cast your verdict on an open case")
    @app_commands.describe(case_id="Case ID (e.g. CASE-A1B2C3)", decision="Your verdict")
    @requires_citizen()
    async def court_vote(self, interaction: discord.Interaction, case_id: str, decision: Literal["guilty", "innocent"]):
        await interaction.response.defer(ephemeral=True)
        try:
            case = await self.service.court_vote(
                str(interaction.guild_id), case_id.strip().upper(), str(interaction.user.id), decision
            )
            await self._refresh_case_card(case)
            await interaction.followup.send(
                f"⚖️ Vote recorded: **{decision}** on `{case.case_id}`.", ephemeral=True
            )
        except AppError as e:
            await interaction.followup.send(f"❌ {e.message}", ephemeral=True)

    @court.command(name="defend", description="Enter or update your defense (accused only)")
    @app_commands.describe(case_id="Case ID", statement="Your defense")
    async def court_defend(self, interaction: discord.Interaction, case_id: str, statement: str):
        await interaction.response.defer(ephemeral=True)
        try:
            case = await self.service.court_defend(
                str(interaction.guild_id), case_id.strip().upper(), str(interaction.user.id), statement
            )
            await self._refresh_case_card(case)
            await interaction.followup.send("📜 Defense entered.", ephemeral=True)
        except AppError as e:
            await interaction.followup.send(f"❌ {e.message}", ephemeral=True)

    @court.command(name="evidence", description="Add evidence (accuser only)")
    @app_commands.describe(case_id="Case ID", statement="Your evidence")
    async def court_evidence(self, interaction: discord.Interaction, case_id: str, statement: str):
        await interaction.response.defer(ephemeral=True)
        try:
            case = await self.service.court_evidence(
                str(interaction.guild_id), case_id.strip().upper(), str(interaction.user.id), statement
            )
            await self._refresh_case_card(case)
            await interaction.followup.send("📜 Evidence added.", ephemeral=True)
        except AppError as e:
            await interaction.followup.send(f"❌ {e.message}", ephemeral=True)

    @court.command(name="close", description="[Magistrate] Conclude a case and pass verdict")
    @app_commands.describe(case_id="Case ID")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def court_close(self, interaction: discord.Interaction, case_id: str):
        await interaction.response.defer()
        case_id = case_id.strip().upper()
        case = await self.service.get_case(case_id)
        if not case:
            await interaction.followup.send(f"❌ No case `{case_id}`.", ephemeral=True)
            return
        if str(interaction.user.id) == case.accused_id:
            await interaction.followup.send("❌ A magistrate cannot judge their own case.", ephemeral=True)
            return
        try:
            result = await self.service.close_case(str(interaction.guild_id), case_id)
        except AppError as e:
            await interaction.followup.send(f"❌ {e.message}", ephemeral=True)
            return
        await self._refresh_case_card(result["case"])
        embed = _verdict_embed(result)
        if result["sentence"]:
            embed.description = (embed.description or "") + "\n\nThe sentence carries out once the appeal window closes."
        await interaction.followup.send(embed=embed)
        if result["sentence"] and result["sentence"]["case"].round >= 2:
            await self._post_sentence(interaction.guild, result["sentence"])

    @court.command(name="appeal", description="Appeal a conviction to a fresh vote (once)")
    @app_commands.describe(case_id="Case ID")
    async def court_appeal(self, interaction: discord.Interaction, case_id: str):
        await interaction.response.defer()
        try:
            case = await self.service.appeal_case(
                str(interaction.guild_id), case_id.strip().upper(), str(interaction.user.id)
            )
        except AppError as e:
            await interaction.followup.send(f"❌ {e.message}", ephemeral=True)
            return
        await self._refresh_case_card(case)
        tribunal = await self._tribunal_channel(interaction.guild)
        if tribunal:
            try:
                law = await self._law(case.law_id)
                msg = await tribunal.send(embed=_case_embed(case, law.title if law else case.law_id, law.fine_amount if law else 0))
                case.message_id = str(msg.id)
                case.channel_id = str(tribunal.id)
                await self.service.repo.save_case(case)
                await msg.add_reaction(GUILTY_EMOJI)
                await msg.add_reaction(INNOCENT_EMOJI)
            except Exception:
                pass
        await interaction.followup.send(f"⚖️ **Appeal granted** on `{case.case_id}`. Fresh jury, fresh vote.")

    @court.command(name="case", description="View a case")
    @app_commands.describe(case_id="Case ID")
    async def court_case(self, interaction: discord.Interaction, case_id: str):
        await interaction.response.defer()
        case = await self.service.get_case(case_id.strip().upper())
        if not case:
            await interaction.followup.send(f"❌ No case `{case_id}`.", ephemeral=True)
            return
        law = await self._law(case.law_id)
        await interaction.followup.send(embed=_case_embed(case, law.title if law else case.law_id, law.fine_amount if law else 0))

    @court.command(name="docket", description="List open cases")
    async def court_docket(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cases = await self.service.list_open_cases(str(interaction.guild_id))
        if not cases:
            await interaction.followup.send("⚖️ The docket is empty.")
            return
        embed = discord.Embed(title="⚖️ Open Docket", color=PINK)
        for case in cases:
            embed.add_field(
                name=f"`{case.case_id}` - {case.law_id}",
                value=f"<@{case.accused_id}> accused by <@{case.accuser_id}> · "
                      f"{len(case.guilty())} guilty / {len(case.innocent())} innocent",
                inline=False,
            )
        await interaction.followup.send(embed=embed)

    # --- Sentence execution ---

    async def _post_sentence(self, guild, sentence: dict):
        case = sentence["case"]
        tribunal = await self._tribunal_channel(guild)
        if not tribunal:
            return
        lines = [f"🔨 **{case.case_id}** - sentence passed on <@{case.accused_id}> under `{case.law_id}` ({sentence['law_title']})."]
        if sentence["multiplier"] > 1:
            lines.append(f"Repeat offender: fine ×{sentence['multiplier']}.")
        if sentence["burned"] > 0:
            lines.append(f"💰 **{sentence['burned']:,} spi** burned from the convicted.")
        if sentence["shamed"]:
            lines.append("🪙 They could not pay - the sentence converts to public shame.")
            shame = await self._channel(guild, "wall-of-shame")
            if shame:
                try:
                    await shame.send(
                        f"🚨 **{case.case_id}**: <@{case.accused_id}> was convicted under `{case.law_id}` "
                        f"but holds no spi to burn. Shame is the sentence."
                    )
                except Exception:
                    pass
        try:
            await tribunal.send("\n".join(lines))
        except Exception:
            pass


def _verdict_embed(result: dict) -> discord.Embed:
    case = result["case"]
    verdict = result["verdict"]
    if verdict == CASE_CONVICTED:
        title, color = "🔨 CONVICTED", discord.Color.red()
        note = "Sentence suspended pending appeal (12h) - the convicted may /court appeal once."
        if case.round >= 2:
            note = "Appeal denied - the conviction stands."
    elif verdict == CASE_ACQUITTED:
        title, color = "🕊️ ACQUITTED", discord.Color.green()
        note = "The accuser is fined 25 spi for a false charge." if result.get("false_witness") else "Acquitted."
    else:
        title, color = "⌛ LAPSED", discord.Color.dark_grey()
        note = "No quorum - fewer than 3 jurors voted. The accused walks."
    embed = discord.Embed(
        title=f"⚖️ {title} - {case.case_id}",
        description=f"{note}\n🔨 {len(case.guilty())} guilty · 🕊️ {len(case.innocent())} innocent",
        color=color,
    )
    return embed
