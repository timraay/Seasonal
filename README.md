# Installation guide

## **Prerequisites**
- Git
- Python 3.8 or above
- A bot application on Discord's [developer portal](https://discord.com/developers/applications) with all Priviliged Gateway Intents enabled

```
git clone https://github.com/timraay/Seasonal.git
cd Seasonal
pip install -r requirements.txt
```
Now fill in the `config.ini` file and follow any instructions there. Then start the bot:
```
python bot.py
```

## Linux

On Linux you will likely want to host your bot inside of a Screen. Also, you need to install wkhtmltoimage, since the bundled libraries are for Windows. Try running either of the commands below. If none works, you will have to download and unpack the binaries yourself from the wkhtmltopdf website.
```
sudo apt-get install wkhtmltopdf
sudo apt install wkhtmltopdf
yum install wkhtmltopdf
```

# How to use

The bot uses mostly slash commands, however not all commands have been migrated yet and still use chat commands using the bot prefix defined in the `config.ini`.

> Default bot prefix: `s!`

## The `/match` command

*Is used to turn text channels into "match channels" and can be used to configure them*
> `/match create <#channel> <match title> [match description] [@Team1] [@Team2] [BansAndPredictionsEnabled?]`
> 
> *Turns a channel into a match channel*
> - This creates a match, but will not yet show it in the channel.
> - To preview how it will look, use `/match view <#channel>`
> - To make the match appear, use `/match reveal <#channel>`
> - To then hide it again, use `/match hide <#channel>`
> - To remove a match entirely, use `/match delete <#channel>`. This is irreversible.
> 
> `/match set <#channel> (title|desc|date|team1|team2|map|banner|result) <value>`
> *Configure a match's properties*
> - "date" will set the match start time in UTC. The parser is quite flexible; stuff like "saturday 19th 10pm" works fine.
> - A lot of these values default to "none" upon match creation, which in result will hide some of these values. After setting them to something you can't set them back to "none"
> - "banner" has to be a valid link to a .png or .jpeg file

## The `/match vote` subcommand

*This lets you enable/disable the map ban, and gives you finer control over the feature*
> `/match vote <#channel> (enable|disable|on|off)`
> 
> *Enable or disable voting*
> 
> `/match vote <#channel> coinflip (random|team1|team2)`
> 
> *Configures who will win the coinflip*
> - By default "random". After the ban phase has started you can no longer change this without resetting the entire ban phase.
> 
> `/match vote <#channel> reset`
> 
> *Resets the entire map ban config*
> - Disables the ban phase, deletes all the progress, and makes the coinflip random again.

## The `/match predictions` subcommand

*This lets you enable/disable the match predictions, and gives you finer control over the feature*
- Predictions become visible once the map ban is complete, if any.
> `/match predictions <#channel> (enable|disable|on|off)`
> 
> *Enable or disable predictions*
> 
> `/match predictions <#channel> (team1|team2) <emoji>`
> 
> *Sets the emoji to be used for voting on said team*
> 
> `/match predictions <#channel> reset`
> 
> *Resets the entire predictions config. This deletes all votes, sets the emojis to the defaults (numbers 1 and 2), and disables the feature*

## The `/match casters` subcommand

*This lets you add and remove casters from a match*
> `/match casters <#channel> add <"name"> <lang> <url>`
> 
> *Adds a caster to a channel*
> - The "lang" language parameter accepts a two-characters long country code. Only the ones that are built-in are supported. Currently recognized codes are UK, US, DE, NL, FR, CN, RU, ES, JP, and AU.
> - You will be asked to confirm before the caster is added.
> 
> `/match casters <#channel> remove <index>`
> 
> *Removes a caster from a match by index*
> - The index starts at 1, not 0. You can view the index with the `/match casters <#channel> list` command.
> - You will be asked to confirm before the caster is removed.
> 
> `/match casters <#channel> set_delay <delay>`
> 
> *Sets the streaming delay in minutes that casters will have*

## The `/calendar` command

*Is used to create a calendar keeping track of all matches*
> `/calendar add <category_id>`
> 
> *Generates a calendar for all matches within a channel category*
> - A category is a collapsable list of channels. Enable Developer mode in your Discord's settings, then right-click on that category name, and copy its ID.
> - Calendars are maintained in a single channel. You can view or set it with `/calendar channel [#channel]`
> - The calendar is automatically updated every 15 minutes
> - To view all listed categories, use `/calendar list`
> - To remove a category, use `/calendar delete <category_id>`

## Permissions
> - Discord Administrators can always use the bot.
> - When `/match reveal`ing a channel permissions for that channel are updated.
> - If the map ban is on-going the `Team1` and `Team2` roles will be able to speak in that channel.
> - If a role's name ends with a `*`, for instance `Team1*`, it will hlook for a role witout it, `Team1` in this case. If it finds it, it will display that role in all embeds. However, the `Team1*` role will be given permission to talk. By giving this role to team reps of said team, only they will be able to ban.
> - Users with Manage Messages can always ban.
> - Users with Manage Messages can type something along the lines of "undo", "revert", etc. during a ban phase and it will undo the last choice.

## TL;DR
> Create a match channel and enable everything;<br>
> `/match create #my-match "epic match" "" @Team1 @Team2 True`<br>
> Show the channel;<br>
> `/match reveal #my-match`<br>
> Set the start time;<br>
> `/match set #my-match date 8 feb 19:30`<br>
> Set the result;<br>
> `/match set #my-match result 5 - 0`

# Common issues

## The information is not properly updated in the match channel itself
Some more complex operations do not always trigger an edit of the message. By using the `/match reveal <channel>` command you can force it to update existing messages and resend any messages that went missing.

## Throughout the map ban some messages are not deleted
This is a known issue. I assume it is simply because we are hitting rate limits whilst also performing regular blocking calls. Just manually delete the unwanted messages for now.

## Sometimes the ban progress image is incorrect and shows another game's ban progress instead
This is a known issue. It can happen when two people in two different channels ban at the same time. It is purely a visual glitch. Anyone with Manage Messages permissions can undo the most recent ban by typing "undo" in the channel, or an Admin could delete the message and run the `/match reveal` command again.

## configparser.MissingSectionHeaderError: File contains no section headers
```py
configparser.MissingSectionHeaderError: File contains no section headers.
file: 'config.ini', line: 1
'\ufeff[bot]\n'
```
The `config.ini` is saved with the wrong encoding. The encoding should be `UTF-8`, but it is `UTF-8-BOM`. Most likely you have made changes using **Notepad**, which automatically changes the encoding to have BOM. It is recommended to use [Notepad++](https://notepad-plus-plus.org/downloads/) instead. It will also allow you to change the encoding.

![Changing the encoding with Notepad++](https://i.stack.imgur.com/Yvpyp.png)

## ModuleNotFoundError: No module named '...'
This error simply tells you that certain modules are not recognized. Make sure you've installed all required modules by running `pip install -r requirements.txt` from inside the `Seasonal` directory.

## wkhtmltoimage exited with non-zero code
![wkhtmltoimage exited with non-zero code](https://media.discordapp.net/attachments/729998051288285256/1023281553205370960/unknown.png)

This error means something unexpected happened with wkhtmltoimage, which is responsible for rendering out the map vote image you see. Often this is caused by broken permissions. An easy fix is to run the bot as Administrator on Windows, or SuperUser on Linux.

# Notes
- The code is old. The code is a mess. It gets the job done, but nothing more. Good luck modifying it.
- Feel free to do whatever with the code, though would be nice if you wouldn't strip my credit entirely. Credit where credit is due.