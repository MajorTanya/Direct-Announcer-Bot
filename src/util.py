import discord

NO_MENTIONS_AT_ALL = discord.AllowedMentions(
    everyone=False,
    users=False,
    roles=False,
    replied_user=False,
)

MENTION_ROLES = discord.AllowedMentions(
    everyone=False,
    users=False,
    roles=True,
    replied_user=False,
)
