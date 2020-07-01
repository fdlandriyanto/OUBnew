# Copyright (C) 2019 The Raphielscape Company LLC.
#
# Licensed under the Raphielscape Public License, Version 1.c (the "License");
# you may not use this file except in compliance with the License.
# credits to @AvinashReddy3108
#
"""
This module updates the userbot based on upstream revision
"""
 
from os import remove, execle, path, environ
import asyncio
import sys
 
from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError
 
from userbot import (CMD_HELP, HEROKU_API_KEY,
                     HEROKU_APP_NAME, UPSTREAM_REPO_URL, UPSTREAM_REPO_BRANCH)
from userbot.events import register
 
requirements_path = path.join(
    path.dirname(path.dirname(path.dirname(__file__))), 'requirements.txt')
 
 
async def gen_chlog(repo, diff):
    ch_log = ''
    d_form = "%d/%m/%y"
    for c in repo.iter_commits(diff):
        ch_log += (
            f'•[{c.committed_datetime.strftime(d_form)}]: '
            f'{c.summary} <{c.author}>\n'
        )
    return ch_log
 
 
async def print_changelogs(event, ac_br, changelog):
    changelog_str = (
        f'**New UPDATE available for [{ac_br}]:\n\nCHANGELOG:**\n`{changelog}`'
    )
    if len(changelog_str) > 4096:
        await event.edit("`Changelog is too big, view the file to see it.`")
        file = open("output.txt", "w+")
        file.write(changelog_str)
        file.close()
        await event.client.send_file(
            event.chat_id,
            "output.txt",
            reply_to=event.id,
        )
        remove("output.txt")
    else:
        await event.client.send_message(
            event.chat_id,
            changelog_str,
            reply_to=event.id,
        )
    return True
 
 
async def update_requirements():
    reqs = str(requirements_path)
    try:
        process = await asyncio.create_subprocess_shell(
            ' '.join([sys.executable, "-m", "pip", "install", "-r", reqs]),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE)
        await process.communicate()
        return process.returncode
    except Exception as e:
        return repr(e)
 
 
async def deploy(event, repo, ups_rem, ac_br, txt):
    if HEROKU_API_KEY is not None:
        import heroku3
        heroku = heroku3.from_key(HEROKU_API_KEY)
        heroku_app = None
        heroku_applications = heroku.apps()
        if HEROKU_APP_NAME is None:
            await event.edit(
                '`[HEROKU]`\n`Please set up the` **HEROKU_APP_NAME** `variable'
                ' to be able to deploy your userbot...`'
            )
            repo.__del__()
            return
        for app in heroku_applications:
            if app.name == HEROKU_APP_NAME:
                heroku_app = app
                break
        if heroku_app is None:
            await event.edit(
                f'{txt}\n'
                '`Invalid Heroku credentials for deploying userbot dyno.`'
            )
            return repo.__del__()
        await event.edit('`[HEROKU]`'
                         '\n`Userbot dyno build in progress, please wait...`'
                         )
        ups_rem.fetch(ac_br)
        repo.git.reset("--hard", "FETCH_HEAD")
        heroku_git_url = heroku_app.git_url.replace(
            "https://", "https://api:" + HEROKU_API_KEY + "@")
        if "heroku" in repo.remotes:
            remote = repo.remote("heroku")
            remote.set_url(heroku_git_url)
        else:
            remote = repo.create_remote("heroku", heroku_git_url)
        try:
            remote.push(refspec="HEAD:refs/heads/sql-extended", force=True)
        except Exception as error:
            await event.edit(f'{txt}\n`Here is the error log:\n{error}`')
            return repo.__del__()
        build = app.builds(order_by='created_at', sort='desc')[0]
        if build.status == "failed":
            await event.edit('`Build failed!\n'
                             'Cancelled or there were some errors...`')
            await asyncio.sleep(5)
            return await event.delete()
        else:
            await event.edit('`Successfully deployed!\n'
                             'Restarting, please wait...`')
    else:
        await event.edit('`[HEROKU]`\n'
                         '`Please set up`  **HEROKU_API_KEY**  `variable...`'
                         )
    return
 
 
async def update(event, repo, ups_rem, ac_br):
    try:
        ups_rem.pull(ac_br)
    except GitCommandError:
        repo.git.reset("--hard", "FETCH_HEAD")
    await update_requirements()
    await event.edit('`Successfully Updated!\n'
                     'Bot is restarting... Wait for a second!`')
    # Spin a new instance of bot
    args = [sys.executable, "-m", "userbot"]
    execle(sys.executable, *args, environ)
    return
 
 
@register(outgoing=True, pattern="^.update( now| deploy|$)")
async def upstream(event):
    "For .update command, check if the bot is up to date, update if specified"
    await event.edit("`Getting information....`")
    conf = event.pattern_match.group(1).strip()
    off_repo = UPSTREAM_REPO_URL
    force_update = False
    try:
        txt = "`Oops.. Updater cannot continue due to "
        txt += "some problems occured`\n\n**LOGTRACE:**\n"
        repo = Repo()
    except NoSuchPathError as error:
        await event.edit(f'{txt}\n`directory {error} is not found`')
        return repo.__del__()
    except GitCommandError as error:
        await event.edit(f'{txt}\n`Early failure! {error}`')
        return repo.__del__()
    except InvalidGitRepositoryError as error:
        if conf is None:
            return await event.edit(
                f"`Unfortunately, the directory {error} "
                "does not seem to be a git repository.\n"
                "But we can fix that by force updating the userbot using "
                ".update now.`"
            )
        repo = Repo.init()
        origin = repo.create_remote('upstream', off_repo)
        origin.fetch()
        force_update = True
        repo.create_head('sql-extended', origin.refs.sql-extended)
        repo.heads.sql-extended.set_tracking_branch(origin.refs.sql-extended)
        repo.heads.sql-extended.checkout(True)

    ac_br = repo.active_branch.name
    if ac_br != UPSTREAM_REPO_BRANCH:
        await event.edit(
            '**[UPDATER]:**\n'
            f'`Looks like you are using your own custom branch ({ac_br}). '
            'in that case, Updater is unable to identify '
            'which branch is to be merged. '
            'please checkout to any official branch`')
        return repo.__del__()
    try:
        repo.create_remote('upstream', off_repo)
    except BaseException:
        pass

    ups_rem = repo.remote('upstream')
    ups_rem.fetch(ac_br)

    changelog = await gen_chlog(repo, f'HEAD..upstream/{ac_br}')
    """ - Special case for deploy - """
    if conf == "deploy":
        await event.edit('`Deploying userbot, please wait....`')
        await deploy(event, repo, ups_rem, ac_br, txt)
        return

    if changelog == '' and not force_update:
        await event.edit(
            '\n`Your USERBOT is`  **up-to-date**  `with`  '
            f'**{UPSTREAM_REPO_BRANCH}**\n')
        return repo.__del__()

    if conf == '' and not force_update:
        await print_changelogs(event, ac_br, changelog)
        await event.delete()
        return await event.respond(
            '`do ".update now or .update deploy" to update.`')

    if force_update:
        await event.edit(
            '`Force-Syncing to latest stable userbot code, please wait...`')
    if conf == "now":
        await event.edit('`Updating userbot, please wait....`')
        await update(event, repo, ups_rem, ac_br)
    return
 
 
CMD_HELP.update({
    'update':
    ">`.update`"
    "\nUsage: Checks if the main userbot repository has any updates "
    "and shows a changelog if so."
    "\n\n>`.update now`"
    "\nUsage: Update your userbot, "
    "if there are any updates in your userbot repository."
    "\n\n>`.update deploy`"
    "\nUsage: Deploy your userbot"
    "\nThis will triggered deploy always, even no updates."
})
 