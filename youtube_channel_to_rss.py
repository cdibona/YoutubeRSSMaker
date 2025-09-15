
#!/usr/bin/env python3
"""
YouTube Channel → RSS (with durations & details)
------------------------------------------------

Create an RSS feed for all videos on a given YouTube channel.
Accepts a channel URL (/channel/, /user/, /c/), a handle (@name), a plain channel ID, or a search string.

Requirements:
- Python 3.8+
- `requests` library
- A YouTube Data API v3 key (set YT_API_KEY or pass --api-key)

Usage:
    python youtube_channel_to_rss.py --channel "https://www.youtube.com/c/thisoldtony" --api-key YOUR_KEY --out thisoldtony.rss
    python youtube_channel_to_rss.py --channel @thisoldtony --out feed.rss  # API key read from env YT_API_KEY
    python youtube_channel_to_rss.py --channel UCxxxx... --out feed.rss

Notes:
- To avoid quota spikes, the script batches video lookups (50 per request).
- Includes: title, link, description, duration (HH:MM:SS), duration_seconds, published date, viewCount, likeCount (when available), and thumbnails.
- The RSS uses the Media RSS namespace for richer metadata.
"""
import argparse
import os
import re
import sys
import time
import html
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

load_dotenv()

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

# --- Helpers -----------------------------------------------------------------

def iso8601_duration_to_seconds(iso_dur: str) -> int:
    """Convert ISO 8601 duration (e.g., PT1H2M3S) to seconds."""
    pattern = re.compile(
        r"^P(?:(?P<years>\d+)Y)?(?:(?P<months>\d+)M)?(?:(?P<weeks>\d+)W)?(?:(?P<days>\d+)D)?"
        r"(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
    )
    m = pattern.match(iso_dur)
    if not m:
        return 0
    parts = {k: int(v) if v else 0 for k, v in m.groupdict().items()}
    total = (
        parts["weeks"] * 7 * 24 * 3600
        + parts["days"] * 24 * 3600
        + parts["hours"] * 3600
        + parts["minutes"] * 60
        + parts["seconds"]
    )
    return total

def seconds_to_hms(sec: int) -> str:
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    else:
        return f"{m:02d}:{s:02d}"

def rfc2822(dt: datetime) -> str:
    # Ensures UTC RFC 2822 format
    return dt.astimezone(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

def safe_text(x: Optional[str]) -> str:
    return html.escape(x or "", quote=False)

def pick_best_thumb(thumbs: Dict) -> Tuple[str, int, int]:
    if not thumbs:
        return ("", 0, 0)
    order = ["maxres", "standard", "high", "medium", "default"]
    for k in order:
        if k in thumbs:
            t = thumbs[k]
            return (t.get("url", ""), t.get("width", 0), t.get("height", 0))
    k, t = next(iter(thumbs.items()))
    return (t.get("url", ""), t.get("width", 0), t.get("height", 0))

# --- API Calls ----------------------------------------------------------------

def yt_get(session: requests.Session, endpoint: str, params: Dict) -> Dict:
    url = f"{YOUTUBE_API_BASE}/{endpoint}"
    r = session.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def resolve_channel_id(session: requests.Session, api_key: str, channel: str) -> Tuple[str, Dict]:
    """Resolve input to a canonical channelId, plus channel metadata. Returns (channel_id, channel_resource)."""
    channel = channel.strip()

    # Full URL?
    m = re.match(r"^https?://(www\.)?youtube\.com/(.+)$", channel, re.IGNORECASE)
    if m:
        path = m.group(2)
        # /channel/UCxxxx...
        m2 = re.match(r"^channel/([A-Za-z0-9_\-]{10,})", path)
        if m2:
            channel_id = m2.group(1)
            data = yt_get(session, "channels", {
                "part": "snippet,contentDetails,statistics",
                "id": channel_id,
                "key": api_key
            })
            items = data.get("items", [])
            if not items:
                raise ValueError("Channel not found by ID.")
            return channel_id, items[0]

        # /@handle
        m3 = re.match(r"^@([A-Za-z0-9_\.]+)", path)
        if m3:
            handle = "@" + m3.group(1)
            data = yt_get(session, "channels", {
                "part": "snippet,contentDetails,statistics",
                "forHandle": handle,
                "key": api_key
            })
            items = data.get("items", [])
            if not items:
                raise ValueError(f"Channel not found for handle {handle}.")
            return items[0]["id"], items[0]

        # /user/USERNAME  (legacy)
        m4 = re.match(r"^user/([^/?#]+)", path)
        if m4:
            username = m4.group(1)
            data = yt_get(session, "channels", {
                "part": "snippet,contentDetails,statistics",
                "forUsername": username,
                "key": api_key
            })
            items = data.get("items", [])
            if not items:
                raise ValueError(f"Channel not found for username {username}.")
            return items[0]["id"], items[0]

        # /c/CUSTOM  → use search
        m5 = re.match(r"^c/([^/?#]+)", path)
        if m5:
            custom = m5.group(1)
            data = yt_get(session, "search", {
                "part": "snippet",
                "q": custom,
                "type": "channel",
                "maxResults": 1,
                "key": api_key
            })
            items = data.get("items", [])
            if not items:
                raise ValueError(f"Channel not found for custom path {custom}.")
            channel_id = items[0]["snippet"]["channelId"]
            data2 = yt_get(session, "channels", {
                "part": "snippet,contentDetails,statistics",
                "id": channel_id,
                "key": api_key
            })
            return channel_id, data2["items"][0]

    # @handle
    if channel.startswith("@"):
        data = yt_get(session, "channels", {
            "part": "snippet,contentDetails,statistics",
            "forHandle": channel,
            "key": api_key
        })
        items = data.get("items", [])
        if not items:
            raise ValueError(f"Channel not found for handle {channel}.")
        return items[0]["id"], items[0]

    # UC... channel ID?
    if re.match(r"^UC[A-Za-z0-9_\-]{20,}$", channel):
        data = yt_get(session, "channels", {
            "part": "snippet,contentDetails,statistics",
            "id": channel,
            "key": api_key
        })
        items = data.get("items", [])
        if not items:
            raise ValueError("Channel not found by ID.")
        return channel, items[0]

    # Otherwise: treat as search query
    data = yt_get(session, "search", {
        "part": "snippet",
        "q": channel,
        "type": "channel",
        "maxResults": 1,
        "key": api_key
    })
    items = data.get("items", [])
    if not items:
        raise ValueError(f"No channel results for query '{channel}'.")
    channel_id = items[0]["snippet"]["channelId"]
    data2 = yt_get(session, "channels", {
        "part": "snippet,contentDetails,statistics",
        "id": channel_id,
        "key": api_key
    })
    return channel_id, data2["items"][0]

def get_uploads_playlist_id(channel_resource: Dict) -> str:
    try:
        return channel_resource["contentDetails"]["relatedPlaylists"]["uploads"]
    except KeyError:
        raise ValueError("Could not find uploads playlist for this channel.")

def fetch_all_playlist_video_ids(session: requests.Session, api_key: str, playlist_id: str) -> List[str]:
    video_ids = []
    page_token = None
    while True:
        data = yt_get(session, "playlistItems", {
            "part": "contentDetails",
            "playlistId": playlist_id,
            "maxResults": 50,
            "pageToken": page_token or "",
            "key": api_key
        })
        for item in data.get("items", []):
            vid = item["contentDetails"]["videoId"]
            video_ids.append(vid)
        page_token = data.get("nextPageToken")
        if not page_token:
            break
        time.sleep(0.05)
    return video_ids

def chunked(seq: List[str], n: int) -> List[List[str]]:
    return [seq[i:i+n] for i in range(0, len(seq), n)]

def fetch_video_details(session: requests.Session, api_key: str, video_ids: List[str]) -> List[Dict]:
    videos = []
    for chunk in chunked(video_ids, 50):
        data = yt_get(session, "videos", {
            "part": "snippet,contentDetails,statistics",
            "id": ",".join(chunk),
            "maxResults": 50,
            "key": api_key
        })
        videos.extend(data.get("items", []))
        time.sleep(0.05)
    videos.sort(key=lambda v: v["snippet"].get("publishedAt", ""))
    return videos

# --- RSS generation -----------------------------------------------------------

def build_rss(channel: Dict, videos: List[Dict], channel_url: Optional[str]=None) -> str:
    ch_snip = channel["snippet"]
    ch_stats = channel.get("statistics", {})
    title = ch_snip.get("title", "YouTube Channel")
    desc = ch_snip.get("description", "")
    published_at = ch_snip.get("publishedAt", None)
    ch_link = channel_url or f"https://www.youtube.com/channel/{channel['id']}"
    last_build = datetime.now(timezone.utc)

    rss = []
    rss.append('<?xml version="1.0" encoding="UTF-8"?>')
    rss.append('<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">')
    rss.append("<channel>")
    rss.append(f"<title>{safe_text(title)}</title>")
    rss.append(f"<link>{safe_text(ch_link)}</link>")
    rss.append(f"<description>{safe_text(desc)}</description>")
    rss.append(f"<lastBuildDate>{rfc2822(last_build)}</lastBuildDate>")
    rss.append(f"<generator>YouTube Channel to RSS (custom)</generator>")

    if published_at:
        try:
            dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            rss.append(f"<pubDate>{rfc2822(dt)}</pubDate>")
        except Exception:
            pass

    ch_thumb = ch_snip.get("thumbnails", {})
    turl, tw, th = pick_best_thumb(ch_thumb)
    if turl:
        rss.append(f'<media:thumbnail url="{html.escape(turl, quote=True)}" width="{tw}" height="{th}"/>')

    subs = ch_stats.get("subscriberCount")
    vids = ch_stats.get("videoCount")
    views = ch_stats.get("viewCount")
    if subs or vids or views:
        extra = []
        if subs: extra.append(f"Subscribers: {subs}")
        if vids: extra.append(f"Videos: {vids}")
        if views: extra.append(f"Views: {views}")
        rss.append(f"<!-- {' | '.join(extra)} -->")

    for v in videos:
        vs = v["snippet"]
        vc = v.get("contentDetails", {})
        vstat = v.get("statistics", {})
        vid = v["id"]
        vtitle = vs.get("title", "Untitled")
        vdesc = vs.get("description", "")
        vurl = f"https://www.youtube.com/watch?v={vid}"
        published = vs.get("publishedAt", None)
        dur_iso = vc.get("duration", "PT0S")
        dur_seconds = iso8601_duration_to_seconds(dur_iso)
        dur_hms = seconds_to_hms(dur_seconds)

        thumbs = vs.get("thumbnails", {})
        turl, tw, th = pick_best_thumb(thumbs)

        rss.append("<item>")
        rss.append(f"<title>{safe_text(vtitle)}</title>")
        rss.append(f"<link>{safe_text(vurl)}</link>")
        rss.append(f"<guid isPermaLink=\"false\">youtube:video:{safe_text(vid)}</guid>")
        if published:
            try:
                dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
                rss.append(f"<pubDate>{rfc2822(dt)}</pubDate>")
            except Exception:
                pass

        meta_bits = [f"Duration: {dur_hms} ({dur_seconds}s)"]
        if vstat.get("viewCount"):
            meta_bits.append(f"Views: {vstat['viewCount']}")
        if vstat.get("likeCount"):
            meta_bits.append(f"Likes: {vstat['likeCount']}")

        meta_html = "<br/>".join(html.escape(bit, quote=False) for bit in meta_bits)
        desc_html = f"{meta_html}<br/><br/>{html.escape(vdesc or '', quote=False)}"
        rss.append(f"<description>{desc_html}</description>")

        if turl:
            rss.append(f'<media:thumbnail url="{html.escape(turl, quote=True)}" width="{tw}" height="{th}"/>')
        rss.append(f'<media:content url="{html.escape(vurl, quote=True)}" medium="video" duration="{dur_seconds}"/>')

        rss.append("</item>")

    rss.append("</channel>")
    rss.append("</rss>")
    return "\n".join(rss)

# --- Main ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Create an RSS feed for a YouTube channel.")
    parser.add_argument("--channel", required=True, help="Channel URL (@handle, /channel/ID, /user/NAME, /c/NAME), channel ID, or search query")
    parser.add_argument("--api-key", default=os.environ.get("YT_API_KEY"), help="YouTube Data API v3 key (or set YT_API_KEY)")
    parser.add_argument("--out", default="-", help="Output RSS file path (default: stdout)")
    parser.add_argument("--descending", action="store_true", help="Sort newest first (default is oldest first)")
    args = parser.parse_args()

    if not args.api_key:
        print("Error: API key required. Pass --api-key or set YT_API_KEY.", file=sys.stderr)
        sys.exit(2)

    session = requests.Session()

    try:
        channel_id, channel_resource = resolve_channel_id(session, args.api_key, args.channel)
        uploads_pid = get_uploads_playlist_id(channel_resource)
        video_ids = fetch_all_playlist_video_ids(session, args.api_key, uploads_pid)
        videos = fetch_video_details(session, args.api_key, video_ids)
        if args.descending:
            videos = list(reversed(videos))
        rss_xml = build_rss(channel_resource, videos, channel_url=args.channel if args.channel.startswith("http") or args.channel.startswith("@") else None)
    except requests.HTTPError as e:
        resp_text = getattr(e, "response", None).text if getattr(e, "response", None) else ""
        print(f"HTTP error from YouTube API: {e}\nResponse: {resp_text}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.out == "-" or args.out.lower() == "stdout":
        sys.stdout.write(rss_xml)
    else:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(rss_xml)
        print(f"Wrote RSS to {args.out}")

if __name__ == "__main__":
    main()

