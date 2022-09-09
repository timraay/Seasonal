import discord
from discord.ext import commands

import sqlite3

db = sqlite3.connect('seasonal.db')
cur = db.cursor()
cur.execute('''CREATE TABLE IF NOT EXISTS "config" (
	"guild_id"	INTEGER,
	"mod_role"	INTEGER,
	"admin_role"	INTEGER,
    "overview_channel_id"	INTEGER,
	"overview_message_id"	INTEGER,
	PRIMARY KEY("guild_id")
)''')
db.commit()

def set_config_value(guild_id, field, value):
    cur.execute(f'UPDATE config SET {field} = ? WHERE guild_id = ?', (value, guild_id,))
    db.commit()

def get_config_value(guild_id, field):
    cur.execute(f'SELECT {field} FROM config WHERE guild_id = ?', (guild_id,))
    return cur.fetchone()[0]

async def has_perms(ctx, mod_role=False, admin_role=False):
    if ctx.channel.permissions_for(ctx.author).administrator or await ctx.bot.is_owner(ctx.author):
        return True
    
    cur.execute('SELECT mod_role, admin_role FROM config WHERE guild_id = ?', (ctx.guild.id,))
    mod, admin = cur.fetchone()
    ids = [role.id for role in ctx.author.roles]
    if admin_role:
        return admin in ids
    elif mod_role:
        return mod in ids or admin in ids
    else:
        return False

def check_perms(mod_role=False, admin_role=False):
    async def predicate(ctx):
        return await has_perms(ctx, mod_role, admin_role)
    return commands.check(predicate)


class config(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        cur.execute('SELECT guild_id FROM config')
        ids = [guild_id[0] for guild_id in cur.fetchall()]
        for guild in self.bot.guilds:
            if guild.id not in ids:
                cur.execute('INSERT INTO config VALUES (?,0,0,0,0)', (guild.id,))
        db.commit()

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        cur.execute('SELECT guild_id FROM config WHERE guild_id = ?', (guild.id,))
        if not cur.fetchone():
            cur.execute('INSERT INTO config VALUES (?,0,0,0,0)', (guild.id,))
            db.commit()

    @commands.command(aliases=['modrole'])
    @check_perms(admin_role=True)
    async def mod_role(self, ctx, role: discord.Role = None):
        if not role:
            cur.execute('SELECT mod_role FROM config WHERE guild_id = ?', (ctx.guild.id,))
            role_id = cur.fetchone()[0]
            try: role = (await commands.RoleConverter().convert(ctx, str(role_id))).mention
            except: role = str(role_id)
            await ctx.send(embed=discord.Embed(description='Current Mod Role is '+role))
        else:
            set_config_value(ctx.guild.id, 'mod_role', role.id)
            await ctx.send(embed=discord.Embed(description='Set Mod Role to '+role.mention))
    
    @commands.command(aliases=['adminrole'])
    @check_perms(admin_role=True)
    async def admin_role(self, ctx, role: discord.Role = None):
        if not role:
            cur.execute('SELECT admin_role FROM config WHERE guild_id = ?', (ctx.guild.id,))
            role_id = cur.fetchone()[0]
            try: role = (await commands.RoleConverter().convert(ctx, str(role_id))).mention
            except: role = str(role_id)
            await ctx.send(embed=discord.Embed(description='Current Admin Role is '+role))
        else:
            set_config_value(ctx.guild.id, 'admin_role', role.id)
            await ctx.send(embed=discord.Embed(description='Set Admin Role to '+role.mention))
    
    # @commands.command()
    # @check_perms(admin_role=True)
    # async def calendar(self, ctx, channel: discord.TextChannel = None):
    #     cur.execute('SELECT overview_channel_id, overview_message_id FROM config WHERE guild_id = ?', (ctx.guild.id,))
    #     overview_channel_id, overview_message_id = cur.fetchone()
    #     if not channel:
    #         try: channel = (await commands.TextChannelConverter().convert(ctx, str(overview_channel_id))).mention
    #         except: channel = str(overview_channel_id)
    #         await ctx.send(embed=discord.Embed(description='Current Calendar Channel is '+channel))
    #     else:
    #         try: msg = await ctx.guild.get_channel(overview_channel_id).fetch_message(overview_message_id)
    #         except: pass
    #         else: await msg.delete()
    #         set_config_value(ctx.guild.id, 'overview_channel_id', channel.id)
    #         await ctx.send(embed=discord.Embed(description='Set Calendar Channel to '+channel.mention))


async def setup(bot):
    await bot.add_cog(config(bot))