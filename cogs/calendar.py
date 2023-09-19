import discord
from discord import app_commands, Interaction
from discord.ext import commands, tasks
from typing import *
from datetime import datetime, timezone
import traceback

from lib.channels import get_all_channels, MatchChannel
from cogs.config import db, has_perms, set_config_value
from utils import get_config
cur = db.cursor()
cur.execute('''CREATE TABLE IF NOT EXISTS "calendar" (
	"channel_id"	INTEGER,
	"message_id"	INTEGER,
	"category_id"	INTEGER,
	"guild_id"	INTEGER,
	PRIMARY KEY("category_id", "message_id"),
    FOREIGN KEY("guild_id") REFERENCES config("guild_id")
)''')
db.commit()

SOVIET_MAPS = ["kursk", "stalingrad", "kharkov"]
BRITISH_MAPS = ["el alamein", "driel"]
def get_allied_team_name(map_name: str):
    map_name = map_name.lower().replace("night", "").strip()
    if map_name in SOVIET_MAPS:
        return "RUS"
    elif map_name in BRITISH_MAPS:
        return "UK"
    else:
        return "US"


class CalendarCategory:
    def __init__(self, channel_id: int, message_id: int, category_id: int, guild_id: int):
        self.channel_id = channel_id
        self.message_id = message_id
        self.category_id = category_id
        self.guild_id = guild_id
        self.matches: Dict[int, MatchChannel] = dict()
        self.channels: Dict[int, discord.TextChannel] = dict()

    def __iter__(self):
        yield from zip(self.channels, self.matches)

    async def fetch_message(self, guild: discord.Guild = None, channel: discord.TextChannel = None) -> discord.Message:
        if not channel and not guild:
            raise ValueError('Must provide either channel or guild')

        if guild and not channel:
            channel = guild.get_channel(self.channel_id)
            if not channel:
                raise ValueError('Could not find channel with ID %s' % self.channel_id)
        
        return await channel.fetch_message(self.message_id)
    
    def to_embed(self, guild: discord.Guild):
        channel = guild.get_channel(self.category_id)
        if not channel:
            raise ValueError('The category could not be found')

        embed = discord.Embed(color=discord.Color(get_config().getint('visuals', 'CalendarColor')), description="")
        embed.set_author(
            name=channel.name if len(self.matches) <= 15 else f"{channel.name} (First 15 matches)",
            icon_url=guild.icon.url
        )

        for match_id, match in sorted(self.matches.items(), key=lambda m: m[1].match_start if m[1].match_start else datetime(3000, 1, 1, tzinfo=timezone.utc))[:15]:
            lines = list()
            if match.vote_result:
                faction1 = "GER" if match.vote_result.startswith("!") else get_allied_team_name(match.map)
                faction2 = "GER" if not match.vote_result.startswith("!") else get_allied_team_name(match.map)
                lines.append(f"{match.get_team1(channel)} ({faction1}) vs {match.get_team2(channel)} ({faction2})")
            else:
                lines.append(f"{match.get_team1(channel)} vs {match.get_team2(channel)}")
            lines += [
                f"> \📅 " + (f"<t:{int(match.match_start.timestamp())}:f>" if match.match_start else "*No date...*"),
                f"> \🗺️ " + (f"Map: **{match.map}**" if match.map else "*No map...*"),
                f"> \🎯 " + (f"Score: ||**{match.result}**||" if match.result else "*No score...*"),
            ]

            streams = match.get_streams()
            if streams:
                lines += [f"\🎙️ {s.to_text(True)}" for s in streams]
                if match.stream_delay:
                    lines.append(f"\🎙️ (+{match.stream_delay} min. delay)")
            # else:
            #     lines.append("> \🎙️ *No cast...*"),
            
            match_channel = self.channels[match_id]
            lines.append(f" → {match_channel.mention}")
            
            embed.add_field(name=match.title, value="\n".join(lines))
        return embed
    
    def save(self):
        cur.execute('''UPDATE
            message_id = ?,
            channel_id = ?
        WHERE category_id = ?''', (self.message_id, self.channel_id, self.category_id))
        db.commit()

def get_categories(guild: discord.Guild):
    cur.execute('''SELECT channel_id, message_id, category_id FROM calendar
                   WHERE guild_id = ?''', (guild.id,))

    cats = {obj[2]: CalendarCategory(
        channel_id=obj[0],
        message_id=obj[1],
        category_id=obj[2],
        guild_id=guild.id
    ) for obj in cur.fetchall()}

    matches = {m.channel_id: m for m in get_all_channels(guild.id)}
    for channel in guild.text_channels:
        cat = cats.get(channel.category_id)
        match = matches.get(channel.id)
        if cat and match:
            cat.channels[channel.id] = channel
            cat.matches[channel.id] = match
    
    return cats

def get_category(category: discord.CategoryChannel):
    calcat = CalendarCategory(
        channel_id=None,
        message_id=None,
        category_id=category.id,
        guild_id=category.guild.id
    )
    matches = {m.channel_id: m for m in get_all_channels(category.guild.id)}
    for channel in category.text_channels:
        if channel.id in matches:
            calcat.channels[channel.id] = channel
            calcat.matches[channel.id] = matches[channel.id]
    return calcat



class Calendar(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.missed = dict()

        #self.channel_name_updater.add_exception_type(Exception)
        #await asyncio.sleep(3*60) # Don't hit rate limits during testing
        self.calendar_updater.start()

    async def cog_check(self, ctx):
        return await has_perms(ctx, mod_role=True)

    CalendarGroup = app_commands.Group(name="calendar", description="Calendar configuration", default_permissions=discord.Permissions())

    @CalendarGroup.command(name="list", description="Show a list of all categories listed on the calendar")
    async def list_calendar(self, interaction: Interaction):
        embed = discord.Embed()
        cats = get_categories(interaction.guild)
        
        if cats:
            embed.title = f"There are {str(len(cats))} listed categories."
            embed.description = ""

            for cat in cats.values():
                cat_channel = interaction.guild.get_channel(cat.category_id)
                if not cat_channel:
                    continue
                embed.add_field(
                    name=cat_channel.name,
                    value="\n".join([channel.mention for channel in cat.channels.values()])
                )
        else:
            embed.title = "There are no listed categories."
            embed.description = f"You can add one with the following command:\n`/calendar add <category>`"

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @CalendarGroup.command(name="channel", description="View or set the channel the calendar is sent to")
    @app_commands.describe(
        channel="The channel to send the calendar to. Leave empty to see the current channel."
    )
    async def set_calendar(self, interaction: Interaction, channel: discord.TextChannel = None):
        cur.execute('SELECT overview_channel_id FROM config WHERE guild_id = ?', (interaction.guild.id,))
        (overview_channel_id,) = cur.fetchone()

        if not channel:
            channel = interaction.guild.get_channel(overview_channel_id)
            if not channel:
                channel = str(overview_channel_id)
            else:
                channel = channel.mention
            await interaction.response.send_message(embed=discord.Embed(description='Current Calendar Channel is '+channel), ephemeral=True)
        
        else:
            await interaction.response.defer(ephemeral=True, thinking=True)
            try:
                cats = get_categories(interaction.guild)
                for cat in cats.values():
                    try:
                        message = await cat.fetch_message(interaction.guild)
                        await message.delete()
                        await channel.send(embed=cat.to_embed(interaction.guild))
                    except:
                        pass
            finally:
                set_config_value(interaction.guild.id, 'overview_channel_id', channel.id)
                await interaction.followup.send(embed=discord.Embed(description='Set Calendar Channel to '+channel.mention), ephemeral=True)
    
    @CalendarGroup.command(name="add", description="Add a channel category to the calendar")
    @app_commands.describe(
        category_id="The ID of the category to add"
    )
    async def add_to_calendar(self, interaction: Interaction, category_id: str):
        try:
            category_id = int(category_id)
        except ValueError:
            raise commands.BadArgument('Value is not a valid ID')
        category = interaction.guild.get_channel(category_id)
        if not category or not isinstance(category, discord.CategoryChannel):
            raise commands.BadArgument('ID does not belong to a channel category')
        
        cur.execute('SELECT * FROM calendar WHERE category_id = ?', (category.id,))
        if cur.fetchone():
            raise commands.BadArgument('Category is already added')

        cur.execute('SELECT overview_channel_id FROM config WHERE guild_id = ?', (interaction.guild.id,))
        (overview_channel_id,) = cur.fetchone()
        calendar_channel = interaction.guild.get_channel(overview_channel_id)

        cat = get_category(category)
        msg = await calendar_channel.send(embed=cat.to_embed(interaction.guild))

        cur.execute('INSERT INTO calendar VALUES (?,?,?,?)', (calendar_channel.id, msg.id, category.id, interaction.guild.id))
        db.commit()

        embed = discord.Embed(color=discord.Color(7844437))
        embed.set_author(name="Category added", icon_url="https://cdn.discordapp.com/emojis/809149148356018256.png")
        embed.description = f"**{category.name}** is now part of {calendar_channel.mention}."
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @CalendarGroup.command(name="remove", description="Remove a channel category from the calendar")
    @app_commands.describe(
        category_id="The ID of the category to remove"
    )
    async def remove_from_calendar(self, interaction: Interaction, category_id: str):
        try:
            category_id = int(category_id)
        except ValueError:
            raise commands.BadArgument('Value is not a valid ID')
        category = interaction.guild.get_channel(category_id)
        if not category or not isinstance(category, discord.CategoryChannel):
            raise commands.BadArgument('ID does not belong to a channel category')
        
        cur.execute('SELECT * FROM calendar WHERE category_id = ?', (category.id,))
        if not cur.fetchone():
            raise commands.BadArgument('Category already isn\'t part of the calendar')

        cat = get_categories(interaction.guild)[category.id]
        try:
            msg = await cat.fetch_message(interaction.guild)
            await msg.delete()
        except:
            pass

        cur.execute('DELETE FROM calendar WHERE category_id = ?', (cat.category_id,))
        db.commit()

        embed = discord.Embed(color=discord.Color(7844437))
        embed.set_author(name="Category added", icon_url="https://cdn.discordapp.com/emojis/809149148356018256.png")
        embed.description = f"**{category.name}** was removed from the calendar."
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tasks.loop(minutes=10)
    async def calendar_updater(self):
        try:
            for guild in self.bot.guilds:
                cur.execute('SELECT overview_channel_id FROM config WHERE guild_id = ?', (guild.id,))
                (calendar_channel_id,) = cur.fetchone()
                calendar_channel = guild.get_channel(calendar_channel_id)
                if not calendar_channel:
                    continue
                
                for cat in get_categories(guild).values():
                    try:
                        msg = await cat.fetch_message(guild)
                        if msg.channel != calendar_channel:
                            await msg.delete()
                            raise Exception('Boom!') # Trigger "except" clause and resend message
                        await msg.edit(embed=cat.to_embed(guild))
                        self.missed[cat.category_id] = 0
                    except:
                        missed = self.missed.get(cat.category_id, 0)
                        missed += 1
                        if missed > 10:
                            self.missed[cat.category_id] = 0
                            msg = await calendar_channel.send(embed=cat.to_embed(guild))
                            cat.message_id = msg.id
                            cat.channel_id = msg.channel.id
                            cat.save()
                        else:
                            self.missed[cat.category_id] = missed
        except Exception as e:
            print(f'Explosions! Calendar failed to update...')
            traceback.print_exc()
    @calendar_updater.before_loop
    async def calendar_updater_before_loop(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        if not isinstance(channel, discord.CategoryChannel):
            return
        
        cur.execute('SELECT * FROM calendar WHERE category_id = ?', (channel.id,))
        if not cur.fetchone():
            return

        cat = get_categories(channel.guild)[channel.id]
        try:
            msg = await cat.fetch_message(channel.guild)
            await msg.delete()
        except:
            pass

        cur.execute('DELETE FROM calendar WHERE category_id = ?', (cat.category_id,))
        db.commit()
            

async def setup(bot):
    await bot.add_cog(Calendar(bot))