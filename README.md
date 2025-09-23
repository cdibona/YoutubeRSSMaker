# YouTube RSS Maker

Modern YouTube RSS feed generator with incremental updates and multi-user support. Create RSS feeds for any YouTube channel with intelligent storage that only fetches new videos since your last check.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.template .env
# Edit .env to add your YT_API_KEY

# Add your first feed
python youtube_rss.py add @TechnologyConnections tech-connections.xml --api-key YOUR_KEY

# Update all feeds (only fetches new videos)
python youtube_rss.py update

# List your feeds
python youtube_rss.py list
```

## Features

- **Incremental Updates**: Only fetches new videos since last check
- **Multi-User Support**: Different users can manage feeds with their own API keys
- **SQLite Storage**: Fast, persistent storage of video metadata
- **Automatic Deduplication**: Prevents duplicate video entries
- **Feed Management**: Add, remove, and list feeds with simple commands
- **Reduced API Usage**: Dramatically lower YouTube API quota consumption
- **Discord Integration**: Optional webhook notifications for feed operations

## Documentation

Detailed documentation is available in the `src/documentation/` directory:

- [Complete README](src/documentation/README.md) - Full feature documentation
- [CLAUDE.md](src/documentation/CLAUDE.md) - Development guide for Claude Code

## Project Structure

```
youtube-rss-maker/
├── youtube_rss.py              # Main entry point
├── src/
│   ├── feed_retrievers/        # YouTube API and feed management
│   ├── discord_interactions/   # Discord webhook integration
│   ├── database/              # SQLite storage and data management
│   └── documentation/         # Project documentation
├── .env.template              # Environment configuration template
└── requirements.txt           # Python dependencies
```

## License

MIT License – feel free to use, modify, and share.