"""
Extension request voting interactive buttons interface.

What it does:
- Provides persistent discord.ui.View buttons for extension requests: Approve, Reject, Conclude Vote.
- Enforces voter permissions and majority vote resolution.
- Updates Discord message embeds and announces vote outcomes.

What it does NOT do:
- Does NOT execute direct SQL queries or database updates.
"""

import re
import logging
from typing import Optional
import discord

from src.application.services.extension_service import ExtensionService
from src.application.dtos.extension_dtos import CastVoteDTO, ExtensionResultDTO
from src.interface.discord_formatters import build_extension_vote_embed, format_discord_timestamps
from src.domain.errors import AppError

logger = logging.getLogger("interface.cogs.extension_buttons")

class ExtensionVoteView(discord.ui.View):
    """Persistent action buttons for extension request cards."""

    def __init__(self, extension_service: ExtensionService, is_resolved: bool = False):
        super().__init__(timeout=None)
        self.service = extension_service
        if is_resolved:
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True

    def _extract_request_id(self, message: discord.Message) -> Optional[str]:
        """Extracts EXT-XXXX request ID from embed title or footer."""
        if not message.embeds:
            return None
        embed = message.embeds[0]
        text_to_search = f"{embed.title or ''} {embed.footer.text if embed.footer else ''}"
        match = re.search(r"\b(EXT-[A-Za-z0-9]+)\b", text_to_search)
        return match.group(1) if match else None

    def _get_task_description(self, message: discord.Message) -> str:
        """Extracts task description from embed fields if available."""
        if not message.embeds:
            return "Task deliverable"
        for field in message.embeds[0].fields:
            if "Task" in field.name:
                return field.value
        return "Task deliverable"

    @discord.ui.button(
        label="Approve",
        style=discord.ButtonStyle.success,
        emoji="👍",
        custom_id="ext_vote_btn:approve"
    )
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._process_vote(interaction, approve=True)

    @discord.ui.button(
        label="Reject",
        style=discord.ButtonStyle.danger,
        emoji="👎",
        custom_id="ext_vote_btn:reject"
    )
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._process_vote(interaction, approve=False)

    async def _process_vote(self, interaction: discord.Interaction, approve: bool):
        await interaction.response.defer(ephemeral=True)
        req_id = self._extract_request_id(interaction.message)
        if not req_id:
            await interaction.followup.send("❌ Could not identify extension request ID.", ephemeral=True)
            return

        try:
            dto = CastVoteDTO(
                request_id=req_id,
                user_id=str(interaction.user.id),
                approve=approve
            )
            result = await self.service.cast_vote(dto)
            task_desc = self._get_task_description(interaction.message)
            embed = build_extension_vote_embed(result, task_desc)
            await interaction.message.edit(embed=embed)

            vote_str = "Approved 👍" if approve else "Rejected 👎"
            await interaction.followup.send(
                f"✅ Your vote has been recorded: **{vote_str}** "
                f"(`{result.approvals_count}` vs `{result.rejections_count}`)",
                ephemeral=True
            )
        except AppError as e:
            await interaction.followup.send(f"❌ {e.message}", ephemeral=True)

    @discord.ui.button(
        label="Conclude Vote",
        style=discord.ButtonStyle.secondary,
        emoji="🏁",
        custom_id="ext_vote_btn:conclude"
    )
    async def conclude_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        req_id = self._extract_request_id(interaction.message)
        if not req_id:
            await interaction.followup.send("❌ Could not identify extension request ID.", ephemeral=True)
            return

        try:
            current = await self.service.get_extension(req_id)
            if current.is_resolved:
                await interaction.followup.send("✨ This vote is already concluded.", ephemeral=True)
                return

            # Only requester or server moderator can conclude the vote
            member = interaction.user
            is_mod = False
            if isinstance(member, discord.Member):
                perms = member.guild_permissions
                is_mod = perms.manage_messages or perms.administrator
            if str(member.id) != current.requester_id and not is_mod:
                await interaction.followup.send(
                    "❌ Only the requester or a team admin can conclude the vote.",
                    ephemeral=True
                )
                return

            resolved = await self.service.conclude_vote(req_id, str(member.id))
            task_desc = self._get_task_description(interaction.message)
            embed = build_extension_vote_embed(resolved, task_desc)
            disabled_view = ExtensionVoteView(self.service, is_resolved=True)
            await interaction.message.edit(embed=embed, view=disabled_view)

            abs_ts, rel_ts = format_discord_timestamps(resolved.proposed_due_date)
            if resolved.is_approved:
                outcome_text = (
                    f"🎉 **Extension Request `{resolved.request_id}` APPROVED!**\n"
                    f"Task `{resolved.task_id}` deadline extended to {abs_ts} ({rel_ts}) "
                    f"by majority vote (`{resolved.approvals_count}` to `{resolved.rejections_count}`)."
                )
            else:
                outcome_text = (
                    f"❌ **Extension Request `{resolved.request_id}` REJECTED.**\n"
                    f"The original deadline stands by majority vote "
                    f"(`{resolved.rejections_count}` to `{resolved.approvals_count}`)."
                )

            if interaction.channel:
                await interaction.channel.send(outcome_text)
            await interaction.followup.send("✅ Vote concluded and outcome recorded!", ephemeral=True)
        except AppError as e:
            await interaction.followup.send(f"❌ {e.message}", ephemeral=True)
