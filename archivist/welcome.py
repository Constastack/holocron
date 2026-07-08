import discord

import db
import pairings
import players


class WelcomeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="👤 Profil / Registrace", style=discord.ButtonStyle.primary, custom_id="archivist:welcome_profile"
    )
    async def profile_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = db.get_player(interaction.user.id)
        if player is None or not player.get("karabast_nick"):
            await interaction.response.send_modal(players.RegisterModal())
        else:
            await players.profile(interaction, None)

    @discord.ui.button(
        label="✍️ Přihlásit se do sezóny", style=discord.ButtonStyle.success, custom_id="archivist:welcome_signup"
    )
    async def signup_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = db.get_player(interaction.user.id)
        if player is None or not player.get("karabast_nick"):
            async def after_submit(referral_interaction: discord.Interaction):
                await referral_interaction.response.edit_message(
                    content="✅ Registrace dokončena! Zkus teď znovu kliknout na „Přihlásit se do sezóny“.",
                    view=None,
                )

            await interaction.response.send_modal(players.RegisterModal(after_submit=after_submit))
        else:
            await pairings.sign_up_cmd(interaction)


async def setup_welcome_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="👋 Vítej v projektu Holocron!",
        description=(
            "**👤 Profil / Registrace** — vyplň své údaje (Karabast nick, jméno, země).\n"
            "**✍️ Přihlásit se do sezóny** — přihlásíš se do aktuální sezóny, nebo tě bot automaticky "
            "zařadí do příští, pokud je registrace zrovna zavřená.\n\n"
            "Nic z toho nemusíš psát příkazem — stačí kliknout na tlačítko níže."
        ),
    )
    embed.set_footer(text="🐉 Pořádá Dragon Squadron")
    await interaction.response.defer(ephemeral=True)
    try:
        await interaction.channel.send(embed=embed, view=WelcomeView())
    except discord.Forbidden:
        await interaction.followup.send(
            "❌ Nemám oprávnění psát do tohoto kanálu. Povol mi tam „Send Messages“ a „Embed Links“ a zkus to znovu.",
            ephemeral=True,
        )
        return
    await interaction.followup.send("✅ Uvítací panel založen v tomto kanálu.", ephemeral=True)
