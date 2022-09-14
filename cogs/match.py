import discord
from discord.ext import commands, tasks
import asyncio
import json

import datetime
from dateutil.parser import parse

from lib.channels import MatchChannel, NotFound, get_all_channels
from lib.streams import Stream, FLAGS
from lib.vote import MapVote, MAPS
from cogs._events import CustomException
from cogs.config import get_config_value, has_perms, set_config_value
from utils import verify_reactions, get_config


CHANNEL_EMOJIS = {
    'PLANNED': '📆',
    'BAN': '🔨',
    'LIVE': '👀',
    'RESULT': '✅'
}

class match(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        return await has_perms(ctx, mod_role=True)

    @commands.group(invoke_without_command=True)
    async def match(self, ctx):
        cmds = [
            f"{ctx.prefix}match list",
            f"{ctx.prefix}match view <channel>",
            f"{ctx.prefix}match create <channel> [title] [description]",
            f"{ctx.prefix}match set <channel> (title|desc|date|team1|team2|map|banner|result) <value>",
            f"{ctx.prefix}match vote <channel> (enable|disable|on|off)",
            f"{ctx.prefix}match vote <channel> coinflip (random|team1|team2)",
            f"{ctx.prefix}match vote <channel> server (other|team1|team2|<location>)",
            f"{ctx.prefix}match vote <channel> reset",
            f"{ctx.prefix}match pred <channel> (enable|disable|on|off)",
            f"{ctx.prefix}match pred <channel> (team1|team2) <emoji>",
            f"{ctx.prefix}match pred <channel> reset",
            f"{ctx.prefix}match cast <channel> add <\"name\"> <\"lang\"> <\"url\">",
            f"{ctx.prefix}match cast <channel> remove <num>",
            f"{ctx.prefix}match show <channel>",
            f"{ctx.prefix}match hide <channel>",
            f"{ctx.prefix}match hoist <channel>",
            f"{ctx.prefix}match delete <channel>"
        ]
        embed = discord.Embed().add_field(name="Available Commands", value=">>> `{}`".format('\n'.join(cmds)))
        await ctx.send(embed=embed)

    @match.command()
    async def list(self, ctx):
        embed = discord.Embed()
        matches = get_all_channels(ctx.guild.id)
        
        if matches:
            embed.title = f"There are {str(len(matches))} ongoing matches."
            embed.description = ""
            
            categories = dict()
            unknown = list()
            for match in matches:
                channel = ctx.guild.get_channel(match.channel_id)
                if channel:
                    if channel.category not in categories.keys():
                        categories[channel.category] = dict(creation_time=None, matches=list())
                    
                    categories[channel.category]['matches'].append((match, channel))
                    if not categories[channel.category]['creation_time'] or match.creation_time > categories[channel.category]['creation_time']:
                        categories[channel.category]['creation_time'] = match.creation_time
                else:
                    unknown.append(match)
            
            categories = {k: v for k, v in sorted(categories.items(), key=lambda item: item[1]['creation_time'], reverse=True)}
            if unknown: categories['Unknown'] = [(m, None) for m in unknown]

            for category, data in categories.items():
                match_data = sorted(data['matches'], key=lambda item: item[0].match_start.timestamp() if item[0].match_start else 0)
                title = str(category) if category else "Other"
                description = '\n'.join([
                    f'`{match.channel_id}` | {match.title} - {channel.mention if isinstance(channel, discord.TextChannel) else "No channel ⚠️"}'
                    for match, channel in match_data
                ])
                embed.add_field(name=title, value=description, inline=False)
                
        else:
            embed.title = "There are no ongoing matches."
            embed.description = f"You can create one with the following command:\n`{ctx.prefix}match create <channel> [\"title\"] [\"description\"]`"            

        await ctx.send(embed=embed)

    @match.command(aliases=['new', 'add'])
    async def create(self, ctx, channel: discord.TextChannel, title: str = "Unnamed Match", description: str = "", team1: discord.Role = None,
    team2: discord.Role = None, vote_n_stuff: bool = get_config().getboolean('behavior', 'EnableVotingByDefault')):
        try: MatchChannel(channel.id)
        except NotFound: pass
        else: raise commands.BadArgument('A match is already linked with this channel.')
        MatchChannel.new(channel=channel, title=title, desc=description, team1=team1.id if team1 else None, team2=team2.id if team1 else None, has_vote=vote_n_stuff, has_predictions=vote_n_stuff)
        overwrites = channel.overwrites
        overwrites[ctx.channel.guild.default_role] = discord.PermissionOverwrite(view_channel=False, send_messages=False)
        await channel.edit(overwrites=overwrites)

        embed = discord.Embed(color=discord.Color(7844437))
        embed.set_author(name="Match created", icon_url="https://cdn.discordapp.com/emojis/809149148356018256.png")
        embed.description = f"Further customize it using `{ctx.prefix}match set {channel.id} ...` and then start it using `{ctx.prefix}match show {channel.id}`. View your progress using `{ctx.prefix}match view {channel.id}`."
        await ctx.send(embed=embed)

    @match.command(aliases=['remove'])
    async def delete(self, ctx, channel: discord.TextChannel):
        match = MatchChannel(channel.id)
        match.delete()

        try: msg = await channel.fetch_message(match.message_id)
        except discord.NotFound: pass
        else: await msg.delete()

        try: msg = await channel.fetch_message(match.vote_message_id)
        except discord.NotFound: pass
        else: await msg.delete()

        try: msg = await channel.fetch_message(match.predictions_message_id)
        except discord.NotFound: pass
        else: await msg.delete()

        embed = discord.Embed(color=discord.Color(7844437))
        embed.set_author(name="Match deleted", icon_url="https://cdn.discordapp.com/emojis/809149148356018256.png")
        embed.description = f"Deleted {match.title} from {channel.mention}."
        await ctx.send(embed=embed)
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        if isinstance(channel, discord.TextChannel):
            try: MatchChannel(channel.id).delete()
            except: pass


    @match.command()
    async def view(self, ctx, channel: discord.TextChannel):
        match = MatchChannel(channel.id)
        embeds = await match.to_embed(ctx)
        
        # Default embed
        embed = embeds.pop(0)
        await ctx.send(embed=embed)

        # Map vote
        if match.has_vote:
            embed = embeds.pop(0)
            await ctx.send(embed=embed, file=discord.File('output.png'))
        
        # Match predictions
        if match.has_predictions:
            embed = embeds.pop(0)
            await ctx.send(embed=embed)

    @match.command(aliases=['update'])
    async def set(self, ctx, channel: discord.TextChannel, property: str, *, value: str):
        match = MatchChannel(channel.id)
        property = property.lower()
        output = None

        if property in ["title"]:
            match.title = value

        elif property in ["desc", "description"]:
            match.desc = value

        elif property in ["match_start", "start", "date", "time"]:
            match_start = parse(value, fuzzy=True)
            if not match_start.tzinfo:
                match_start = match_start.replace(tzinfo=datetime.timezone.utc)
            match_start = match_start.astimezone(datetime.timezone.utc)
            match.match_start = match_start
            output = match_start.isoformat(sep=' ')

        elif property in ["team1", "allies", "us"]:
            try:
                role = await commands.RoleConverter().convert(ctx, value)
                match.team1 = role.id
                output = role.mention
            except commands.BadArgument:
                match.team1 = value
                output = value

        elif property in ["team2", "axis", "ger"]:
            try:
                role = await commands.RoleConverter().convert(ctx, value)
                match.team2 = role.id
                output = role.mention
            except commands.BadArgument:
                match.team2 = value
                output = value

        elif property in ["map", "level"]:
            match.map = None if value.lower() == "none" else value

        elif property in ["banner_url", "banner", "image", "image_url", "thumbnail", "poster"]:
            match.banner_url = None if value.lower() == "none" else value

        elif property in ["result", "score", "winner"]:
            match.result = None if value.lower() == "none" else value

        else:
            raise commands.BadArgument("%s isn't a valid option" % property)
        
        match.save()
        if not output: output = None if value.lower() == "none" else value
        embed = discord.Embed(color=discord.Color(7844437))
        embed.set_author(name="Property updated", icon_url="https://cdn.discordapp.com/emojis/809149148356018256.png")
        embed.description = f"{channel.mention}'s `{property}` is now {output}."
        await ctx.send(embed=embed)

        await self._update_match(ctx, channel, send=False)

    @match.command(aliases=['caster', 'casters', 'stream', 'streams', 'streamer', 'streamers'])
    async def cast(self, ctx, channel: discord.TextChannel, action, arg1=None, arg2=None, arg3=None):
        match = MatchChannel(channel.id)
        action = action.lower()

        if action == 'add':
            if arg1 is None:
                raise commands.MissingRequiredArgument('name')
            if arg2 is None:
                raise commands.MissingRequiredArgument('lang')
            if arg3 is None:
                raise commands.MissingRequiredArgument('url')

            try:
                name = (await commands.MemberConverter().convert(ctx, arg1)).name
            except commands.BadArgument:
                name = str(arg1)
            lang = str(arg2).upper()
            url = str(arg3)
            
            displaylang, flag = FLAGS.get(lang, ['??', '❓'])
            embed = discord.Embed(description=f"({displaylang}) {flag} {name} - <{url}>")
            embed.set_author(name='Add this stream?')
            msg = await ctx.send(embed=embed)
            emojis = ['✅', '❎']
            for e in emojis:
                await msg.add_reaction(e)
            try:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=lambda r, u: str(r.emoji) in emojis and u.id == ctx.author.id)
            except asyncio.TimeoutError:
                await msg.clear_reactions()
                embed.set_footer(text='Event timed out, please execute the command again')
                await msg.edit(embed=embed)
            else:
                await msg.clear_reactions()
                emoji = str(reaction.emoji)
                if emoji == emojis[0]:
                    stream = Stream.new(channel.id, lang, name, url)
                    embed = discord.Embed(description=stream.to_text(), color=discord.Color(7844437))
                    embed.set_author(name="Streamer added", icon_url="https://cdn.discordapp.com/emojis/809149148356018256.png")
                    await msg.edit(embed=embed)
                elif emoji == emojis[1]:
                    embed = discord.Embed(color=discord.Color.from_rgb(221, 46, 68))
                    embed.set_author(name="User cancelled the action", icon_url="https://cdn.discordapp.com/emojis/808045512393621585.png")
                    await msg.edit(embed=embed)
        
        elif action == 'remove':
            if arg1 is None:
                raise commands.MissingRequiredArgument('num')

            streams = match.get_streams()
            if not streams:
                raise commands.BadArgument('Match has no streams to remove')

            try:
                index = int(arg1) - 1
            except ValueError:
                raise commands.BadArgument('Invalid number: %s' % arg1)
            if not -1 < index < len(streams):
                raise commands.BadArgument('%s must be between 1 and %s', arg1, len(streams))
            stream = streams[index-1]

            embed = discord.Embed(description=stream.to_text())
            embed.set_author(name='Remove this stream?')
            msg = await ctx.send(embed=embed)
            emojis = ['✅', '❎']
            for e in emojis:
                await msg.add_reaction(e)
            try:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=lambda r, u: str(r.emoji) in emojis and u.id == ctx.author.id)
            except asyncio.TimeoutError:
                await msg.clear_reactions()
                embed.set_footer(text='Event timed out, please execute the command again')
                await msg.edit(embed=embed)
            else:
                await msg.clear_reactions()
                emoji = str(reaction.emoji)
                if emoji == emojis[0]:
                    embed = discord.Embed(description=stream.to_text(), color=discord.Color(7844437))
                    stream.delete()
                    embed.set_author(name="Stream removed", icon_url="https://cdn.discordapp.com/emojis/809149148356018256.png")
                    await msg.edit(embed=embed)
                elif emoji == emojis[1]:
                    embed = discord.Embed(color=discord.Color.from_rgb(221, 46, 68))
                    embed.set_author(name="User cancelled the action", icon_url="https://cdn.discordapp.com/emojis/808045512393621585.png")
                    await msg.edit(embed=embed)

        elif action == 'list':
            streams = match.get_streams()
            embed = discord.Embed(description="\n".join([s.to_text() for s in streams]) if streams else "No streams yet...")
            await ctx.send(embed=embed)
            return
        
        await self._update_match(ctx, channel, send=False)

    async def _update_match(self, ctx, channel: discord.TextChannel, send=True, update_image=False, update_perms=False, delay_predictions=False):
        match = MatchChannel(channel.id)
        embeds = await match.to_embed(ctx)

        try:
            msg = await channel.fetch_message(match.message_id)
        except discord.NotFound:
            if send:
                msg = await channel.send(embed=embeds.pop(0))
                match.message_id = msg.id
                match.save()
        else:
            await msg.edit(embed=embeds.pop(0))
        
        if match.has_vote:
            try:
                msg = await channel.fetch_message(match.vote_message_id)
            except discord.NotFound:
                if send:
                    msg = await channel.send(embed=embeds.pop(0), file=discord.File('output.png'))
                    match.vote_message_id = msg.id
                    match.save()
            else:
                if update_image:
                    await msg.delete()
                    msg = await channel.send(embed=embeds.pop(0), file=discord.File('output.png'))
                    match.vote_message_id = msg.id
                    match.save()
                else:
                    await msg.edit(embed=embeds.pop(0))

        elif match.vote_message_id:
            try: msg = await channel.fetch_message(match.vote_message_id)
            except discord.NotFound: pass
            else: await msg.delete()
            finally:
                match.vote_message_id = 0
                match.save()

        if match.has_predictions and not (match.has_vote and not match.vote_result):
            try:
                msg = await channel.fetch_message(match.predictions_message_id)
            except discord.NotFound:
                if send:
                    embed = embeds.pop(0)
                    if delay_predictions and not (match.match_start and datetime.datetime.now(datetime.timezone.utc) > match.match_start):
                        embed.set_footer(text="Predictions will be available\nin approx. 10 minutes")
                    msg = await channel.send(embed=embed)
                    match.predictions_message_id = msg.id
                    match.save()

                    if not (match.match_start and datetime.datetime.now(datetime.timezone.utc) > match.match_start):
                        if delay_predictions:
                            await asyncio.sleep(10*60)
                            await verify_reactions(msg, emojis=[match.predictions_team1_emoji, match.predictions_team2_emoji], whitelisted_ids=[self.bot.user.id])
                            embed.set_footer()
                            await msg.edit(embed=embed)
                        else:
                            await verify_reactions(msg, emojis=[match.predictions_team1_emoji, match.predictions_team2_emoji], whitelisted_ids=[self.bot.user.id])
            else:
                await msg.edit(embed=embeds.pop(0))
                if not (match.match_start and datetime.datetime.now(datetime.timezone.utc) > match.match_start):
                    await verify_reactions(msg, emojis=[match.predictions_team1_emoji, match.predictions_team2_emoji], whitelisted_ids=[self.bot.user.id])
        elif match.predictions_message_id:
            try: msg = await channel.fetch_message(match.predictions_message_id)
            except discord.NotFound: pass
            else: await msg.delete()
            finally:
                match.predictions_message_id = 0
                match.save()

        if update_perms:
            overwrites = channel.overwrites
            defaults = overwrites[ctx.channel.guild.default_role]
            defaults.update(send_messages=False, add_reactions=False, read_message_history=True)
            overwrites[ctx.channel.guild.default_role] = defaults
            
            if match.has_vote:
                try: rep1 = await commands.RoleConverter().convert(ctx, str(match.team1))
                except: pass
                else: overwrites[rep1] = discord.PermissionOverwrite(send_messages=None if match.vote_result else True, view_channel=None if defaults.view_channel else True)
                try: rep2 = await commands.RoleConverter().convert(ctx, str(match.team2))
                except: pass
                else: overwrites[rep2] = discord.PermissionOverwrite(send_messages=None if match.vote_result else True, view_channel=None if defaults.view_channel else True)
            
            await channel.edit(overwrites=overwrites)
        
        await self._update_channel_name(channel)
        
                
    async def _update_channel_name(self, channel: discord.TextChannel):
        match = MatchChannel(channel.id)
        
        channel_name = channel.name
        for emoji in CHANNEL_EMOJIS.values():
            if channel_name.startswith(emoji):
                channel_name = channel_name.replace(emoji, '')
                break
        
        if match.result: emoji = CHANNEL_EMOJIS["RESULT"]
        elif match.has_vote and not match.vote_result: emoji = CHANNEL_EMOJIS["BAN"]
        elif match.match_start and datetime.datetime.now(datetime.timezone.utc) > match.match_start: emoji = CHANNEL_EMOJIS["LIVE"]
        else: emoji = CHANNEL_EMOJIS["PLANNED"]

        if emoji + channel_name != channel.name:
            await channel.edit(name=emoji+channel_name)

        
    async def _update_predictions(self, ctx, channel: discord.TextChannel):
        match = MatchChannel(channel.id)
        embed = await match.to_predictions_embed(ctx)
        try:
            msg = await channel.fetch_message(match.predictions_message_id)
        except discord.NotFound:
            msg = await channel.send(embed=embed)
            match.predictions_message_id = msg.id
            match.save()
        else:
            await msg.edit(embed=embed)
        if not (match.match_start and datetime.datetime.now(datetime.timezone.utc) > match.match_start):
            await verify_reactions(msg, emojis=[match.predictions_team1_emoji, match.predictions_team2_emoji], whitelisted_ids=[self.bot.user.id])
    
    @match.command(aliases=["reveal"])
    async def show(self, ctx, channel: discord.TextChannel):
        await self._update_match(ctx, channel, update_perms=True)

        embed = discord.Embed(color=discord.Color(7844437))
        embed.set_author(name="Match revealed", icon_url="https://cdn.discordapp.com/emojis/809149148356018256.png")
        embed.description = f"{channel.mention} is now visible publically, if it wasn't already."
        await ctx.send(embed=embed)                        
    
    @match.command()
    async def hide(self, ctx, channel: discord.TextChannel):
        overwrites = channel.overwrites
        overwrites[ctx.channel.guild.default_role].update(view_channel=False, send_messages=False)
        await channel.edit(overwrites=overwrites)

        embed = discord.Embed(color=discord.Color(7844437))
        embed.set_author(name="Match hidden", icon_url="https://cdn.discordapp.com/emojis/809149148356018256.png")
        embed.description = f"{channel.mention} is now hidden, if it wasn't already."
        await ctx.send(embed=embed)

    @match.command()
    async def hoist(self, ctx, channel: discord.TextChannel):
        match = MatchChannel(channel.id)
        match.creation_time = datetime.datetime.now()
        match.save()


    @match.command()
    async def vote(self, ctx, channel: discord.TextChannel, argument: str, *, option: str = None):
        match = MatchChannel(channel.id)
        argument = argument.lower()
        output = None

        if argument in ["0", "off", "disable"]:
            match.has_vote = False
            if match.vote_message_id:
                try: msg = await channel.fetch_message(match.vote_message_id)
                except: pass
                else: await msg.delete()
            output = "Disabled map voting"
        
        elif argument in ["1", "on", "enable"]:
            match.has_vote = True
            output = "Enabled map voting"

        elif argument in ["coinflip", "cf", "firstpick"]:
            if not option:
                raise CustomException('Missing required argument!', 'value is a required argument that is missing')
            option = option.lower()

            if option in ["random"]:
                match.vote_coinflip_option = 0
                output = "Coinflip winner will now be random"

            elif option in ["team1", "allies", "us"]:
                match.vote_coinflip_option = 1
                output = "Coinflip winner will now be team 1"
            
            elif option in ["team2", "axis", "ger"]:
                match.vote_coinflip_option = 2
                output = "Coinflip winner will now be team 2"
            
            else:
                raise commands.BadArgument("%s isn't a valid value" % option)
        
        elif argument in ["server", "host"]:
            if not option:
                raise CustomException('Missing required argument!', 'value is a required argument that is missing')

            if option.lower() in ["random", "other", "loser"]:
                match.vote_server_option = 0
                output = "Server host will now be the coinflip loser"

            elif option.lower() in ["team1", "allies", "us"]:
                match.vote_server_option = 1
                output = "Server host will now be team 1"
            
            elif option.lower() in ["team2", "axis", "ger"]:
                match.vote_server_option = 2
                output = "Server host will now be team 2"
            
            else:
                match.vote_server_option = 3
                match.vote_server = option
                output = f"Server host will now be {option}"

        elif argument in ["reset"]:
            match.vote_result = None
            match.vote_coinflip_option = 0
            match.vote_coinflip = None
            match.vote_server_option = 0
            match.vote_server = None
            match.vote_first_ban = 0
            match.vote_progress = None
            match.vote = MapVote(team1=match.team1, team2=match.team2, data=match.vote_progress)
            match.save()
            
            embed = discord.Embed(color=discord.Color(7844437))
            embed.set_author(name="Map vote was reset", icon_url="https://cdn.discordapp.com/emojis/809149148356018256.png")
            embed.description = f"For {channel.mention}."
            await ctx.send(embed=embed)

            match.vote.render()
            await self._update_match(ctx, channel, send=False, update_image=True)

            return

        else:
            raise commands.BadArgument("%s isn't a valid option" % argument)

        match.save()
        embed = discord.Embed(color=discord.Color(7844437))
        embed.set_author(name="Map voting property updated", icon_url="https://cdn.discordapp.com/emojis/809149148356018256.png")
        embed.description = f"{output} for {channel.mention}."
        await ctx.send(embed=embed)

        await self._update_match(ctx, channel, send=False)
                
    @commands.Cog.listener()
    async def on_message(self, message):
        # Is not self?
        if message.author.id == self.bot.user.id: return

        # Is this a match channel?
        try: match = MatchChannel(message.channel.id)
        except: return
        
        # Is there an ongoing vote?
        if match.has_vote and not match.vote_result:
            
            try:
                team_index = match.vote.get_last_team_index()

                team_id = 0
                if team_index == 1: team_id = match.team1
                elif team_index == 2: team_id = match.team2
                try: team_id = int(team_id)
                except ValueError: team_id = 0

                # Does the user have the right role?
                is_admin = True if message.author.permissions_in(message.channel).manage_messages else False
                if message.guild.get_role(team_id) in message.author.roles or is_admin:
                    
                    content = message.content.lower()

                    if not match.vote_first_ban:
                        if 'ban' in content.split() or 'pick' in content.split(): match.vote_first_ban = team_index
                        elif 'host' in content.split() or 'server' in content.split(): match.vote_first_ban = 2 if team_index == 1 else 1
                        else: raise CustomException('Invalid option!', 'Choose between either "ban" and "host".')

                        # Update vote!
                        match.vote.add_progress(team=match.vote_first_ban, action=5, faction=0, map=0)
                        match.save()
                        
                        # Update message
                        ctx = await self.bot.get_context(message)
                        await self._update_match(ctx, message.channel, update_image=False)

                    else:
                        # Undo last ban
                        if is_admin and content in ['back', 'reverse', 'undo']:
                            match.reverse()
                        
                        else:
                            # Get faction from input
                            if 'allies' in content.split() or 'us' in content.split(): faction = 'allies'
                            elif 'axis' in content.split() or 'ger' in content.split(): faction = 'axis'
                            else: raise CustomException('Invalid faction!', 'Available factions are Allies, Axis.')
                            content = content.replace(faction, '', 1).strip()
                            
                            # Get map from input
                            try: map_index = [m.lower() for m in MAPS].index(content)
                            except ValueError: raise CustomException('Invalid map!', 'Available maps are %s.' % ', '.join(MAPS))
                            map = MAPS[map_index]
                            
                            # Is this map available?
                            if (team_index == 1 and match.vote.team1[faction][map] != 'available') or (team_index == 2 and match.vote.team2[faction][map] != 'available'):
                                raise CustomException('This map was already banned!', 'Please pick another one.')
                            
                            # Ban it!
                            match.ban_map(team=team_index, faction=faction, map=map)
                        
                        # Update message
                        ctx = await self.bot.get_context(message)
                        await self._update_match(ctx, message.channel, update_image=True, update_perms=True if match.vote_result else False, delay_predictions=False)
                        # If delayed predictions are ever turned on again, remember to fix the last input to be deleted before the 10min delay

            except CustomException as e:
                embed = discord.Embed(color=discord.Color.from_rgb(221, 46, 68))
                icon_url = 'https://cdn.discordapp.com/emojis/808045512393621585.png'
                embed.set_author(icon_url=icon_url, name=e.error)
                embed.description = str(e)
                msg = await message.channel.send(embed=embed)
                await asyncio.sleep(4)
                await msg.delete()

            finally:
                await message.delete()


    @match.command(aliases=['pred'])
    async def predictions(self, ctx, channel: discord.TextChannel, argument: str, option: str = None):
        match = MatchChannel(channel.id)
        argument = argument.lower()
        output = None

        if argument in ["0", "off", "disable"]:
            match.has_predictions = False
            if match.predictions_message_id:
                try: msg = await channel.fetch_message(match.predictions_message_id)
                except: pass
                else: await msg.delete()
            output = "Disabled match predictions"
        
        elif argument in ["1", "on", "enable"]:
            match.has_predictions = True
            output = "Enabled match predictions"

        elif argument in ["team1", "allies", "us", "emoji1"]:
            if not option:
                raise CustomException('Missing required argument!', 'value is a required argument that is missing')

            converter = commands.EmojiConverter()
            with open('emoji_map.json', 'r') as f:
                emoji_map = json.load(f)
            if option not in emoji_map.values():
                try: option = str(await converter.convert(ctx, option))
                except commands.BadArgument: raise CustomException('Invalid emoji!', f'Can\'t recognize "{option}" as an emoji.')
            match.predictions_team1_emoji = option
            output = f"Emoji for team 1 is now {option}"
        
        elif argument in ["team2", "axis", "ger", "emoji2"]:
            if not option:
                raise CustomException('Missing required argument!', 'value is a required argument that is missing')

            converter = commands.EmojiConverter()
            with open('emoji_map.json', 'r') as f:
                emoji_map = json.load(f)
            if option not in emoji_map.values():
                try: option = str(await converter.convert(ctx, option))
                except commands.BadArgument: raise CustomException('Invalid emoji!', f'Can\'t recognize "{option}" as an emoji.')
            match.predictions_team2_emoji = option
            output = f"Emoji for team 2 is now {option}"
        
        elif argument in ["reset"]:
            match.predictions_team1 = []
            match.predictions_team2 = []
            match.predictions_team1_emoji = get_config()['visuals']['DefaultTeam1Emoji']
            match.predictions_team2_emoji = get_config()['visuals']['DefaultTeam2Emoji']
            match.save()
            
            embed = discord.Embed(color=discord.Color(7844437))
            embed.set_author(name="Match predictions were reset", icon_url="https://cdn.discordapp.com/emojis/809149148356018256.png")
            embed.description = f"For {channel.mention}."
            await ctx.send(embed=embed)

            match.vote.render()
            await self._update_match(ctx, channel, send=False, update_image=True)

            return

        else:
            raise commands.BadArgument("%s isn't a valid option" % argument)

        match.save()
        embed = discord.Embed(color=discord.Color(7844437))
        embed.set_author(name="Map voting property updated", icon_url="https://cdn.discordapp.com/emojis/809149148356018256.png")
        embed.description = f"{output} for {channel.mention}."
        await ctx.send(embed=embed)

        await self._update_match(ctx, channel, send=False)
    
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        # Is not self?
        if payload.user_id == self.bot.user.id: return

        # Is this a match channel?
        try: match = MatchChannel(payload.channel_id)
        except: return
        
        # Does it have predictions and is it one?
        if match.has_predictions and match.predictions_message_id == payload.message_id:

            guild = self.bot.get_guild(payload.guild_id)
            channel = guild.get_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            
            # Has the match started already?
            if match.match_start and datetime.datetime.now(datetime.timezone.utc) > match.match_start:
                await message.clear_reaction(match.predictions_team1_emoji)
                await message.clear_reaction(match.predictions_team2_emoji)
            
            else:
                await message.remove_reaction(payload.emoji, payload.member)
                
                id_s = str(payload.user_id)
                if str(payload.emoji) == match.predictions_team1_emoji:
                    if id_s in match.predictions_team1:
                        match.predictions_team1.remove(id_s)
                    elif id_s in match.predictions_team2:
                        match.predictions_team1.append(id_s)
                        match.predictions_team2.remove(id_s)
                    else:
                        match.predictions_team1.append(id_s)

                elif str(payload.emoji) == match.predictions_team2_emoji:
                    if id_s in match.predictions_team2:
                        match.predictions_team2.remove(id_s)
                    elif id_s in match.predictions_team1:
                        match.predictions_team2.append(id_s)
                        match.predictions_team1.remove(id_s)
                    else:
                        match.predictions_team2.append(id_s)
                
                else:
                    return
                
                match.save()
                ctx = await self.bot.get_context(message)
                await self._update_predictions(ctx, channel)
                
    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        # Is self?
        if payload.user_id == self.bot.user.id:

            # Is this a match channel?
            try: match = MatchChannel(payload.channel_id)
            except: return
            
            # Does it have predictions, is it one, and is it active?
            if match.has_predictions and match.predictions_message_id == payload.message_id and not (match.match_start and datetime.datetime.now(datetime.timezone.utc) > match.match_start):
                
                guild = self.bot.get_guild(payload.guild_id)
                channel = guild.get_channel(payload.channel_id)
                message = await channel.fetch_message(payload.message_id)

                await verify_reactions(message, emojis=[match.predictions_team1_emoji, match.predictions_team2_emoji])
    @commands.Cog.listener()
    async def on_raw_reaction_clear(self, payload):
        # Is this a match channel?
            try: match = MatchChannel(payload.channel_id)
            except: return
            
            # Does it have predictions, is it one, and is it active?
            if match.has_predictions and match.predictions_message_id == payload.message_id and not (match.match_start and datetime.datetime.now(datetime.timezone.utc) > match.match_start):
                
                guild = self.bot.get_guild(payload.guild_id)
                channel = guild.get_channel(payload.channel_id)
                message = await channel.fetch_message(payload.message_id)

                await verify_reactions(message, emojis=[match.predictions_team1_emoji, match.predictions_team2_emoji])

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        try: match = MatchChannel(channel.id)
        except: pass
        else: match.delete()

    @tasks.loop(minutes=3)
    async def channel_name_updater(self):
        try:
            for guild in self.bot.guilds:
                matches = get_all_channels(guild.id)
                
                categories = dict()
                for match in matches:
                    channel = guild.get_channel(match.channel_id)
                    if channel:
                        await self._update_channel_name(channel)

                        """
                        if not channel.overwrites[channel.guild.default_role].view_channel:
                            continue

                        if channel.category not in categories.keys():
                            categories[channel.category] = dict(creation_time=None, matches=list())
                        
                        categories[channel.category]['matches'].append((match, channel))
                        if not categories[channel.category]['creation_time'] or match.creation_time > categories[channel.category]['creation_time']:
                            categories[channel.category]['creation_time'] = match.creation_time
                
                categories = {k: v for k, v in sorted(categories.items(), key=lambda item: item[1]['creation_time'], reverse=True)}

                if categories:
                    calendar_channel = guild.get_channel(get_config_value(guild.id, 'overview_channel_id'))
                    if calendar_channel: 
                        embed = discord.Embed(color=discord.Color(16237246))
                        embed.set_author(name="Match Calendar", icon_url=guild.icon_url)
                        embed.set_thumbnail(url=guild.icon_url)
                        is_first_category = True
                        for category, data in categories.items():
                            match_data = sorted(data['matches'], key=lambda item: item[0].match_start.timestamp() if item[0].match_start else 0)
                            title = category.name if category else "Other"
                            description = '\n'.join([
                                f'No date specified - {channel.mention}'
                                if not match.match_start else (
                                    f'<t:{int(match.match_start.timestamp())}:d> <t:{int(match.match_start.timestamp())}:t> - {channel.mention} (<t:{int(match.match_start.timestamp())}:R>)'
                                    if match.match_start > datetime.datetime.now(datetime.timezone.utc) else (
                                        f'<t:{int(match.match_start.timestamp())}:d> <t:{int(match.match_start.timestamp())}:t> - {channel.mention} R: ||{match.result}||'
                                        if match.result else
                                        f'<t:{int(match.match_start.timestamp())}:d> <t:{int(match.match_start.timestamp())}:t> - {channel.mention}'
                                    )
                                ) for match, channel in match_data
                            ])
                            if is_first_category:
                                embed.title = title
                                embed.description = description
                                is_first_category = False
                            else:
                                embed.add_field(name=title, value=description, inline=False)
                            
                        try: calendar_message = await calendar_channel.fetch_message(get_config_value(guild.id, 'overview_message_id'))
                        except: calendar_message = None

                        if calendar_message:
                            await calendar_message.edit(embed=embed)
                        else:
                            calendar_message = await calendar_channel.send(embed=embed)
                            set_config_value(guild.id, 'overview_message_id', calendar_message.id)
            """
        except Exception as e:
            print('\n\nEXCEPTION WAAAAAA!!!\n', e.__class__.__name__, str(e))
                    

    @commands.Cog.listener()
    async def on_ready(self):
        #self.channel_name_updater.add_exception_type(Exception)
        await asyncio.sleep(60) # Don't hit rate limits during testing
        self.channel_name_updater.start()


def setup(bot):
    bot.add_cog(match(bot))