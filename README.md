# YouTube RSS Maker

Modern YouTube RSS feed generator with **incremental updates** and **multi-user support**. Create RSS feeds for any YouTube channel with intelligent storage that only fetches new videos since your last check.

This system uses the [YouTube Data API v3](https://developers.google.com/youtube/v3) to fetch videos and stores them in SQLite for efficient incremental updates, supporting multiple users with their own API keys.

---

## ✨ Features

### 🚀 **Modern Incremental System (Default)**
- **Incremental Updates**: Only fetches new videos since last check
- **Multi-User Support**: Different users can manage feeds with their own API keys
- **SQLite Storage**: Fast, persistent storage of video metadata
- **Automatic Deduplication**: Prevents duplicate video entries
- **Feed Management**: Add, remove, and list feeds with simple commands
- **Reduced API Usage**: Dramatically lower YouTube API quota consumption

### 📺 **Rich Video Metadata**
- **Channel Support**: URLs (`/channel/UC…`, `/user/NAME`, `/c/CUSTOM`), handles (`@username`), IDs, search queries
- **Complete Video Data**: Title, link, description, duration (`HH:MM:SS` and seconds), publish date
- **Statistics**: Views and likes (when available)
- **Media Elements**: Thumbnails (`<media:thumbnail>`), content metadata (`<media:content>`)
- **Optional Captions**: Manual or auto-generated transcripts in `<description>` and `<media:subtitle>`
- **Channel Metadata**: Title, description, subscriber/video/view counts

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

### **Quick Start (Recommended)**

```bash
# 1. Add your first feed
python youtube_rss.py add @TechnologyConnections tech-connections.xml --user alice --api-key YOUR_KEY

# 2. Update all feeds (only fetches new videos)
python youtube_rss.py update

# 3. List your feeds
python youtube_rss.py list
```

### **Common Operations**

```bash
# Add feeds for different users
python youtube_rss.py add @ThisOldTony this-old-tony.xml --user alice --api-key ALICE_KEY
python youtube_rss.py add @NileRed nilered.xml --user bob --api-key BOB_KEY

# Update all feeds using their stored API keys
python youtube_rss.py update

# List feeds for a specific user
python youtube_rss.py list --user alice

# Remove a feed
python youtube_rss.py remove @TechnologyConnections --user alice

# View feed statistics
python youtube_rss.py stats

# Clean up old videos
python youtube_rss.py cleanup 365
```

### **Advanced Usage**

```bash
# Add feed with captions and custom settings
python youtube_rss.py add @VeritasiumVideos veritasium.xml \
  --include-captions --caption-language en --oldest-first

# Continuous updates (runs forever, checking every hour)
python youtube_rss.py update --loop --interval 3600

# Single channel generation (legacy mode)
python youtube_rss.py channel @TechnologyConnections --out single-feed.xml
```

### Commands Reference

| Command | Description |
|---------|-------------|
| `add CHANNEL OUTPUT` | Add new feed with user and API key |
| `update` | Update all feeds incrementally |
| `list` | Show all feeds or filter by user |
| `remove CHANNEL` | Remove a feed (with user permission check) |
| `stats` | Display feed and video statistics |
| `cleanup DAYS` | Remove videos older than N days |
| `channel CHANNEL` | Single-channel mode (legacy) |

| Common Options | Description |
|----------------|-------------|
| `--user USER` | User ID for feed ownership (default: DefaultUser) |
| `--api-key KEY` | YouTube API key for this operation |
| `--db-path PATH` | Custom database location |
| `--include-captions` | Fetch and embed video captions |
| `--oldest-first` | Sort videos oldest-first instead of newest-first |

---

## 📄 Output

---

## 🔁 Migration from Legacy System

If you're upgrading from the old `update_feeds.py` system, you can migrate easily:

### **Option 1: Use New System (Recommended)**

```bash
# Add your existing feeds to the new system
python youtube_rss.py add @thisoldtony thisoldtony.xml --api-key YOUR_KEY
python youtube_rss.py add @nilered nilered.xml --api-key YOUR_KEY
python youtube_rss.py add @technologyconnections technology-connections.xml --api-key YOUR_KEY

# Then use the new update command
python youtube_rss.py update
```

### **Option 2: Keep Using .env Config**

```bash
# Use legacy .env CHANNELS configuration
python youtube_rss.py update --use-env-config
```

The `.env` configuration still works:
```env
YT_API_KEY=your-key
OUTPUT_DIRECTORY=./feeds
CHANNELS='[
  {"channel": "@ThisOldTony", "output": "thisoldtony.xml"},
  {"channel": "@NileRed", "output": "nilered.xml"}
]'
```


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

## 🎯 **How the New System Works**

### **First Run vs. Incremental Updates**

```bash
# First time adding a feed - fetches ALL videos
python youtube_rss.py add @TechnologyConnections tech.xml --api-key KEY
# INFO: First run for Technology Connections - fetching all videos
# INFO: Stored 219 videos for Technology Connections

# Subsequent updates - only processes NEW videos
python youtube_rss.py update
# INFO: Incremental update for Technology Connections (last update: 2024-01-15 10:30:00)
# INFO: Found 2 new videos for Technology Connections (total: 221)
```

### **Multi-User Support**

```bash
# Alice adds feeds with her API key
python youtube_rss.py add @channel1 feed1.xml --user alice --api-key ALICE_KEY
python youtube_rss.py add @channel2 feed2.xml --user alice --api-key ALICE_KEY

# Bob adds feeds with his API key
python youtube_rss.py add @channel3 feed3.xml --user bob --api-key BOB_KEY

# Updates use each feed's stored API key automatically
python youtube_rss.py update
# Uses ALICE_KEY for alice's feeds, BOB_KEY for bob's feeds

# Users can only manage their own feeds
python youtube_rss.py remove @channel1 --user alice  # ✅ Works
python youtube_rss.py remove @channel1 --user bob    # ❌ Permission denied
```

### **Performance Benefits**

- **Faster Updates**: Only processes new videos, not entire channel history
- **Lower API Usage**: Dramatically reduced YouTube API quota consumption
- **Offline RSS Generation**: Create feeds from stored data without API calls
- **Automatic Deduplication**: No duplicate videos even if run multiple times

---

## ⚠️ Notes

- **Quota limits:** Fetching every video can consume API quota quickly, especially for large channels.
- **Durations:** Extracted from ISO 8601 (e.g., `PT1H2M3S → 01:02:03`).
- **Feed readers:** Some may ignore extended `<media:*>` tags, but major ones (Tiny Tiny RSS, FreshRSS, etc.) support them.

---

## 🛠 License

MIT License – feel free to use, modify, and share.

