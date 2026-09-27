"""Shared checks to gate write commands behind constitution signing."""

from discord import app_commands


def _community(interaction):
    return getattr(interaction.client, "plugins", {}).get("community")


async def _is_citizen(interaction) -> bool:
    community = _community(interaction)
    if community is None:
        return True  # community plugin absent -> no gate
    return await community.service.is_citizen(
        str(interaction.guild_id), str(interaction.user.id)
    )


def requires_citizen():
    """Reject catizens (unsigned members) from gated write commands."""

    async def predicate(interaction):
        if await _is_citizen(interaction):
            return True
        raise app_commands.CheckFailure("Sign the constitution first - run `/join`.")

    return app_commands.check(predicate)