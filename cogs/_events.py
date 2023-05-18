import discord
from discord import Interaction, app_commands
from discord.ext import commands, tasks
import random
from datetime import datetime, timedelta
import traceback

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

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.update_status.start()

        @bot.tree.error
        async def on_interaction_error(interaction: Interaction, error):
            exc = error.original if isinstance(error, app_commands.CommandInvokeError) else error

            if isinstance(error, app_commands.CommandInvokeError):
                error = error.original

            embed = discord.Embed(color=discord.Color.from_rgb(221, 46, 68))
            icon_url = 'https://cdn.discordapp.com/emojis/808045512393621585.png'

            if isinstance(error, app_commands.CommandNotFound):
                embed.set_author(icon_url=icon_url, name='Unknown command!')
            elif type(error).__name__ == CustomException.__name__:
                embed.set_author(icon_url=icon_url, name=error.error)
                embed.description = str(error)
            elif isinstance(error, app_commands.CommandOnCooldown):
                embed.set_author(icon_url=icon_url, name="That command is still on cooldown!")
                embed.description = "Cooldown expires in " + convert_time(int(error.retry_after)) + "."
            elif isinstance(error, app_commands.MissingPermissions):
                embed.set_author(icon_url=icon_url, name="Missing required permissions to use that command!")
                embed.description = str(error)
            elif isinstance(error, app_commands.BotMissingPermissions):
                embed.set_author(icon_url=icon_url, name="I am missing required permissions to use that command!")
                embed.description = str(error)
            elif isinstance(error, app_commands.CheckFailure):
                embed.set_author(icon_url=icon_url, name="Couldn't run that command!")
                embed.description = None
            # elif isinstance(error, app_commands.MissingRequiredArgument):
            #     embed.set_author(icon_url=icon_url, name="Missing required argument(s)!")
            #     embed.description = str(error)
            # elif isinstance(error, app_commands.MaxConcurrencyReached):
            #     embed.set_author(icon_url=icon_url, name="You can't do that right now!")
            #     embed.description = str(error)
            elif isinstance(error, commands.BadArgument):
                embed.set_author(icon_url=icon_url, name="Invalid argument!")
                embed.description = str(error)
            elif isinstance(error, channels.NotFound):
                embed.set_author(icon_url=icon_url, name="Channel not found!")
                embed.description = str(error)
            else:
                embed.set_author(icon_url=icon_url, name="An unexpected error occured!")
                embed.description = str(error)

            if isinstance(interaction, Interaction):
                if interaction.response.is_done() or interaction.is_expired():
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.send(embed=embed)

            if not isinstance(error, (app_commands.CommandOnCooldown, commands.BadArgument)):
                print("\nError in " + interaction.guild.name + " #" + interaction.channel.name + ":\n" + str(error))
                try:
                    raise error
                except:
                    traceback.print_exc()

    '''
    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        models.Guild.create(guild.id)
    '''

    @tasks.loop(minutes=15.0)
    async def update_status(self):

        statuses = [
            {"type": "listening", "message": "meta discussions"},
            {"type": "watching", "message": "the latest dev brief"},
            {"type": "listening", "message": "The Recapping"},
            {"type": "watching", "message": "the finals for the 7th time"},
            {"type": "watching", "message": "everyone getting blown up by arty"},
            {"type": "playing", "message": "in Seasonal"},
            {"type": "listening", "message": "the community"},
            {"type": "playing", "message": "mind games"},
            {"type": "playing", "message": "with Alty's wheel"},
            {"type": "watching", "message": "rockets fly across the map"},
            {"type": "listening", "message": "the endless complaints"},
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



async def setup(bot):
    await bot.add_cog(_events(bot))