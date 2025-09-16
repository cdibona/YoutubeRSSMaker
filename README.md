# YouTube Channel → RSS Feed Generator

This Python script creates an **RSS feed** for any YouTube channel, including video metadata such as title, description, duration, views, likes, and thumbnails.  

It uses the [YouTube Data API v3](https://developers.google.com/youtube/v3) to fetch all videos from a channel’s **Uploads** playlist and formats them as a valid **RSS 2.0** feed with [Media RSS](https://www.rssboard.org/media-rss) extensions.

---

## ✨ Features

- Accepts:
  - Channel URLs (`/channel/UC…`, `/user/NAME`, `/c/CUSTOM`)
  - Handles (`@username`)
  - Raw channel IDs
  - Even plain search queries
- Fetches **all videos** from the channel
- Includes:
  - Video **title, link, description**
  - **Duration** (`HH:MM:SS` and seconds)
  - **Publish date**
  - **Views** and **likes** (if available)
  - **Thumbnails** (via `<media:thumbnail>`)
  - `<media:content>` entries with duration metadata
  - Optional **captions/transcripts** (manual or opt-in auto-generated) embedded in `<description>` and `<media:subtitle>`
- Channel metadata:
  - Channel title, description, publish date
  - Subscriber/video/view counts (as comments)

---

## 📦 Setup

Clone the repo:

```bash
git clone https://github.com/yourname/youtube-channel-to-rss.git
cd youtube-channel-to-rss
```

Install dependencies (from `requirements.txt`):

```bash
pip install -r requirements.txt
```

Copy the environment template and add your API key:

```bash
cp .env.template .env
# then edit .env and set YT_API_KEY
```

---

## 🔑 API Key Setup

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (if needed).
3. Enable the **YouTube Data API v3**.
4. Create an **API key**.
5. Make it available to the script:
   - Copy `.env.template` to `.env` and set `YT_API_KEY=YOUR_API_KEY`
   - Or export it as an environment variable:
     ```bash
     export YT_API_KEY="YOUR_API_KEY"
     ```
   - Or pass it with `--api-key`.

---

## 🚀 Usage

```bash
python youtube_channel_to_rss.py --channel <CHANNEL> [options]
```

### Examples

```bash
# Using a custom URL
python youtube_channel_to_rss.py --channel "https://www.youtube.com/c/thisoldtony" --api-key YOUR_KEY --out thisoldtony.rss

# Using a handle with API key from .env
python youtube_channel_to_rss.py --channel @thisoldtony --out feed.rss

# Using a handle with an exported env var
export YT_API_KEY=YOUR_KEY
python youtube_channel_to_rss.py --channel @thisoldtony --out feed.rss

# Using a raw channel ID (newest videos come first by default)
python youtube_channel_to_rss.py --channel UCxxxxxxx --out latest.rss

# Flipping the feed to oldest-first order
python youtube_channel_to_rss.py --channel UCxxxxxxx --oldest-first --out archive.rss

# Including English captions in the feed
python youtube_channel_to_rss.py --channel UCxxxxxxx --include-captions --caption-language en --out captions.rss

# Including captions with auto-generated fallback
python youtube_channel_to_rss.py --channel UCxxxxxxx --include-captions --allow-generated-captions --out captions.rss
```

### Arguments

| Option               | Description                                                                 |
|----------------------|-----------------------------------------------------------------------------|
| `--channel`          | Channel URL, @handle, /channel/ID, /user/NAME, /c/NAME, or search query     |
| `--api-key`          | YouTube API key (or set `YT_API_KEY` env var)                               |
| `--out`              | Output file path (default: `stdout`)                                        |
| `--oldest-first`     | Sort the feed so the oldest uploads appear first (default is newest-first)  |
| `--include-captions` | Fetch and embed captions/transcripts for each video                         |
| `--caption-language` | Preferred caption language code (default: `en`; used with `--include-captions`) |
| `--allow-generated-captions` | Permit falling back to YouTube's auto-generated captions (used with `--include-captions`) |

---

## 📄 Output

Generates a valid RSS 2.0 XML feed:

```xml
<item>
  <title>How to Make Stuff</title>
  <link>https://www.youtube.com/watch?v=abcd1234</link>
  <guid isPermaLink="false">youtube:video:abcd1234</guid>
  <pubDate>Mon, 01 Jan 2024 12:00:00 +0000</pubDate>
  <description>
    Duration: 12:34 (754s)<br/>
    Views: 12345<br/>
    Likes: 678<br/><br/>
    Video description here...
  </description>
  <media:thumbnail url="..." width="1280" height="720"/>
  <media:content url="https://www.youtube.com/watch?v=abcd1234" medium="video" duration="754"/>
</item>
```

---

## ⚠️ Notes

- **Quota limits:** Fetching every video can consume API quota quickly, especially for large channels.
- **Durations:** Extracted from ISO 8601 (e.g., `PT1H2M3S → 01:02:03`).
- **Feed readers:** Some may ignore extended `<media:*>` tags, but major ones (Tiny Tiny RSS, FreshRSS, etc.) support them.

---

## 🛠 License

MIT License – feel free to use, modify, and share.

