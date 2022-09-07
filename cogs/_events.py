import discord
from discord.ext import commands, tasks
import random
from datetime import datetime, timedelta
from ast import literal_eval
import difflib
import re

from lib import channels 


def convert_time(seconds):
    sec = timedelta(seconds=seconds)
    d = datetime(1,1,1) + sec

    output = ("%dh%dm%ds" % (d.hour, d.minute, d.second))
    if output.startswith("0h"):
        output = output.replace("0h", "")
    if output.startswith("0m"):
        output = output.replace("0m", "")

    return output


class CustomException(Exception):
    """Raised to log a custom exception"""
    def __init__(self, error, *args):
        self.error = error
        super().__init__(*args)

class _events(commands.Cog):
    """A class with most events in it"""

    def __init__(self, bot):
        self.bot = bot
        self.update_status.start()


    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        
        if not isinstance(error, commands.CommandOnCooldown) and not isinstance(error, commands.CommandNotFound):
            ctx.command.reset_cooldown(ctx)
        
        if hasattr(ctx.command, 'on_error'):
            return

        if isinstance(error, commands.CommandInvokeError):
            error = error.original

        embed = discord.Embed(color=discord.Color.from_rgb(221, 46, 68))
        icon_url = 'https://cdn.discordapp.com/emojis/808045512393621585.png'

        if isinstance(error, commands.CommandNotFound):
            used_command = re.search(r'Command "(.*)" is not found', str(error)).group(1)
            all_commands = [command.name for command in self.bot.commands]
            close_matches = difflib.get_close_matches(used_command, all_commands, cutoff=0.3)
            embed.set_author(icon_url=icon_url, name='Unknown command!')
            if close_matches: embed.description = f"Maybe try one of the following: {ctx.prefix}{f', {ctx.prefix}'.join(close_matches)}"

        elif type(error).__name__ == CustomException.__name__:
            embed.set_author(icon_url=icon_url, name=error.error)
            embed.description = str(error)
        elif isinstance(error, commands.CommandOnCooldown):
            embed.set_author(icon_url=icon_url, name="That command is still on cooldown!")
            embed.description = "Cooldown expires in " + convert_time(int(error.retry_after)) + "."
        elif isinstance(error, commands.MissingPermissions):
            embed.set_author(icon_url=icon_url, name="Missing required permissions to use that command!")
            embed.description = str(error)
        elif isinstance(error, commands.BotMissingPermissions):
            embed.set_author(icon_url=icon_url, name="I am missing required permissions to use that command!")
            embed.description = str(error)
        elif isinstance(error, commands.CheckFailure):
            embed.set_author(icon_url=icon_url, name="Couldn't run that command!")
            embed.description = None
        elif isinstance(error, commands.MissingRequiredArgument):
            embed.set_author(icon_url=icon_url, name="Missing required argument(s)!")
            embed.description = str(error)
        elif isinstance(error, commands.MaxConcurrencyReached):
            embed.set_author(icon_url=icon_url, name="You can't do that right now!")
            embed.description = str(error)
        elif isinstance(error, commands.BadArgument):
            embed.set_author(icon_url=icon_url, name="Invalid argument!")
            embed.description = str(error)
        elif isinstance(error, channels.NotFound):
            embed.set_author(icon_url=icon_url, name="Channel not found!")
            embed.description = str(error)
        else:
            embed.set_author(icon_url=icon_url, name="An unexpected error occured!")
            embed.description = str(error)

        await ctx.send(embed=embed)

        if not isinstance(error, commands.CommandOnCooldown):
            try:
                print("\nError in " + ctx.guild.name + " #" + ctx.channel.name + ":\n" + str(error))
            except:
                print("\nFailed to log error")
        raise error

    '''
    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        models.Guild.create(guild.id)
    '''
    @commands.Cog.listener()
    async def on_ready(self):
        print("\nLaunched " + self.bot.user.name + " on " + str(datetime.now()))
        print("ID: " + str(self.bot.user.id))



    @tasks.loop(minutes=15.0)
    async def update_status(self):

        statuses = [
            {"type": "listening", "message": "meta discussions"},
            {"type": "watching", "message": "the latest dev brief"},
            {"type": "listening", "message": "HLT"},
            {"type": "watching", "message": "the finals for the 7th time"},
            {"type": "watching", "message": "everyone getting blown up by arty"},
            {"type": "playing", "message": "in Seasona- No I will never get to play in Seasonal :("},
            {"type": "listening", "message": "the community"},
            {"type": "playing", "message": "mind games"},
            {"type": "listening", "message": "meta discussions"}
        ]
        status = random.choice(statuses)
        message = status["message"]
        activity = status["type"]
        if activity == "playing": activity = discord.ActivityType.playing
        elif activity == "streaming": activity = discord.ActivityType.streaming
        elif activity == "listening": activity = discord.ActivityType.listening
        elif activity == "watching": activity = discord.ActivityType.watching
        else: activity = discord.ActivityType.playing

        await self.bot.change_presence(activity=discord.Activity(name=message, type=activity))
    @update_status.before_loop
    async def before_status(self):
        await self.bot.wait_until_ready()



def setup(bot):
    bot.add_cog(_events(bot))