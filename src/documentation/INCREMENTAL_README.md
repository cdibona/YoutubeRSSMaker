# Incremental YouTube RSS Feed System

This enhanced version of the YouTube RSS Maker adds SQLite-based storage for efficient incremental updates. Instead of fetching all videos every time, it stores video metadata locally and only processes new videos since the last update.

## Key Features

- **SQLite Storage**: Persistent storage of channel and video metadata
- **Incremental Updates**: Only fetch new videos since last check
- **Automatic Deduplication**: Prevents duplicate video entries
- **RSS Generation from Storage**: Fast RSS generation without API calls
- **Statistics & Cleanup**: View feed stats and clean old videos

## Files Added

- `feed_storage.py` - SQLite database management
- `incremental_updater.py` - Enhanced updater with incremental logic
- `test_incremental.py` - Test script for verification
- `example_usage.py` - Usage examples

## Quick Start

### 1. Basic Usage

```bash
# Set your API key
export YT_API_KEY="your-youtube-api-key"

# Run the incremental updater (uses same .env config as original)
python incremental_updater.py

# Or specify custom settings
python incremental_updater.py --db-path my_feeds.db --output-directory ./feeds
```

### 2. First Run vs Subsequent Runs

**First Run**: Fetches all videos for each channel and stores them
```bash
python incremental_updater.py
# INFO: First run for Technology Connections - fetching all videos
# INFO: Stored 219 videos for Technology Connections
```

**Subsequent Runs**: Only processes new videos since last update
```bash
python incremental_updater.py
# INFO: Incremental update for Technology Connections (last update: 2024-01-15 10:30:00)
# INFO: Found 2 new videos for Technology Connections (total: 221)
```

### 3. View Statistics

```bash
python incremental_updater.py --stats
# Total feeds: 3
# Total videos: 450
#
# Technology Connections: 219 videos
#   Last updated: 2024-01-15T10:30:00+00:00
#   Newest video: 2024-01-14T20:15:00+00:00
```

### 4. Cleanup Old Videos

```bash
# Remove videos older than 1 year
python incremental_updater.py --cleanup-days 365
```

## Configuration

The incremental updater uses the same `.env` configuration as the original `update_feeds.py`:

```env
YT_API_KEY=your-api-key
OUTPUT_DIRECTORY=./feeds
DATABASE_PATH=feeds.db
CHANNELS='[
  {"channel": "@TechnologyConnections", "output": "tech-connections.xml"},
  {"channel": "@ThisOldTony", "output": "this-old-tony.xml"}
]'
```

### Database Path Configuration

The `DATABASE_PATH` setting controls where the SQLite database is stored:

- **Default**: `feeds.db` (in current directory)
- **Relative paths**: `./data/feeds.db` (relative to working directory)
- **Absolute paths**: `/var/lib/youtube-rss/feeds.db` (full system path)
- **Command line override**: `--db-path custom.db`

Examples:
```bash
# Use default location (feeds.db)
python incremental_updater.py

# Use custom path from .env
DATABASE_PATH=/home/user/data/youtube_feeds.db python incremental_updater.py

# Override with command line
python incremental_updater.py --db-path /tmp/test_feeds.db
```

## Database Schema

The SQLite database stores:

### Feeds Table
- `channel_id` - YouTube channel ID (primary key)
- `channel_identifier` - Original input (@handle, URL, etc.)
- `channel_title` - Channel display name
- `last_updated` - Timestamp of last update
- `last_video_count` - Number of videos at last update
- `feed_config` - JSON config (captions, etc.)

### Videos Table
- `video_id` - YouTube video ID (primary key)
- `channel_id` - Associated channel
- `title`, `description` - Video metadata
- `published_at` - Video publication date
- `duration_seconds` - Video length
- `view_count`, `like_count` - Statistics
- `thumbnail_url` - Best available thumbnail
- `captions` - Transcript text (if enabled)
- `first_seen` - When we first discovered this video

## Performance Benefits

- **Faster Updates**: Only processes new videos instead of all videos
- **Reduced API Usage**: Significantly lower YouTube API quota consumption
- **Offline RSS Generation**: Create RSS feeds from stored data without API calls
- **Historical Data**: Keeps full video history even if removed from YouTube

## Migration from Original System

1. Keep using `update_feeds.py` for full refreshes
2. Use `incremental_updater.py` for regular updates
3. Both systems can coexist - they generate the same RSS format

## Example Workflow

```bash
# Initial setup - fetch all videos for configured channels
python incremental_updater.py

# Set up cron job for regular incremental updates
# This runs every hour and only fetches new videos
0 * * * * cd /path/to/YoutubeRSSMaker && python incremental_updater.py

# Monthly cleanup of old videos
0 0 1 * * cd /path/to/YoutubeRSSMaker && python incremental_updater.py --cleanup-days 365
```

## Advanced Usage

### Programmatic Access

```python
from incremental_updater import IncrementalFeedUpdater
from update_feeds import ChannelConfig

# Initialize
updater = IncrementalFeedUpdater("feeds.db")

# Update a single channel
config = ChannelConfig(channel="@TechnologyConnections", output="tech.xml")
success = updater.update_feed_incremental(config, api_key)

# Generate RSS from storage (no API call needed)
rss_xml = updater.generate_rss_from_storage(channel_id, config)

# Get statistics
stats = updater.get_feed_stats()
```

### Custom Database Queries

```python
from feed_storage import FeedStorage

storage = FeedStorage("feeds.db")

# Get all videos from last 7 days
from datetime import datetime, timedelta
week_ago = datetime.now() - timedelta(days=7)
recent_videos = storage.get_videos_since(channel_id, week_ago)

# Get only new videos since last update
new_videos = storage.get_new_videos_since_last_update(channel_id)
```

## Troubleshooting

### Database Locked Errors
If running multiple instances, ensure only one updater runs at a time or use different database files.

### API Quota Issues
The incremental system dramatically reduces API usage, but first runs still fetch all videos. For large channels, consider running initial setup during off-peak hours.

### Missing Videos
If videos seem missing, check:
1. Video publication date vs last update time
2. API quota limits
3. Channel configuration in CHANNELS setting

## Limitations

- Still requires API calls to detect new videos (YouTube doesn't provide "since" filtering)
- First run for large channels can still consume significant API quota
- Private/unlisted videos are not accessible via API
- Video statistics may change but aren't automatically updated (use full refresh occasionally)