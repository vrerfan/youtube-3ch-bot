import os
import re
import json
import requests
import xml.etree.ElementTree as ET

CHANNELS = [
    "@AIFastLane-y5k",
    "@Q.TECHSTUDIOS",
    "@airyzenai",
]

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = "-5378156600"

STATE_FILE = "last_videos.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
    )
}

session = requests.Session()
session.headers.update(HEADERS)


def get_channel_id(handle):
    url = f"https://www.youtube.com/{handle}"
    response = session.get(url, timeout=30)
    response.raise_for_status()

    patterns = [
        r'"externalId"\s*:\s*"(UC[\w-]{22})"',
        r'"channelId"\s*:\s*"(UC[\w-]{22})"',
        r'<meta itemprop="identifier" content="(UC[\w-]{22})"',
    ]

    for pattern in patterns:
        match = re.search(pattern, response.text)

        if match:
            return match.group(1)

    raise RuntimeError(f"Could not find channel ID: {handle}")


def get_videos(channel_id):
    url = (
        "https://www.youtube.com/feeds/videos.xml"
        f"?channel_id={channel_id}"
    )

    response = session.get(url, timeout=30)
    response.raise_for_status()

    root = ET.fromstring(response.content)

    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "yt": "http://www.youtube.com/xml/schemas/2015",
    }

    videos = []

    for entry in root.findall("atom:entry", ns):
        video_id = entry.findtext("yt:videoId", namespaces=ns)

        if video_id:
            videos.append({
                "id": video_id,
                "url": f"https://www.youtube.com/watch?v={video_id}",
            })

    return videos


def send_video(video):
    video_id = video["id"]
    video_url = video["url"]

    thumbnail_urls = [
        f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
        f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
    ]

    last_error = None

    for thumbnail_url in thumbnail_urls:
        try:
            image_response = session.get(
                thumbnail_url,
                timeout=30,
            )
            image_response.raise_for_status()

            if len(image_response.content) < 5000:
                continue

            response = requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                data={
                    "chat_id": CHAT_ID,
                    "caption": video_url,
                },
                files={
                    "photo": (
                        f"{video_id}.jpg",
                        image_response.content,
                        "image/jpeg",
                    )
                },
                timeout=60,
            )

            result = response.json()

            if result.get("ok"):
                print(f"Sent: {video_url}")
                return

            last_error = result.get("description", "Unknown Telegram error")

        except requests.RequestException as error:
            last_error = str(error)

    raise RuntimeError(
        f"Could not send video {video_url}: {last_error}"
    )


def main():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as file:
            state = json.load(file)
    else:
        state = {}

    changed = False

    for handle in CHANNELS:
        print(f"Checking {handle}")

        channel_id = get_channel_id(handle)
        videos = get_videos(channel_id)

        if not videos:
            print(f"No videos found for {handle}")
            continue

        previous_id = state.get(handle)

        if previous_id is None:
            state[handle] = videos[0]["id"]
            changed = True
            print(f"Initialized tracking for {handle}")
            continue

        new_videos = []

        for video in videos:
            if video["id"] == previous_id:
                break

            new_videos.append(video)

        for video in reversed(new_videos):
            send_video(video)

        if new_videos:
            state[handle] = videos[0]["id"]
            changed = True

    if changed or not os.path.exists(STATE_FILE):
        with open(STATE_FILE, "w", encoding="utf-8") as file:
            json.dump(state, file, indent=2)

    print("Finished checking channels.")


if __name__ == "__main__":
    main()
