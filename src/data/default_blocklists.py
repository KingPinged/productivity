"""
Pre-made block lists for common distracting apps and websites.
"""

BLOCKED_APPS = {
    "games": [
        # Game Launchers
        "steam.exe",
        "steamwebhelper.exe",
        "epicgameslauncher.exe",
        "easyanticheat.exe",
        "gog galaxy.exe",
        "galaxyclient.exe",
        "origin.exe",
        "ea.exe",
        "eadesktop.exe",
        "battle.net.exe",
        "riotclientservices.exe",
        "riotclientux.exe",
        "leagueclient.exe",
        "vanguard.exe",

        # Popular Games
        "valorant.exe",
        "valorant-win64-shipping.exe",
        "minecraft.exe",
        "minecraftlauncher.exe",
        "javaw.exe",
        "csgo.exe",
        "cs2.exe",
        "dota2.exe",
        "fortnite.exe",
        "fortniteclient-win64-shipping.exe",
        "gta5.exe",
        "gtavlauncher.exe",
        "rdr2.exe",
        "eldenring.exe",
        "baldursgate3.exe",
        "bg3.exe",
        "overwatch.exe",
        "hearthstone.exe",
        "wowclassic.exe",
        "wow.exe",
        "apex_legends.exe",
        "r5apex.exe",
        "pubg.exe",
        "tslgame.exe",
        "robloxplayerbeta.exe",
        "robloxstudiobeta.exe",
    ],

    "social_media": [
        "discord.exe",
        "discordptb.exe",
        "discordcanary.exe",
        "slack.exe",
        "telegram.exe",
        "whatsapp.exe",
        "signal.exe",
        "messenger.exe",
        "teams.exe",
        "zoom.exe",
        "skype.exe",
        "viber.exe",
        "line.exe",
        "wechat.exe",
        "guilded.exe",
    ],

    "entertainment": [
        "spotify.exe",
        "netflix.exe",
        "amazon music.exe",
        "vlc.exe",
        "potplayer.exe",
        "potplayer64.exe",
        "mpc-hc.exe",
        "mpc-hc64.exe",
        "mpc-be.exe",
        "mpc-be64.exe",
        "obs64.exe",
        "obs32.exe",
        "streamlabs obs.exe",
    ],
}

BLOCKED_WEBSITES = {
    "social_media": [
        "facebook.com",
        "www.facebook.com",
        "m.facebook.com",
        "twitter.com",
        "www.twitter.com",
        "x.com",
        "www.x.com",
        "instagram.com",
        "www.instagram.com",
        "tiktok.com",
        "www.tiktok.com",
        "snapchat.com",
        "www.snapchat.com",
        "linkedin.com",
        "www.linkedin.com",
        "reddit.com",
        "www.reddit.com",
        "old.reddit.com",
        "tumblr.com",
        "www.tumblr.com",
        "pinterest.com",
        "www.pinterest.com",
        "threads.net",
        "www.threads.net",
        "bsky.app",
        "quora.com",
        "www.quora.com",
    ],

    "video_streaming": [
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "youtu.be",
        "music.youtube.com",
        "netflix.com",
        "www.netflix.com",
        "hulu.com",
        "www.hulu.com",
        "disneyplus.com",
        "www.disneyplus.com",
        "hbomax.com",
        "www.hbomax.com",
        "max.com",
        "www.max.com",
        "primevideo.com",
        "www.primevideo.com",
        "twitch.tv",
        "www.twitch.tv",
        "vimeo.com",
        "www.vimeo.com",
        "dailymotion.com",
        "www.dailymotion.com",
        "crunchyroll.com",
        "www.crunchyroll.com",
    ],

    "gaming": [
        "steampowered.com",
        "www.steampowered.com",
        "store.steampowered.com",
        "steamcommunity.com",
        "epicgames.com",
        "www.epicgames.com",
        "store.epicgames.com",
        "gog.com",
        "www.gog.com",
        "itch.io",
        "roblox.com",
        "www.roblox.com",
        "minecraft.net",
        "www.minecraft.net",
        "ea.com",
        "www.ea.com",
        "ubisoft.com",
        "www.ubisoft.com",
        "blizzard.com",
        "www.blizzard.com",
        "battle.net",
        "riotgames.com",
        "www.riotgames.com",
    ],

    "messaging": [
        "discord.com",
        "www.discord.com",
        "discordapp.com",
        "slack.com",
        "www.slack.com",
        "web.whatsapp.com",
        "web.telegram.org",
        "messenger.com",
        "www.messenger.com",
    ],

    "news_entertainment": [
        "buzzfeed.com",
        "www.buzzfeed.com",
        "9gag.com",
        "www.9gag.com",
        "imgur.com",
        "www.imgur.com",
        "giphy.com",
        "www.giphy.com",
        "boredpanda.com",
        "www.boredpanda.com",
        "knowyourmeme.com",
        "www.knowyourmeme.com",
    ],
}


def get_all_blocked_apps(enabled_categories: list[str]) -> set[str]:
    """Get all blocked app names for enabled categories."""
    apps = set()
    for category in enabled_categories:
        if category in BLOCKED_APPS:
            apps.update(app.lower() for app in BLOCKED_APPS[category])
    return apps


def get_all_blocked_websites(enabled_categories: list[str]) -> set[str]:
    """Get all blocked website domains for enabled categories."""
    sites = set()
    for category in enabled_categories:
        if category in BLOCKED_WEBSITES:
            sites.update(BLOCKED_WEBSITES[category])
    return sites
