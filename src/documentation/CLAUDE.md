# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

YouTube RSS Maker is a Python application that generates RSS feeds from YouTube channels using the YouTube Data API v3. It features incremental updates with SQLite storage and multi-user support.

## Development Commands

### Setup and Dependencies
```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment (copy and edit)
cp .env.template .env
# Edit .env to add your YT_API_KEY
```

### Running the Application

```bash
# Add a feed
python youtube_rss.py add @ChannelHandle output.xml --user username --api-key YOUR_KEY

# Update all feeds incrementally
python youtube_rss.py update

# List all feeds
python youtube_rss.py list

# Remove a feed
python youtube_rss.py remove @ChannelHandle --user username

# View statistics
python youtube_rss.py stats

# Clean up old videos
python youtube_rss.py cleanup 365
```

### Testing
```bash
# Test Discord integration
python src/discord_interactions/test_discord.py

# Test basic functionality
python youtube_rss.py --help
python youtube_rss.py list
python youtube_rss.py stats
```

## Architecture Overview

### Project Structure

```
youtube-rss-maker/
├── youtube_rss.py                    # Main entry point and CLI
├── src/
│   ├── feed_retrievers/              # YouTube API and feed management
│   │   ├── feed_manager.py          # Feed CRUD operations
│   │   ├── feed_updater.py          # Incremental feed updates
│   │   └── youtube_channel_to_rss.py # YouTube API integration
│   ├── discord_interactions/         # Discord webhook integration
│   │   ├── discord_logger.py        # Discord logging and notifications
│   │   └── test_discord.py          # Discord integration tests
│   ├── database/                     # SQLite storage layer
│   │   ├── feed_storage.py          # Database operations and models
│   │   └── data/                    # Database files location
│   │       └── feeds.db             # SQLite database (auto-created)
│   └── documentation/               # Project documentation
│       ├── README.md               # Complete feature documentation
│       ├── INCREMENTAL_README.md   # Legacy documentation
│       └── CLAUDE.md               # This file
├── .env.template                    # Environment configuration template
└── requirements.txt                 # Python dependencies
```

### Core Components

**Main Entry Point**:
- `youtube_rss.py` - CLI interface routing commands to appropriate modules

**Feed Retrievers** (`src/feed_retrievers/`):
- `feed_manager.py` - FeedManager class for add/remove/list operations
- `feed_updater.py` - FeedUpdater class for incremental updates
- `youtube_channel_to_rss.py` - YouTube API integration and RSS generation

**Database Layer** (`src/database/`):
- `feed_storage.py` - FeedStorage class with StoredFeed and StoredVideo models
- `data/feeds.db` - SQLite database file (auto-created)

**Discord Integration** (`src/discord_interactions/`):
- `discord_logger.py` - Discord webhook logging and notifications

### Data Flow

1. **Channel Resolution**: YouTube handles/URLs → Channel IDs via YouTube API
2. **Video Fetching**: Channel ID → Video list via YouTube API (incremental)
3. **Storage**: Videos stored in SQLite with deduplication
4. **RSS Generation**: Database → RSS XML files
5. **Incremental Updates**: Only fetch videos newer than last update timestamp

### Database Schema

**feeds table**:
- Stores channel metadata, user ownership, API keys, last update times
- Primary key: channel_id

**videos table**:
- Stores video metadata with foreign key to feeds
- Primary key: video_id
- Enables incremental updates and offline RSS generation

## Key Patterns

### Error Handling
- API quota limits are a primary concern
- YouTube API rate limiting requires exponential backoff
- Channel resolution can fail (deleted channels, API changes)

### Multi-User Support
- Users identified by string user_id (default: "DefaultUser")
- API keys stored per-user in database
- Permission checking prevents cross-user operations

### Discord Integration
- Optional webhook logging via `discord_interactions/discord_logger.py`
- Supports multiple webhook URLs (main, testing, developer)
- Structured reporting for feed operations and API usage

### YouTube API Integration
- Channel resolution supports @handles, /c/custom, /channel/UC..., /user/legacy
- Video duration parsing from ISO 8601 format (PT1H2M3S)
- Optional caption fetching via youtube-transcript-api
- Thumbnail URL extraction from multiple resolution options

## Environment Variables

Required:
- `YT_API_KEY` - YouTube Data API v3 key

Optional:
- `OUTPUT_DIRECTORY` - RSS output directory (default: ./feeds)
- `DATABASE_PATH` - SQLite database path (default: src/database/data/feeds.db)
- `DISCORD_WEBHOOK_URL` - Main Discord notifications
- `DISCORD_TESTING_WEBHOOK_URL` - Testing Discord channel
- `DISCORD_DEVELOPER_WEBHOOK_URL` - Developer Discord channel
- `LOG_TO_DISCORD` - Enable Discord logging (true/false)

## Import Structure

The project uses relative imports within modules and sys.path manipulation for cross-module imports:

```python
# Main entry point adds src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Cross-module imports
from database.feed_storage import FeedStorage
from discord_interactions.discord_logger import get_logger
from feed_retrievers.feed_manager import FeedManager

# Relative imports within modules
from .youtube_channel_to_rss import resolve_channel_id
```

## Development Notes

- Database file is automatically created in `src/database/data/feeds.db`
- RSS files are generated in `OUTPUT_DIRECTORY` (default: `./feeds/`)
- All legacy functionality has been removed (no incremental_updater.py, update_feeds.py)
- Main CLI handles all routing to appropriate classes
- Discord integration is optional but enabled by default if webhook URLs are provided