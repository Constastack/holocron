import discord

import db

MATCH_MILESTONES = [100, 500, 1000, 2000]
PLAYER_MILESTONES = [10, 20, 50, 100]
REFERRAL_MILESTONES = [50]


async def _announce(client: discord.Client, text: str):
    channel_id = db.get_setting("community_channel_id")
    if channel_id:
        channel = client.get_channel(int(channel_id))
        if channel is not None:
            try:
                await channel.send(text)
            except discord.Forbidden:
                pass

    import hall_of_fame  # deferred to avoid a circular import (hall_of_fame imports community)

    await hall_of_fame.refresh_live_hof(client)


async def check_match_milestones(client: discord.Client):
    total = db.get_total_confirmed_matches()
    for threshold in MATCH_MILESTONES:
        key = f"matches_{threshold}"
        if total >= threshold and not db.is_milestone_unlocked(key):
            db.unlock_milestone(key)
            await _announce(client, f"🎉 **Komunita dohromady odehrála {threshold} zápasů!** 🎮")


async def check_player_milestones(client: discord.Client, guild: discord.Guild):
    import achievements  # deferred to avoid a circular import (achievements imports community)

    total = db.get_total_registered_players()
    for threshold in PLAYER_MILESTONES:
        key = f"players_{threshold}"
        if total >= threshold and not db.is_milestone_unlocked(key):
            db.unlock_milestone(key)
            await _announce(client, f"🎉 **Komunita má už {threshold} registrovaných hráčů!** 🐉")
            if threshold == 100:
                for row in db.get_first_n_registered_players(100):
                    await achievements.award(guild, row["discord_id"], "founding_member")


async def check_referral_milestones(client: discord.Client):
    total = db.get_total_referrals()
    for threshold in REFERRAL_MILESTONES:
        key = f"referrals_{threshold}"
        if total >= threshold and not db.is_milestone_unlocked(key):
            db.unlock_milestone(key)
            await _announce(client, f"🎉 **Komunita dohromady zprostředkovala {threshold} referralů!** 🤝")


async def set_channel_cmd(interaction: discord.Interaction):
    db.set_setting("community_channel_id", str(interaction.channel.id))
    await interaction.response.send_message(
        "✅ Community milníky se od teď budou oznamovat do tohoto kanálu.", ephemeral=True
    )
