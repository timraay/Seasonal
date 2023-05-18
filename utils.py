import discord
from discord.ext import commands
from asyncio import TimeoutError
from configparser import ConfigParser
from functools import wraps
import asyncio

def int_to_emoji(value: int):
    if value == 0: return "0️⃣"
    elif value == 1: return "1️⃣"
    elif value == 2: return "2️⃣"
    elif value == 3: return "3️⃣"
    elif value == 4: return "4️⃣"
    elif value == 5: return "5️⃣"
    elif value == 6: return "6️⃣"
    elif value == 7: return "7️⃣"
    elif value == 8: return "8️⃣"
    elif value == 9: return "9️⃣"
    elif value == 10: return "🔟"
    else: return f"**#{str(value)}**"

def get_name(user):
    return user.nick if user.nick else user.name

def add_empty_fields(embed):
    try: fields = len(embed._fields)
    except AttributeError: fields = 0
    if fields > 3:
        empty_fields_to_add = 3 - (fields % 3)
        if empty_fields_to_add in [1, 2]:
            for i in range(empty_fields_to_add):
                embed.add_field(name="‏‎ ", value="‎ ") # These are special characters that can not be seen
    return embed


async def ask_reaction(ctx, embed, options, timeout=180.0, delete_after=False):
    emojis = []
    _options = "**Pick one of the below answers**"
    for emoji, option in options.items():
        emojis.append(emoji)
        _options += f"\n{emoji} {option}"

    embed.add_field(name="‏", value=_options, inline=False)
    msg = await ctx.send(embed=embed)

    for emoji in emojis:
        await msg.add_reaction(emoji)

    def check_reaction(reaction, user):
        return str(reaction.emoji) in emojis and user == ctx.author and reaction.message == msg
    try:
        reaction, user = await ctx.bot.wait_for('reaction_add', check=check_reaction, timeout=timeout)
    except TimeoutError:
        if delete_after:
            await msg.delete()
        else:
            await msg.clear_reactions()
            embed.set_field_at(-1, name="‏", value=_options+"\n\nTimed out, execute the command again.", inline=False)
            embed.color = discord.Color.from_rgb(221, 46, 68)
            await msg.edit(embed=embed)
        return

    if delete_after:
        await msg.delete()
    else:
        await msg.clear_reactions()
        _options = "**Answer:**"
        for emoji, option in options.items():
            if emoji == str(reaction.emoji): _options += f"\n{emoji} **{option}**"
            else: _options += f"\n{emoji} {option}"
        embed.set_field_at(-1, name="‏", value=_options, inline=False)
        await msg.edit(embed=embed)
    return str(reaction.emoji)

async def ask_message(ctx, embed, timeout=180.0, allow_image=False, delete_after=False):
    if allow_image: _options = "**Type out your answer, image attachment allowed**"
    else: _options = "**Type out your answer**"

    embed.add_field(name="‏", value=_options, inline=False)
    msg = await ctx.send(embed=embed)

    def check_message(message):
        return message.author == ctx.author and message.channel == ctx.channel and message.content
    try:
        message = await ctx.bot.wait_for('message', check=check_message, timeout=timeout)
    except TimeoutError:
        if delete_after:
            await msg.delete()
        else:
            embed.set_field_at(-1, name="‏", value=_options+"\n\nTimed out, execute the command again.", inline=False)
            embed.color = discord.Color.from_rgb(221, 46, 68)
            await msg.edit(embed=embed)
            if allow_image: return None, None
            else: return None

    if allow_image:
        attachment = ""
        for att in message.attachments:
            if att.height:
                if att.filename.lower().split('.')[-1] in ["tif", "tiff", "bmp", "jpg", "jpeg", "gif", "png", "eps"]:
                    attachment = att.url
                    embed.set_image(url=attachment)
                else:
                    if att.is_spoiler: message.content += f"\n\n||{att.url}||"
                    else: message.content += f"\n\n{att.url}"
                break
        if delete_after:
            await msg.delete()
        else:
            _options = f"**Answer:**\n>>> \"{message.content}\""
            embed.set_field_at(-1, name="‏", value=_options, inline=False)
            await msg.edit(embed=embed)
        return message.content, attachment
    else:
        if delete_after:
            await msg.delete()
        else:
            _options = f"**Answer:**\n>>> \"{message.content}\""
            embed.set_field_at(-1, name="‏", value=_options, inline=False)
            await msg.edit(embed=embed)
        return message.content


async def verify_reactions(message: discord.Message, emojis: list, whitelisted_ids: list = None):
    # Get list of current emojis
    reacted_emojis = [str(reaction.emoji) for reaction in message.reactions]

    # Add missing emojis
    for emoji in emojis:
        if emoji not in reacted_emojis:
            await message.add_reaction(emoji)
    
    for reaction in message.reactions:
        # Clear faulty emojis
        if str(reaction.emoji) not in emojis:
            await message.clear_reaction(reaction.emoji)
        
        elif whitelisted_ids:
            # Remove reactions from users that are not whitelisted
            if not isinstance(whitelisted_ids, list):
                whitelisted_ids = [whitelisted_ids]
            async for user in reaction.users():
                if user.id not in whitelisted_ids:
                    await message.remove_reaction(emoji, user)


def retry(times: int, delay: float = None):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            for i in range(times):
                try:
                    res = await func(*args, **kwargs)
                except:
                    if times - 1 == i:
                        raise
                    elif delay:
                        await asyncio.sleep(delay)
                else:
                    return res
        return wrapper
    return decorator


CONFIG = {}
def get_config() -> ConfigParser:
    global CONFIG
    if not CONFIG:
        parser = ConfigParser()
        parser.read('config.ini', encoding='utf-8')
        CONFIG = parser
    return CONFIG
    