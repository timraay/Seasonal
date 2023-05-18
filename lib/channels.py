import discord
from discord.ext import commands

from datetime import datetime, timezone
from random import randint

from lib.vote import MapVote
from lib.streams import Stream
from utils import get_config

import sqlite3
db = sqlite3.connect('seasonal.db')
cur = db.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS "channels" (
	"creation_time"	TEXT,
	"guild_id"	INTEGER,
	"channel_id"	INTEGER,
	"message_id"	INTEGER,
	"title"	TEXT,
	"desc"	TEXT,
	"match_start"	TEXT,
	"map"	TEXT,
	"team1"	TEXT,
	"team2"	TEXT,
	"banner_url"	TEXT,
	"has_vote"	INTEGER,
	"has_predictions"	INTEGER,
	"result"	TEXT,
	"vote_message_id"	INTEGER,
	"vote_result"	TEXT,
	"vote_coinflip_option"	INTEGER,
	"vote_coinflip"	INTEGER,
	"vote_server_option"	INTEGER,
	"vote_server"	TEXT,
	"vote_first_ban"	INTEGER,
	"vote_progress"	TEXT,
	"predictions_message_id"	INTEGER,
	"predictions_team1"	TEXT,
	"predictions_team2"	TEXT,
	"predictions_team1_emoji"	TEXT,
	"predictions_team2_emoji"	TEXT,
	PRIMARY KEY("channel_id")
);""")
db.commit()

def get_all_channels(guild_id):
    cur.execute('SELECT channel_id FROM channels WHERE guild_id = ?', (guild_id,))
    res = cur.fetchall()
    return [MatchChannel(channel_id[0]) for channel_id in res]

class MatchChannel:
    def __init__(self, channel_id):
        cur.execute('SELECT * FROM channels WHERE channel_id = ?', (channel_id,))
        res = cur.fetchone()
        if not res: raise NotFound("There is no match attached to channel %s" % channel_id)

        (self.creation_time, self.guild_id, self.channel_id, self.message_id, self.title, self.desc, self.match_start,
        self.map, self.team1, self.team2, self.banner_url, self.has_vote, self.has_predictions, self.result,
        self.vote_message_id, self.vote_result, self.vote_coinflip_option, self.vote_coinflip,
        self.vote_server_option, self.vote_server, self.vote_first_ban, self.vote_progress, self.predictions_message_id,
        self.predictions_team1, self.predictions_team2, self.predictions_team1_emoji, self.predictions_team2_emoji) = res

        self.creation_time = datetime.fromisoformat(self.creation_time) if self.creation_time else datetime.now()
        self.match_start = datetime.fromisoformat(self.match_start) if self.match_start else None
        self.has_vote = bool(self.has_vote)
        self.has_predictions = bool(self.has_predictions)

        self.vote = MapVote(team1=self.team1, team2=self.team2, data=self.vote_progress)

        self.predictions_team1 = self.predictions_team1.split(',') if self.predictions_team1 else []
        self.predictions_team2 = self.predictions_team2.split(',') if self.predictions_team2 else []

    @classmethod
    def new(cls, channel, title: str, desc: str, match_start: datetime = None, map=None, team1 = None, team2 = None, banner_url: str = None, has_vote: bool = False, has_predictions: bool = False, result: str = None):
        creation_time = datetime.now()
        channel_id = channel.id
        guild_id = channel.guild.id
        if match_start and not match_start.tzinfo:
            raise ValueError('match_start should be an aware Datetime object, not naïve')
        message_id = 0
        vote_message_id = 0
        vote_result = None
        vote_coinflip_option = 0
        vote_coinflip = None
        vote_server_option = 0
        vote_server = None
        vote_first_ban = None
        vote_progress = None
        predictions_message_id = 0
        predictions_team1 = ''
        predictions_team2 = ''
        predictions_team1_emoji = get_config()['visuals']['DefaultTeam1Emoji']
        predictions_team2_emoji = get_config()['visuals']['DefaultTeam2Emoji']
        cur.execute(
            "INSERT INTO channels VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (creation_time, guild_id, channel_id, message_id, title, desc, match_start, map, team1, team2, banner_url, int(has_vote), int(has_predictions), result,
            vote_message_id, vote_result, vote_coinflip_option, vote_coinflip, vote_server_option, vote_server, vote_first_ban, vote_progress,
            predictions_message_id, predictions_team1, predictions_team2, predictions_team1_emoji, predictions_team2_emoji)
        )
        db.commit()
        return cls(channel_id)

    def save(self):
        self.vote_progress = ','.join(self.vote.progress)
        cur.execute("""UPDATE channels SET
        creation_time = ?, message_id = ?, title = ?, desc = ?, match_start = ?, map = ?, team1 = ?, team2 = ?,
        banner_url = ?, has_vote = ?, has_predictions = ?, result = ?, vote_message_id = ?,
        vote_result = ?, vote_coinflip_option = ?, vote_coinflip = ?, vote_server_option = ?,
        vote_server = ?, vote_first_ban = ?, vote_progress = ?, predictions_message_id = ?, predictions_team1 = ?,
        predictions_team2 = ?, predictions_team1_emoji = ?, predictions_team2_emoji = ? WHERE channel_id = ?""",
        (self.creation_time.isoformat(), self.message_id, self.title, self.desc, self.match_start.isoformat() if isinstance(self.match_start, datetime) else None,
        self.map, self.team1, self.team2, self.banner_url, int(self.has_vote), int(self.has_predictions), self.result, self.vote_message_id,
        self.vote_result, self.vote_coinflip_option, self.vote_coinflip, self.vote_server_option, self.vote_server, self.vote_first_ban, self.vote_progress,
        self.predictions_message_id, ','.join(self.predictions_team1), ','.join(self.predictions_team2), self.predictions_team1_emoji, self.predictions_team2_emoji,
        self.channel_id))
        db.commit()

    def delete(self):
        cur.execute("""DELETE FROM channels WHERE channel_id = ?""", (self.channel_id,))
        db.commit()
        for stream in self.get_streams():
            stream.delete()

    async def get_channel(self, ctx):
        try: return await commands.TextChannelConverter().convert(ctx, self.channel_id)
        except commands.BadArgument: return None
    def get_team1(self, ctx, mention=True):
        try: team = int(self.team1)
        except: team = str(self.team1)
        
        result = ctx.guild.get_role(team)
        if result:
            if result.name.endswith('*'):
                try: result = [role for role in ctx.guild.roles if role.name == result.name[:-1]][0]
                except IndexError: pass

            if mention: return result.mention
            else: return result.name
        else:
            team = str(team)
            return team[:-1] if team.endswith('*') else team
    def get_team2(self, ctx, mention=True):
        try: team = int(self.team2)
        except: team = str(self.team2)
        
        result = ctx.guild.get_role(team)
        if result:
            if result.name.endswith('*'):
                try: result = [role for role in ctx.guild.roles if role.name == result.name[:-1]][0]
                except IndexError: pass

            if mention: return result.mention
            else: return result.name
        else:
            team = str(team)
            return team[:-1] if team.endswith('*') else team
    def get_streams(self):
        return Stream.in_channel(self.channel_id)

    async def to_payload(self, ctx, render_images=False, delay_predictions=False):
        data = {
            'embeds': []
        }
        data['embeds'].append(await self.to_match_embed(ctx))

        if self.has_vote:
            embed, file = await self.to_vote_embed(ctx, render_images)
            data['embeds'].append(embed)
            if render_images:
                data['file'] = file

        if self.should_show_predictions():
            embed = await self.to_predictions_embed(ctx, delay_predictions)
            data['embeds'].append(embed)

        return data
    async def to_match_embed(self, ctx):
        if not self.has_vote:
            embed = discord.Embed(title=self.title, description=self.desc if self.desc else None)
            embed.add_field(inline=True, name='🔵 Team 1 (Allies)', value=self.get_team1(ctx))
            embed.add_field(inline=True, name='🔴 Team 2 (Axis)', value=self.get_team2(ctx))
            embed.add_field(inline=True, name='🗺️ Map', value=str(self.map) if self.map else "Unknown")

        else:
            embed = discord.Embed(title=self.title, description=self.desc if self.desc else None)
            team1 = self.get_team1(ctx)
            team2 = self.get_team2(ctx)
            if not self.vote_result:
                embed.add_field(inline=True, name='🔵 Team 1', value=team1)
                embed.add_field(inline=True, name='🔴 Team 2', value=team2)
            else:
                embed.add_field(inline=True, name=f'🔵 Team 1 ({"Axis" if self.vote_result.startswith("!") else "Allies"})', value=team1)
                embed.add_field(inline=True, name=f'🔴 Team 2 ({"Allies" if self.vote_result.startswith("!") else "Axis"})', value=team2)
            embed.add_field(inline=True, name='🗺️ Map', value=str(self.map) if self.vote_result else "Ban phase ongoing")

        if not self.match_start: embed.add_field(inline=True, name='📅 Match Start', value='Unknown')
        else: embed.add_field(inline=True, name='📅 Match Start', value=f'<t:{int(self.match_start.timestamp())}:F>')

        if self.result: embed.add_field(inline=True, name='🎯 Result', value=f"||{str(self.result)}||")

        streams = self.get_streams()
        if streams: embed.add_field(inline=False, name='🎙️ Streamers', value="\n".join([stream.to_text() for stream in streams]))
        if self.banner_url: embed.set_image(url=self.banner_url)
        return embed
    async def to_vote_embed(self, ctx, render_images=False):
        # Map vote embed
        embed = discord.Embed(title='Map Ban Phase')

        if not self.vote_coinflip:
            if self.vote_coinflip_option == 0:
                self.vote_coinflip = randint(1, 2)
            elif self.vote_coinflip_option in [1, 2]:
                self.vote_coinflip = self.vote_coinflip_option
            self.vote.add_progress(team=self.vote_coinflip, action=4, faction=0, map=0)
        
        team1 = self.get_team1(ctx)
        team2 = self.get_team2(ctx)
        coinflip_winner = team1 if self.vote_coinflip == 1 else (team2 if self.vote_coinflip == 2 else "Unknown")

        first_ban = (team1, team2)[self.vote_first_ban-1] if self.vote_first_ban else 'TBD'
        
        server_host = 'Unknown'
        if not self.vote_server:
            if not self.vote_first_ban:
                server_host = 'TBD'
            elif self.vote_server_option == 0:
                self.vote_server = '2' if self.vote_first_ban == 1 else '1'
            elif self.vote_server_option in [1, 2]:
                self.vote_server = str(self.vote_server_option)

        if self.vote_server == '1': server_host = team1
        elif self.vote_server == '2': server_host = team2
        elif self.vote_server: server_host = self.vote_server

        self.save()

        embed.add_field(inline=True, name='🎲 Coinflip Winner', value=coinflip_winner)
        embed.add_field(inline=True, name='🔨 First Ban', value=first_ban)
        embed.add_field(inline=True, name='💻 Server Host', value=server_host)

        progress = self.parse_progress(self.vote_progress, self.get_team1(ctx), self.get_team2(ctx))
        embed.description = '\n'.join(progress)
        team_index = self.vote.get_last_team_index()
        team_mention = self.get_team1(ctx) if team_index == 1 else self.get_team2(ctx)
        if not self.vote_result:
            if not self.vote_first_ban:
                embed.description += f'\n\n{team_mention}, do you choose to ban first, or to host the server? Type `ban` or `host` below.'
            else:
                embed.description += f"\n\nYour time to ban, {team_mention}! Type map + faction down below.\nExample: `Foy Allies`."

        self.vote.team1_name = self.get_team1(ctx, mention=False)
        self.vote.team2_name = self.get_team2(ctx, mention=False)

        if render_images:
            img = self.vote.render()
            file = discord.File(img, filename='output.png')
        else:
            file = None
        embed.set_image(url='attachment://output.png')

        return embed, file
    async def to_predictions_embed(self, ctx, delay_predictions=False):
        # Predictions
        embed = discord.Embed(title='Match Predictions')
        embed.description = f'_ _\n{self.predictions_team1_emoji} {self.get_team1(ctx)} (**{len(self.predictions_team1)}** votes)\n{self.predictions_team2_emoji} {self.get_team2(ctx)} (**{len(self.predictions_team2)}** votes)'

        if not self.should_have_predictions():
            embed.set_footer(text='Voting has ended')
        elif self.match_start:
            if delay_predictions:
                embed.set_footer(text="Predictions will be available\nin approx. 10 minutes")
            else:
                embed.set_footer(text='Voting ends at ' + self.match_start.strftime('%A %B %d, %H:%M %p UTC').replace(" 0", " "))
        return embed
    
    def should_have_predictions(self):
        return (
            self.should_show_predictions()
            and not self.result
            and (
                not self.match_start
                or datetime.now(timezone.utc) > self.match_start
            )
        )

    def should_show_predictions(self):
        return self.has_predictions and not (self.has_vote and not self.vote_result)

    def get_prediction_of_user(self, user_id):
        user_id = str(user_id)
        if user_id in self.predictions_team1:
            return 1
        elif user_id in self.predictions_team2:
            return 2
        else:
            return None

    def ban_map(self, team: int, faction, map):
        self.vote.ban(team, faction, map)
        if str(self.vote).count('0') == 2:
            for team_index, data in enumerate([self.vote.team1, self.vote.team2]):
                team_index += 1
                for faction, column in data.items():
                    for map, status in column.items():
                        if status == 'available':
                            self.vote.final_pick(team=team_index, faction=faction, map=map)
                            if not self.vote_result:
                                if (team_index == 1 and faction == 'allies') or (team_index == 2 and faction == 'axis'):
                                    self.vote_result = map
                                else:
                                    self.vote_result = '!' + map
                                self.map = map
                            break
        self.save()
    def reverse(self, amount: int = 1):
        for i in range(amount):
            if not len(self.vote.progress) > 3:
                break
            del self.vote.progress[-2:]
        self.save()

    def parse_progress(self, progress, team1, team2):
        output = list()
        for item in progress.split(','):
            if item:
                action = self._parse_individual_progress(item, team1, team2)
                if action: output.append(action)
        return output
    def _parse_individual_progress(self, progress, team1, team2):
        data = self.vote._translate_action(progress)

        if data['team_index'] == 1:
            data['team'] = team1
            data['other'] = team2
        elif data['team_index'] == 2:
            data['team'] = team2
            data['other'] = team1
        
        if data['type'] == 1: action = "{team} banned {map} {faction}.".format(**data)
        elif data['type'] == 3: action = "{map} {faction} is final pick for {team}.".format(**data)
        elif data['type'] == 4: action = "{team} won the coinflip.".format(**data)
        elif data['type'] == 5:
            if self.vote_coinflip == self.vote_first_ban: action = "{team} chooses to ban first. {other} may host the server.".format(**data)
            else: action = "{other} lets {team} ban first, and will be hosting the server.".format(**data)
        else: action = None
        return action


class NotFound(Exception):
    """Raised when a database row couldn't be found"""
    pass


if __name__ == '__main__':
    channel = MatchChannel(1)
