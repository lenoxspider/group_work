"""Shared check: gate a command behind an office of state.

The admin fallback is deliberate. Requiring the office outright would lock
everyone out - including the founder - until someone is appointed, and an empty
Magistrate seat would freeze the court. With the fallback, appointing a non-admin
genuinely hands them the power, while admins are never stranded. Once offices
are filled and trusted, the fallback can be tightened.
"""

from discord import app_commands

from src.plugins.offices.domain import OFFICE_LABELS


def _offices(interaction):
    return getattr(interaction.client, "plugins", {}).get("offices")


async def holds_office_or_admin(interaction, office: str) -> bool:
    """True if the invoker holds the office, or has manage_guild as a fallback."""
    plugin = _offices(interaction)
    if plugin is None:
        return True  # offices plugin absent -> no gate
    if interaction.guild_id is None:
        return False
    if await plugin.service.holds(str(interaction.guild_id), str(interaction.user.id), office):
        return True
    perms = getattr(interaction, "permissions", None)
    return bool(perms is not None and getattr(perms, "manage_guild", False))


def requires_office(office: str):
    """Command check: the office holder, or an admin until the seat is filled."""
    label = OFFICE_LABELS.get(office, office)

    async def predicate(interaction) -> bool:
        if await holds_office_or_admin(interaction, office):
            return True
        raise app_commands.CheckFailure(f"That requires the office of {label}.")

    return app_commands.check(predicate)
