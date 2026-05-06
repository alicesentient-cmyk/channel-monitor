#!/usr/bin/env python3
"""Update channel-monitor data from channel_data and push to GitHub Pages."""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
CHANNEL_DATA_DIR = HOME / "channel_data"
MONITOR_DIR = HOME / "channel-monitor"
CHANNELS = ["xhqcankao", "zaihuapd"]


def load_channel_data(channel: str) -> dict:
    path = CHANNEL_DATA_DIR / f"{channel}.json"
    if not path.exists():
        return {"messages": [], "last_update": ""}
    with open(path) as f:
        return json.load(f)


def build_data_json() -> dict:
    """Build combined data.json from all channel data."""
    all_messages = []
    for channel in CHANNELS:
        data = load_channel_data(channel)
        for msg in data.get("messages", []):
            # Normalize message format
            entry = {
                "id": f"{channel}_{msg.get('id', '')}",
                "channel": channel,
                "text": msg.get("text", ""),
                "clean_text": msg.get("clean_text", msg.get("text", "")),
                "datetime": msg.get("datetime", ""),
                "views": msg.get("views", "0"),
                "source_links": msg.get("source_links", []),
                "url": f"https://t.me/s/{channel}#{msg.get('id', '')}",
                "scraped_at": msg.get("scraped_at", datetime.now(timezone.utc).isoformat()),
            }
            all_messages.append(entry)

    # Sort by datetime descending
    all_messages.sort(key=lambda m: m.get("datetime", ""), reverse=True)
    return {"messages": all_messages, "updated_at": datetime.now(timezone.utc).isoformat()}


def save_monitor_files(data: dict):
    """Save combined data.json and per-channel files."""
    # Save combined data
    with open(MONITOR_DIR / "data.json", "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Save per-channel files
    for channel in CHANNELS:
        channel_data = load_channel_data(channel)
        with open(MONITOR_DIR / f"{channel}.json", "w") as f:
            json.dump(channel_data, f, ensure_ascii=False, indent=2)

    print(f"✅ Data updated: {len(data['messages'])} total messages")


def git_push():
    """Commit and push changes to GitHub."""
    os.chdir(MONITOR_DIR)
    result = subprocess.run(["git", "add", "-A"], capture_output=True, text=True)
    result = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True, text=True)
    if result.returncode == 0:
        print("😴 No changes to commit")
        return True

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subprocess.run(["git", "commit", "-m", f"Update channel data ({ts})"], capture_output=True, text=True)
    result = subprocess.run(["git", "push", "origin", "main"], capture_output=True, text=True)
    if result.returncode == 0:
        print("✅ Pushed to GitHub Pages")
        return True
    else:
        print(f"⚠️ Git push failed: {result.stderr}")
        print("Trying gh auth setup-git...")
        subprocess.run(["gh", "auth", "setup-git"], capture_output=True, text=True)
        result = subprocess.run(["git", "push", "origin", "main"], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Pushed after auth setup")
            return True
        else:
            print(f"❌ Push failed: {result.stderr}")
            return False


if __name__ == "__main__":
    print("🚀 更新频道数据...")
    data = build_data_json()
    save_monitor_files(data)
    success = git_push()
    sys.exit(0 if success else 1)
