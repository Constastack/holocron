import traceback

import discord


class SafeView(discord.ui.View):
    """Base for every View in the bot.

    Without this, an unhandled exception inside a button/select callback leaves the
    interaction with no response at all — Discord just shows "thinking..." forever
    instead of an error, and nothing about it shows up anywhere for us to diagnose.
    """

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        print(f"⚠️ Chyba v UI komponentě ({item}): {error!r}")
        traceback.print_exc()
        message = "⚠️ Něco se pokazilo. Zkus to prosím znovu, nebo se ozvi organizátorovi."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException:
            pass
