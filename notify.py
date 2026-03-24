"""Shiny notification module — alerts when a shiny is detected.

Supports multiple notification methods:
  - ntfy.sh: Free push notifications to your phone (no account needed)
  - macOS: Native notification center + sound
  - Discord: Webhook message to a channel

Setup:
  ntfy:    Set NTFY_TOPIC env var (e.g. "pokebots-austin")
           Install ntfy app on phone, subscribe to same topic
  Discord: Set DISCORD_WEBHOOK env var to your webhook URL
  macOS:   Always enabled (sound + notification center)

Usage:
  import notify
  notify.shiny_found("Bulbasaur", resets=5312, runtime="68:27:31")
"""

import os
import subprocess
import urllib.request
import json

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh")
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")
IMESSAGE_TO = os.environ.get("IMESSAGE_TO", "")  # set via: export IMESSAGE_TO="+18041234567"


def shiny_found(pokemon="Pokemon", resets=0, runtime=""):
    """Send notifications that a shiny was found."""
    title = f"Shiny {pokemon} Found!"
    body = f"After {resets} resets ({runtime})"
    print(f"\n{'='*50}")
    print(f"  {title}")
    print(f"  {body}")
    print(f"{'='*50}\n")

    _notify_macos(title, body)
    _notify_imessage(title, body)
    _notify_ntfy(title, body)
    _notify_discord(title, body, pokemon, resets, runtime)


def _notify_macos(title, body):
    """macOS notification center + alert sound."""
    try:
        # Play alert sound (loud, repeating)
        subprocess.Popen(
            ["afplay", "/System/Library/Sounds/Glass.aiff"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        # Notification center
        script = f'display notification "{body}" with title "{title}" sound name "Glass"'
        subprocess.run(
            ["osascript", "-e", script],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=5,
        )
        # Also use say for audible alert
        subprocess.Popen(
            ["say", f"Shiny detected!"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        print(f"macOS notification failed: {e}")


def _notify_imessage(title, body):
    """Send an iMessage to yourself via macOS Messages app."""
    if not IMESSAGE_TO:
        return
    message = f"{title}\n{body}"
    script = f'''
    tell application "Messages"
        set targetService to 1st account whose service type = iMessage
        set targetBuddy to participant "{IMESSAGE_TO}" of targetService
        send "{message}" to targetBuddy
    end tell
    '''
    try:
        subprocess.run(
            ["osascript", "-e", script],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=15,
        )
        print(f"iMessage sent to {IMESSAGE_TO}")
    except Exception as e:
        print(f"iMessage failed: {e}")


def _notify_ntfy(title, body):
    """Send push notification via ntfy.sh (free, no account needed)."""
    if not NTFY_TOPIC:
        return
    url = f"{NTFY_SERVER}/{NTFY_TOPIC}"
    try:
        req = urllib.request.Request(
            url,
            data=body.encode(),
            headers={
                "Title": title,
                "Priority": "urgent",
                "Tags": "sparkles,pokemon",
            },
        )
        urllib.request.urlopen(req, timeout=10)
        print(f"ntfy notification sent to {NTFY_TOPIC}")
    except Exception as e:
        print(f"ntfy notification failed: {e}")


def _notify_discord(title, body, pokemon="", resets=0, runtime=""):
    """Send message to Discord via webhook."""
    if not DISCORD_WEBHOOK:
        return
    payload = {
        "content": f"**{title}**\n{body}",
        "embeds": [{
            "title": f"Shiny {pokemon}!",
            "color": 16766720,  # gold
            "fields": [
                {"name": "Resets", "value": str(resets), "inline": True},
                {"name": "Runtime", "value": runtime or "—", "inline": True},
            ],
        }],
    }
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            DISCORD_WEBHOOK,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
        print("Discord notification sent")
    except Exception as e:
        print(f"Discord notification failed: {e}")


def test():
    """Send a test notification."""
    print("Sending test notification...")
    print(f"  NTFY_TOPIC: {NTFY_TOPIC or '(not set)'}")
    print(f"  DISCORD_WEBHOOK: {'(set)' if DISCORD_WEBHOOK else '(not set)'}")
    print(f"  IMESSAGE_TO: {IMESSAGE_TO or '(not set)'}")
    shiny_found("Test Pokemon", resets=0, runtime="00:00:00")
    print("Done.")


if __name__ == "__main__":
    test()
