from typing import Callable
import discord
from discord import app_commands, ui, Interaction
from discord.ext import commands, tasks
import asyncio

import datetime
from dateutil.parser import parse

from lib.channels import MatchChannel, NotFound, get_all_channels
from lib.streams import Stream, FLAGS
from lib.vote import MapVote, MAPS
from cogs._events import CustomException
from utils import get_config


CHANNEL_EMOJIS = {
    'PLANNED': '📆',
    'BAN': '🔨',
    'LIVE': '👀',
    'RESULT': '✅'
}

class CallableButton(ui.Button):
    def __init__(self, callback: Callable, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._callback = callback
    async def callback(self, interaction: Interaction):
        await self._callback(interaction)
class CallableSelect(ui.Select):
    def __init__(self, callback: Callable, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._callback = callback
    async def callback(self, interaction: Interaction):
        await self._callback(interaction, self.values)

class ConfirmView(ui.View):
    def __init__(self, on_confirm: Callable, on_cancel: Callable, timeout = 180):
        super().__init__(timeout=timeout)
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
        self.add_item(CallableButton(label="Confirm", style=discord.ButtonStyle.success, callback=self._on_confirm))
        self.add_item(CallableButton(label="Cancel", style=discord.ButtonStyle.danger, callback=self._on_cancel))
    
    async def _on_confirm(self, interaction: Interaction):
        await self.on_confirm(interaction)
    async def _on_cancel(self, interaction: Interaction):
        await self.on_cancel(interaction)


class match(commands.Cog):
    def __init__(self, bot):
        self.bot: commands.Bot = bot

    MatchGroup = app_commands.Group(name="match", description="Match configuration", default_permissions=discord.Permissions())
    MatchSetGroup = app_commands.Group(name="set", description="Change one of the match's properties", parent=MatchGroup)
    MatchCastersGroup = app_commands.Group(name="casters", description="Assign or remove casters from a match", parent=MatchGroup)
    MatchMapvoteGroup = app_commands.Group(name="mapvote", description="Configurate map voting for a match", parent=MatchGroup)
    MatchPredictionsGroup = app_commands.Group(name="predictions", description="Configurate winner predictions for a match", parent=MatchGroup)
    
    # async def cog_check(self, interaction: Interaction):
    #     return await has_perms(interaction, mod_role=True)

    @MatchGroup.command(name="list", description="Show a list of all match channels")
    async def list(self, interaction: Interaction):
        embed = discord.Embed()
        matches = get_all_channels(interaction.guild.id)
        
        if matches:
            embed.title = f"There are {str(len(matches))} ongoing matches."
            embed.description = ""
            
            categories = dict()
            unknown = list()
            for match in matches:
                channel = interaction.guild.get_channel(match.channel_id)
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
            embed.description = f"You can create one with the following command:\n`/match create <channel> [\"title\"] [\"description\"]`"            

        await interaction.response.send_message(embed=embed)

    @MatchGroup.command(name="create", description="Host a new match inside a channel")
    @app_commands.describe(
        channel="A text channel",
        title="The match's title",
        description="The match's description",
        team1="The first team",
        team2="The second team",
        enable_voting="Whether to enable map voting and winner predictions"
    )
    async def create(self, interaction: Interaction, channel: discord.TextChannel, title: str, description: str = "", team1: discord.Role = None,
                     team2: discord.Role = None, enable_voting: bool = get_config().getboolean('behavior', 'EnableVotingByDefault')):
        try: MatchChannel(channel.id)
        except NotFound: pass
        else: raise commands.BadArgument('A match is already linked with this channel.')
        MatchChannel.new(channel=channel, title=title, desc=description, team1=team1.id if team1 else None, team2=team2.id if team1 else None, has_vote=enable_voting, has_predictions=enable_voting)
        overwrites = channel.overwrites
        overwrites[interaction.channel.guild.default_role] = discord.PermissionOverwrite(view_channel=False, send_messages=False)
        await channel.edit(overwrites=overwrites)

        embed = discord.Embed(color=discord.Color(7844437))
        embed.set_author(name="Match created", icon_url="https://cdn.discordapp.com/emojis/809149148356018256.png")
        embed.description = f"Further customize it using the `/match set ...` command and reveal it with `/match reveal ...`. You will need to set permissions to view the channel for `@everyone` manually`."
        await interaction.response.send_message(embed=embed)

    @MatchGroup.command(name="delete", description="Remove a match from a channel")
    @app_commands.describe(
        channel="The match channel",
    )
    async def delete(self, interaction: Interaction, channel: discord.TextChannel):
        match = MatchChannel(channel.id)

        embed = discord.Embed(description=channel.mention)
        embed.set_author(name='Remove this match?')
        await interaction.response.send_message(embed=embed)

        async def on_confirm(_interaction: Interaction):
            embed = discord.Embed(description=channel.mention, color=discord.Color(7844437))
            embed.set_author(name="Match removed", icon_url="https://cdn.discordapp.com/emojis/809149148356018256.png")
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
            
            message = await _interaction.original_response()
            await message.edit(embed=embed, view=None)
        async def on_cancel(_interaction: Interaction):
            embed = discord.Embed(color=discord.Color.from_rgb(221, 46, 68))
            embed.set_author(name="User cancelled the action", icon_url="https://cdn.discordapp.com/emojis/808045512393621585.png")
            message = await _interaction.original_response()
            await message.edit(embed=embed, view=None)

        await interaction.response.send_message(embed=embed, view=ConfirmView(on_confirm=on_confirm, on_cancel=on_cancel))

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        if isinstance(channel, discord.TextChannel):
            try: MatchChannel(channel.id).delete()
            except: pass


    @MatchGroup.command(name="preview", description="Show a preview of what the match will look like")
    @app_commands.describe(
        channel="The match channel",
    )
    async def view(self, interaction: Interaction, channel: discord.TextChannel):
        match = MatchChannel(channel.id)
        embeds = await match.to_embed(interaction)
        
        if match.has_vote:
            await interaction.response.send_message(embeds=embeds, file=discord.File('output.png'), ephemeral=True)
        else:
            await interaction.response.send_message(embeds=embeds, ephemeral=True)

    async def _set_match_prop(self, interaction: Interaction, channel: discord.TextChannel, prop_name: str, value, display):
        match = MatchChannel(channel.id)
        setattr(match, prop_name, value)
        match.save()
        embed = discord.Embed(color=discord.Color(7844437))
        embed.set_author(name="Property updated", icon_url="https://cdn.discordapp.com/emojis/809149148356018256.png")
        embed.description = f"{channel.mention}'s `{prop_name}` is now {display}."
        await interaction.response.send_message(embed=embed)
        await self._update_match(interaction, channel, send=False)

    @MatchSetGroup.command(name="title")
    @app_commands.describe(
        channel="The match channel",
        value="The new title"
    )
    async def set_title(self, interaction: Interaction, channel: discord.TextChannel, value: str):
        await self._set_match_prop(interaction, channel, "title", value, value)
    @MatchSetGroup.command(name="description")
    @app_commands.describe(
        channel="The match channel",
        value="The new description"
    )
    async def set_description(self, interaction: Interaction, channel: discord.TextChannel, value: str):
        await self._set_match_prop(interaction, channel, "desc", value, value)
    @MatchSetGroup.command(name="date")
    @app_commands.describe(
        channel="The match channel",
        value="The new start time"
    )
    async def set_date(self, interaction: Interaction, channel: discord.TextChannel, value: str):
        match_start = parse(value, fuzzy=True)
        if not match_start.tzinfo:
            match_start = match_start.replace(tzinfo=datetime.timezone.utc)
        match_start = match_start.astimezone(datetime.timezone.utc)
        await self._set_match_prop(interaction, channel, "date", match_start, match_start.isoformat(sep=' '))
    @MatchSetGroup.command(name="team1")
    @app_commands.describe(
        channel="The match channel",
        value="The new team 1"
    )
    async def set_team1(self, interaction: Interaction, channel: discord.TextChannel, value: discord.Role):
        await self._set_match_prop(interaction, channel, "team1", value.id, value.mention)
    @MatchSetGroup.command(name="team2")
    @app_commands.describe(
        channel="The match channel",
        value="The new team 2"
    )
    async def set_team2(self, interaction: Interaction, channel: discord.TextChannel, value: discord.Role):
        await self._set_match_prop(interaction, channel, "team2", value.id, value.mention)
    @MatchSetGroup.command(name="map")
    @app_commands.describe(
        channel="The match channel",
        value="The new map"
    )
    async def set_map(self, interaction: Interaction, channel: discord.TextChannel, value: str):
        await self._set_match_prop(interaction, channel, "map", value, value)
    @MatchSetGroup.command(name="banner")
    @app_commands.describe(
        channel="The match channel",
        url="The new banner URL"
    )
    async def set_banner(self, interaction: Interaction, channel: discord.TextChannel, url: str):
        await self._set_match_prop(interaction, channel, "banner", url, url)
    @MatchSetGroup.command(name="result")
    @app_commands.describe(
        channel="The match channel",
        value="The new result"
    )
    async def set_result(self, interaction: Interaction, channel: discord.TextChannel, value: str):
        await self._set_match_prop(interaction, channel, "result", value, value)

    @MatchCastersGroup.command(name="list", description="List all casters assigned to a match")
    @app_commands.describe(
        channel="The match channel",
    )
    async def casters_list(self, interaction: Interaction, channel: discord.TextChannel):
        match = MatchChannel(channel.id)
        streams = match.get_streams()
        embed = discord.Embed(description="\n".join([s.to_text() for s in streams]) if streams else "No streams yet...")
        await interaction.response.send_message(embed=embed)

    @MatchCastersGroup.command(name="add", description="Add a casters to a match")
    @app_commands.describe(
        channel="The match channel",
        name="The name of the caster",
        language="The language of the stream",
        url="The URL where the stream can be found at"
    )
    @app_commands.choices(language=[
        app_commands.Choice(name=f"{key} ({flag} {name})", value=key)
        for key, (name, flag) in FLAGS.items()
    ])
    async def casters_add(self, interaction: Interaction, channel: discord.TextChannel, name: str, language: str, url: str):
        displaylang, flag = FLAGS.get(language, ['??', '❓'])

        embed = discord.Embed(description=f"({displaylang}) {flag} {name} - <{url}>")
        embed.set_author(name='Add this stream?')

        async def on_confirm(_interaction: Interaction):
            stream = Stream.new(channel.id, language, name, url)
            embed = discord.Embed(description=stream.to_text(), color=discord.Color(7844437))
            embed.set_author(name="Streamer added", icon_url="https://cdn.discordapp.com/emojis/809149148356018256.png")
            message = await _interaction.original_response()
            await message.edit(embed=embed, view=None)
        async def on_cancel(_interaction: Interaction):
            embed = discord.Embed(color=discord.Color.from_rgb(221, 46, 68))
            embed.set_author(name="User cancelled the action", icon_url="https://cdn.discordapp.com/emojis/808045512393621585.png")
            message = await _interaction.original_response()
            await message.edit(embed=embed, view=None)

        await interaction.response.send_message(embed=embed, view=ConfirmView(on_confirm=on_confirm, on_cancel=on_cancel))

    @MatchCastersGroup.command(name="remove", description="Remove a caster from a match")
    @app_commands.describe(
        channel="The match channel",
        index="The index of the caster (starting at 1)"
    )
    async def casters_remove(self, interaction: Interaction, channel: discord.TextChannel, index: int):
        match = MatchChannel(channel.id)
        streams = match.get_streams()
        if not streams:
            raise commands.BadArgument('Match has no streams to remove')

        index = int(index - 1)
        if not 0 < index < len(streams):
            raise commands.BadArgument('Index must be between 1 and %s' % len(streams))

        stream = streams[index]

        embed = discord.Embed(description=stream.to_text())
        embed.set_author(name='Remove this stream?')
        await interaction.response.send_message(embed=embed)

        async def on_confirm(_interaction: Interaction):
            embed = discord.Embed(description=stream.to_text(), color=discord.Color(7844437))
            embed.set_author(name="Streamer removed", icon_url="https://cdn.discordapp.com/emojis/809149148356018256.png")
            stream.delete()
            message = await _interaction.original_response()
            await message.edit(embed=embed, view=None)
        async def on_cancel(_interaction: Interaction):
            embed = discord.Embed(color=discord.Color.from_rgb(221, 46, 68))
            embed.set_author(name="User cancelled the action", icon_url="https://cdn.discordapp.com/emojis/808045512393621585.png")
            message = await _interaction.original_response()
            await message.edit(embed=embed, view=None)

        await interaction.response.send_message(embed=embed, view=ConfirmView(on_confirm=on_confirm, on_cancel=on_cancel))


    async def _update_match(self, interaction: Interaction, channel: discord.TextChannel, send=True, update_image=False, update_perms=False, delay_predictions=False):
        match = MatchChannel(channel.id)
        embeds = await match.to_embed(interaction)

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
                    footer = getattr(embed, '_footer', None)
                    if delay_predictions and match.should_have_predictions():
                        embed.set_footer(text="Predictions will be available\nin approx. 10 minutes")
                    msg = await channel.send(embed=embed)
                    match.predictions_message_id = msg.id
                    match.save()

                    if match.should_have_predictions():
                        if delay_predictions:
                            await asyncio.sleep(10*60)
                            if footer:
                                embed._footer = footer
                            else:
                                embed.remove_footer()
                            await msg.edit(embed=embed, view=self._get_predictions_view(match))
                        else:
                            await msg.edit(view=self._get_predictions_view(match))
            else:
                embed = embeds.pop(0)
                if match.should_have_predictions():
                    await msg.edit(embed=embed, view=self._get_predictions_view(match))
                else:
                    await msg.edit(embed=embed)
        elif match.predictions_message_id:
            try: msg = await channel.fetch_message(match.predictions_message_id)
            except discord.NotFound: pass
            else: await msg.delete()
            finally:
                match.predictions_message_id = 0
                match.save()

        if update_perms:
            overwrites = channel.overwrites
            defaults = overwrites[interaction.channel.guild.default_role]
            defaults.update(send_messages=False, add_reactions=False, read_message_history=True)
            overwrites[interaction.channel.guild.default_role] = defaults
            
            if match.has_vote:
                try: rep1 = await commands.RoleConverter().convert(interaction, str(match.team1))
                except: pass
                else: overwrites[rep1] = discord.PermissionOverwrite(send_messages=None if match.vote_result else True, view_channel=None if defaults.view_channel else True)
                try: rep2 = await commands.RoleConverter().convert(interaction, str(match.team2))
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

        
    async def _update_predictions(self, interaction: Interaction, channel: discord.TextChannel):
        match = MatchChannel(channel.id)
        embed = await match.to_predictions_embed(interaction)
        try:
            msg = await channel.fetch_message(match.predictions_message_id)
        except discord.NotFound:
            view = self._get_predictions_view(match)
            msg = await channel.send(embed=embed, view=view)
            match.predictions_message_id = msg.id
            match.save()
        else:
            await msg.edit(embed=embed)

        if match.should_have_predictions():
            if not msg.components:
                view = self._get_predictions_view(match)
                await msg.edit(view=view)
        else:
            if msg.components:
                await msg.edit(view=ui.View())
    
    @MatchGroup.command(name="reveal", description="Start showing the match in its channel")
    @app_commands.describe(
        channel="The match channel",
    )
    async def show(self, interaction: Interaction, channel: discord.TextChannel):
        await self._update_match(interaction, channel, update_perms=True)

        embed = discord.Embed(color=discord.Color(7844437))
        embed.set_author(name="Match revealed", icon_url="https://cdn.discordapp.com/emojis/809149148356018256.png")
        embed.description = f"{channel.mention} is now visible publically, if it wasn't already."
        await interaction.response.send_message(embed=embed)                        
    
    @MatchGroup.command(name="hide", description="Stop showing a match in its channel")
    @app_commands.describe(
        channel="The match channel",
    )
    async def hide(self, interaction: Interaction, channel: discord.TextChannel):
        overwrites = channel.overwrites
        overwrites[interaction.channel.guild.default_role].update(view_channel=False, send_messages=False)
        await channel.edit(overwrites=overwrites)

        embed = discord.Embed(color=discord.Color(7844437))
        embed.set_author(name="Match hidden", icon_url="https://cdn.discordapp.com/emojis/809149148356018256.png")
        embed.description = f"{channel.mention} is now hidden, if it wasn't already."
        await interaction.response.send_message(embed=embed)


    async def _after_setting_change(self, interaction: Interaction, match: MatchChannel, channel: discord.TextChannel, output: str = None):
        match.save()
        embed = discord.Embed(color=discord.Color(7844437))
        embed.set_author(name="Property updated", icon_url="https://cdn.discordapp.com/emojis/809149148356018256.png")
        embed.description = f"{output} for {channel.mention}."
        await interaction.response.send_message(embed=embed)
        await self._update_match(interaction, channel, send=False)

    @MatchMapvoteGroup.command(name="enable")
    @app_commands.describe(
        channel="The match channel",
    )
    async def mapvote_enable(self, interaction: Interaction, channel: discord.TextChannel):
        match = MatchChannel(channel.id)
        match.has_vote = True
        await self._after_setting_change(interaction, match, channel, "Enabled map voting")
    @MatchMapvoteGroup.command(name="disable")
    @app_commands.describe(
        channel="The match channel",
    )
    async def mapvote_disable(self, interaction: Interaction, channel: discord.TextChannel):
        match = MatchChannel(channel.id)
        match.has_vote = False
        if match.vote_message_id:
            try: msg = await channel.fetch_message(match.vote_message_id)
            except: pass
            else: await msg.delete()
        await self._after_setting_change(interaction, match, channel, "Disabled map voting")
    @MatchMapvoteGroup.command(name="coinflip")
    @app_commands.describe(
        channel="The match channel",
        option="Who should win the coinflip"
    )
    @app_commands.choices(option=[
        app_commands.Choice(name="random", value="random"),
        app_commands.Choice(name="team1", value="team1"),
        app_commands.Choice(name="team2", value="team2"),
    ])
    async def mapvote_coinflip(self, interaction: Interaction, channel: discord.TextChannel, option: str):
        match = MatchChannel(channel.id)

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
        
        await self._after_setting_change(interaction, match, channel, output)
    @MatchMapvoteGroup.command(name="serverhost")
    @app_commands.describe(
        channel="The match channel",
        option="Who should be the server host"
    )
    @app_commands.choices(option=[
        app_commands.Choice(name="other", value="other"),
        app_commands.Choice(name="team1", value="team1"),
        app_commands.Choice(name="team2", value="team2"),
    ])
    async def mapvote_serverhost(self, interaction: Interaction, channel: discord.TextChannel, option: str):
        match = MatchChannel(channel.id)

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
        
        await self._after_setting_change(interaction, match, channel, output)
    @MatchMapvoteGroup.command(name="reset")
    @app_commands.describe(
        channel="The match channel",
    )
    async def mapvote_reset(self, interaction: Interaction, channel: discord.TextChannel):
        match = MatchChannel(channel.id)
        match.vote_result = None
        match.vote_coinflip_option = 0
        match.vote_coinflip = None
        match.vote_server_option = 0
        match.vote_server = None
        match.vote_first_ban = 0
        match.vote_progress = None
        match.vote = MapVote(team1=match.team1, team2=match.team2, data=match.vote_progress)
        await self._after_setting_change(interaction, match, channel, "Reset map vote")

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
                is_admin = True if message.channel.permissions_for(message.author).manage_messages else False
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
                        interaction = await self.bot.get_context(message)
                        await self._update_match(interaction, message.channel, update_image=False)

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
                        interaction = await self.bot.get_context(message)
                        await self._update_match(interaction, message.channel, update_image=True, update_perms=True if match.vote_result else False, delay_predictions=False)
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

    @MatchPredictionsGroup.command(name="enable")
    @app_commands.describe(
        channel="The match channel",
    )
    async def predictions_enable(self, interaction: Interaction, channel: discord.TextChannel):
        match = MatchChannel(channel.id)
        match.has_predictions = True
        await self._after_setting_change(interaction, match, channel, "Enabled predictions")
    @MatchPredictionsGroup.command(name="disable")
    @app_commands.describe(
        channel="The match channel",
    )
    async def predictions_disable(self, interaction: Interaction, channel: discord.TextChannel):
        match = MatchChannel(channel.id)
        match.has_predictions = False
        if match.predictions_message_id:
            try: msg = await channel.fetch_message(match.predictions_message_id)
            except: pass
            else: await msg.delete()
        await self._after_setting_change(interaction, match, channel, "Disabled predictions")
    @MatchPredictionsGroup.command(name="reset")
    @app_commands.describe(
        channel="The match channel",
    )
    async def predictions_enable(self, interaction: Interaction, channel: discord.TextChannel):
        match = MatchChannel(channel.id)
        match.predictions_team1 = []
        match.predictions_team2 = []
        match.predictions_team1_emoji = get_config()['visuals']['DefaultTeam1Emoji']
        match.predictions_team2_emoji = get_config()['visuals']['DefaultTeam2Emoji']
        await self._after_setting_change(interaction, match, channel, "Reset predictions")

    def _get_predictions_view(self, match: MatchChannel):
        view = ui.View(timeout=None)
        async def on_press_1(interaction: Interaction):
            await self.user_make_prediction(interaction, 1)
        async def on_press_2(interaction: Interaction):
            await self.user_make_prediction(interaction, 2)
        

        view.add_item(CallableButton(on_press_1, emoji=match.predictions_team1_emoji, style=discord.ButtonStyle.primary))
        view.add_item(CallableButton(on_press_2, emoji=match.predictions_team2_emoji, style=discord.ButtonStyle.primary))
        
        view.add_item(CallableButton(self.user_make_prediction, emoji="❓", style=discord.ButtonStyle.gray))

        return view

    async def user_make_prediction(self, interaction: Interaction, vote: int = None):
        match = MatchChannel(interaction.channel_id)

        # Has the match started already?
        if not match.should_have_predictions():
            await interaction.response.send_message("Sorry, but predictions are closed! You can no longer vote.", ephemeral=True)
            embed = await match.to_predictions_embed(interaction)
            await interaction.message.edit(embed=embed, view=ui.View())
        
        else:
                        
            id_s = str(interaction.user.id)
            cur_vote_id = match.get_prediction_of_user(interaction.user.id)

            if not vote:
                if cur_vote_id:
                    cur_vote = match.get_team1(interaction, False) if cur_vote_id == 1 else match.get_team2(interaction, False)
                    embed = discord.Embed(color=discord.Color(7844437))
                    embed.set_author(name=f"Your current vote is {cur_vote}!", icon_url="https://cdn.discordapp.com/emojis/809149148356018256.png")
                    embed.description = "To change your vote you can always press one of the buttons."
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return

                else:
                    embed = discord.Embed(
                        title = "You have not yet voted!",
                        description = "As long as the match has not started yet you can cast your vote, or update your existing vote, by pressing one of the buttons."
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            elif vote == 1:
                if id_s in match.predictions_team1:
                    pass
                elif id_s in match.predictions_team2:
                    match.predictions_team1.append(id_s)
                    match.predictions_team2.remove(id_s)
                else:
                    match.predictions_team1.append(id_s)

            elif vote == 2:
                if id_s in match.predictions_team2:
                    pass
                elif id_s in match.predictions_team1:
                    match.predictions_team2.append(id_s)
                    match.predictions_team1.remove(id_s)
                else:
                    match.predictions_team2.append(id_s)
            
            else:
                return

            match.save()
            await self._update_predictions(interaction, interaction.channel)

            new_vote = match.get_team1(interaction, False) if vote == 1 else match.get_team2(interaction, False)
            embed = discord.Embed(color=discord.Color(7844437))
            embed.set_author(name=f"Voted for {new_vote}!", icon_url="https://cdn.discordapp.com/emojis/809149148356018256.png")
            await interaction.response.send_message(embed=embed, ephemeral=True)

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
                        embed.set_author(name="Match Calendar", icon_url=guild.icon.url)
                        embed.set_thumbnail(url=guild.icon.url)
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
        for guild in self.bot.guilds:
            matches = get_all_channels(guild.id)
            for match in matches:
                if match.has_predictions:
                    channel = guild.get_channel(match.channel_id)
                    try:
                        message = await channel.fetch_message(match.predictions_message_id)
                    except:
                        continue
                    else:
                        if match.should_have_predictions():
                            ctx = await self.bot.get_context(message)
                            embed = await match.to_predictions_embed(ctx)
                            await message.edit(embed=embed, view=self._get_predictions_view(match))
                            print('+', channel.name, match.title)
                        else:
                            if message.components:
                                await message.edit(view=ui.View())
                                print('-', channel.name, match.title)

        #self.channel_name_updater.add_exception_type(Exception)
        await asyncio.sleep(60) # Don't hit rate limits during testing
        self.channel_name_updater.start()


async def setup(bot):
    await bot.add_cog(match(bot))