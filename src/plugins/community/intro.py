"""The prompted introduction - a short flow that completes a catizen's Task #1.

Each question offers canned answers plus an "in my own words" modal.
The session state lives on the cog; the views are stateless.
"""

import logging

import discord

logger = logging.getLogger("plugins.community.intro")

PINK = discord.Color.from_rgb(255, 0, 144)
OWN_VALUE = "__own__"
OWN_LABEL = "✏️ In my own words"

QUESTIONS = [
    {"prompt": "What shall the collective call you?", "options": ["Use my Discord name"]},
    {
        "prompt": "What do you bring to the collective?",
        "options": ["🛠️ A craft or skill", "🧠 Ideas and strategy", "💰 Resources", "🎨 Art or design"],
    },
    {"prompt": "Why have you come?", "options": ["To build something", "To learn", "To compete", "To belong"]},
    {"prompt": "Which mark do you bear?", "options": ["○ Circle", "△ Triangle", "□ Square"]},
]


class IntroSession:
    def __init__(self, user_id: str, display_name: str):
        self.user_id = user_id
        self.display_name = display_name
        self.index = 0
        self.answers = []

    @property
    def done(self) -> bool:
        return self.index >= len(QUESTIONS)


def intro_embed(session: IntroSession) -> discord.Embed:
    q = QUESTIONS[session.index]
    embed = discord.Embed(
        title=f"○ △ □ INTRODUCTION · {session.index + 1}/{len(QUESTIONS)}",
        description=f"**{q['prompt']}**",
        color=PINK,
    )
    if session.answers:
        embed.add_field(name="So far", value="\n".join(f"• {a}" for a in session.answers), inline=False)
    embed.set_footer(text="Pick an option, or write your own.")
    return embed


def intro_view(cog, session: IntroSession) -> discord.ui.View:
    q = QUESTIONS[session.index]
    options = [discord.SelectOption(label=o[:100], value=o) for o in q["options"]]
    options.append(discord.SelectOption(label=OWN_LABEL, value=OWN_VALUE))
    view = discord.ui.View(timeout=900)

    select = discord.ui.Select(placeholder=q["prompt"][:150], options=options[:25], min_values=1, max_values=1)

    async def on_pick(interaction: discord.Interaction):
        if str(interaction.user.id) != session.user_id:
            await interaction.response.send_message("This isn't your introduction.", ephemeral=True)
            return
        value = interaction.data["values"][0]
        if value == OWN_VALUE:
            await interaction.response.send_modal(OwnAnswerModal(cog, session))
            return
        session.answers.append(value)
        session.index += 1
        await cog.intro_advance(interaction, session)

    select.callback = on_pick
    view.add_item(select)
    return view


class OwnAnswerModal(discord.ui.Modal):
    answer = discord.ui.TextInput(label="Your answer", max_length=120, required=True)

    def __init__(self, cog, session: IntroSession):
        super().__init__(title=QUESTIONS[session.index]["prompt"][:45])
        self.cog = cog
        self.session = session

    async def on_submit(self, interaction: discord.Interaction):
        self.session.answers.append(str(self.answer.value).strip())
        self.session.index += 1
        await self.cog.intro_advance(interaction, self.session, from_modal=True)


class StartIntroView(discord.ui.View):
    """Persistent button on the welcome card that starts the introduction."""

    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Begin your introduction", style=discord.ButtonStyle.success, custom_id="intro:start")
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.begin_intro(interaction)