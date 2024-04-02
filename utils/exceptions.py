from discord.ext import commands


class NotVoted(commands.CheckFailure):
    """
    Raised when a user has not voted for the bot.
    """


class Maintenance(commands.CheckFailure):
    """
    Raised when bot is under maintenance.
    """
