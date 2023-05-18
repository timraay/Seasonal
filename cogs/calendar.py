import discord
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
    map_name = map_name.lower().replace(" night", "")
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
        embed.set_author(name=channel.name, icon_url=guild.icon.url)
        for match_id, match in sorted(self.matches.items(), key=lambda m: m[1].match_start if m[1].match_start else datetime(3000, 1, 1, tzinfo=timezone.utc)):
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

    async def cog_check(self, ctx):
        return await has_perms(ctx, mod_role=True)

    @commands.group(invoke_without_command=True, aliases=['cal'])
    async def calendar(self, ctx: commands.Context):
        cmds = [
            (f"{ctx.prefix}calendar list", "List all displayed categories"),
            (f"{ctx.prefix}calendar set <channel>", "Change the channel to send the calendar to"),
            (f"{ctx.prefix}calendar add <category>", "Add a channel category to the calendar"),
            (f"{ctx.prefix}calendar remove <category>", "Remove a category from the calendar")
        ]
        embed = discord.Embed().add_field(name="Available Commands", value="\n".join([f"> `{syntax}` - {desc}" for (syntax, desc) in cmds]))
        await ctx.send(embed=embed)


    @calendar.command(name="list")
    async def list_calendar(self, ctx: commands.Context):
        embed = discord.Embed()
        cats = get_categories(ctx.guild)
        
        if cats:
            embed.title = f"There are {str(len(cats))} listed categories."
            embed.description = ""

            for cat in cats.values():
                cat_channel = ctx.guild.get_channel(cat.category_id)
                if not cat_channel:
                    continue
                embed.add_field(
                    name=cat_channel.name,
                    value="\n".join([channel.mention for channel in cat.channels.values()])
                )
        else:
            embed.title = "There are no listed categories."
            embed.description = f"You can add one with the following command:\n`{ctx.prefix}calendar add <category>`"

        await ctx.send(embed=embed)

    @calendar.command(name="channel", aliases=["set"])
    async def set_calendar(self, ctx: commands.Context, channel: discord.TextChannel = None):
        cur.execute('SELECT overview_channel_id FROM config WHERE guild_id = ?', (ctx.guild.id,))
        (overview_channel_id,) = cur.fetchone()
        if not channel:
            try: channel = (await commands.TextChannelConverter().convert(ctx, str(overview_channel_id))).mention
            except: channel = str(overview_channel_id)
            await ctx.send(embed=discord.Embed(description='Current Calendar Channel is '+channel))
        else:
            try:
                cats = get_categories(ctx.guild)
                for cat in cats.values():
                    try:
                        message = await cat.fetch_message(ctx.guild)
                        await message.delete()
                        await channel.send(embed=cat.to_embed(ctx.guild))
                    except:
                        pass
            finally:
                set_config_value(ctx.guild.id, 'overview_channel_id', channel.id)
                await ctx.send(embed=discord.Embed(description='Set Calendar Channel to '+channel.mention))
    
    @calendar.command(name="add")
    async def add_to_calendar(self, ctx: commands.Context, *, category: discord.CategoryChannel):
        cur.execute('SELECT * FROM calendar WHERE category_id = ?', (category.id,))
        if cur.fetchone():
            raise commands.BadArgument('Category is already added')

        cur.execute('SELECT overview_channel_id FROM config WHERE guild_id = ?', (ctx.guild.id,))
        (overview_channel_id,) = cur.fetchone()
        calendar_channel = ctx.guild.get_channel(overview_channel_id)

        cat = get_category(category)
        msg = await calendar_channel.send(embed=cat.to_embed(ctx.guild))

        cur.execute('INSERT INTO calendar VALUES (?,?,?,?)', (calendar_channel.id, msg.id, category.id, ctx.guild.id))
        db.commit()

        embed = discord.Embed(color=discord.Color(7844437))
        embed.set_author(name="Category added", icon_url="https://cdn.discordapp.com/emojis/809149148356018256.png")
        embed.description = f"**{category.name}** is now part of {calendar_channel.mention}."
        await ctx.send(embed=embed)

    @calendar.command(name="remove")
    async def remove_from_calendar(self, ctx: commands.Context, *, category: discord.CategoryChannel):
        cur.execute('SELECT * FROM calendar WHERE category_id = ?', (category.id,))
        if not cur.fetchone():
            raise commands.BadArgument('Category already isn\'t part of the calendar')

        cat = get_categories(ctx.guild)[category.id]
        try:
            msg = await cat.fetch_message(ctx.guild)
            await msg.delete()
        except:
            pass

        cur.execute('DELETE FROM calendar WHERE category_id = ?', (cat.category_id,))
        db.commit()

        embed = discord.Embed(color=discord.Color(7844437))
        embed.set_author(name="Category added", icon_url="https://cdn.discordapp.com/emojis/809149148356018256.png")
        embed.description = f"**{category.name}** was removed from the calendar."
        await ctx.send(embed=embed)

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

    
    @commands.Cog.listener()
    async def on_ready(self):
        #self.channel_name_updater.add_exception_type(Exception)
        #await asyncio.sleep(3*60) # Don't hit rate limits during testing
        self.calendar_updater.start()
            

async def setup(bot):
    await bot.add_cog(Calendar(bot))