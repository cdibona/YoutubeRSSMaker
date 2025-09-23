#!/usr/bin/env python3
"""
YouTube RSS Maker - Main Entry Point
------------------------------------

Modern YouTube RSS feed generator with incremental updates and multi-user support.

Usage:
    # Add a new feed
    python youtube_rss.py add @TechnologyConnections tech-connections.xml --user alice --api-key KEY

    # Update all feeds
    python youtube_rss.py update

    # List feeds
    python youtube_rss.py list
"""

import sys
import argparse
import os
from pathlib import Path

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Add src to Python path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from feed_retrievers.feed_manager import FeedManager
from feed_retrievers.feed_updater import FeedUpdater


def main():
    parser = argparse.ArgumentParser(
        description="YouTube RSS Maker - Generate RSS feeds from YouTube channels",
        epilog="""
Examples:
  # Add a new feed
  youtube_rss.py add @TechnologyConnections tech-connections.xml --user alice

  # Update all feeds using stored configurations
  youtube_rss.py update

  # List all feeds
  youtube_rss.py list
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Add command
    add_parser = subparsers.add_parser("add", help="Add a new feed")
    add_parser.add_argument("channel", help="Channel identifier (@handle, URL, or channel ID)")
    add_parser.add_argument("--output", help="Output RSS filename (defaults to channel-name.xml)")
    add_parser.add_argument("--user", default="DefaultUser", help="User ID (default: DefaultUser)")
    add_parser.add_argument("--api-key", help="YouTube API key for this feed")
    add_parser.add_argument("--include-captions", action="store_true", help="Include video captions")
    add_parser.add_argument("--caption-language", default="en", help="Caption language code")
    add_parser.add_argument("--allow-generated-captions", action="store_true", help="Allow auto-generated captions")
    add_parser.add_argument("--oldest-first", action="store_true", help="Sort oldest videos first")
    add_parser.add_argument("--channel-url", help="Custom channel URL override")
    add_parser.add_argument("--db-path", help="Database path (defaults to DATABASE_PATH env or feeds.db)")

    # Remove command
    remove_parser = subparsers.add_parser("remove", help="Remove a feed")
    remove_parser.add_argument("channel", help="Channel identifier or channel ID")
    remove_parser.add_argument("--user", help="User ID (for permission check)")
    remove_parser.add_argument("--db-path", help="Database path")

    # List command
    list_parser = subparsers.add_parser("list", help="List feeds")
    list_parser.add_argument("--user", help="Show feeds for specific user only")
    list_parser.add_argument("--show-api-keys", action="store_true", help="Show masked API keys")
    list_parser.add_argument("--db-path", help="Database path")

    # Update command
    update_parser = subparsers.add_parser("update", help="Update all feeds (incremental)")
    update_parser.add_argument("--output-directory", help="Directory for generated feeds")
    update_parser.add_argument("--api-key", help="Fallback API key for feeds without stored keys")
    update_parser.add_argument("--db-path", help="Database path")
    update_parser.add_argument("--loop", action="store_true", help="Continuously refresh feeds")
    update_parser.add_argument("--interval", type=int, help="Refresh interval in seconds when using --loop")
    update_parser.add_argument("--log-level", help="Logging verbosity")

    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Show feed statistics")
    stats_parser.add_argument("--db-path", help="Database path")
    stats_parser.add_argument("--send-discord", action="store_true", help="Send stats to Discord testing channel")

    # Cleanup command
    cleanup_parser = subparsers.add_parser("cleanup", help="Remove old videos")
    cleanup_parser.add_argument("days", type=int, help="Remove videos older than N days")
    cleanup_parser.add_argument("--db-path", help="Database path")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        print("\nHint: Start with 'python youtube_rss.py add' to add your first feed")
        return 1

    # Set default database path
    db_path = getattr(args, 'db_path', None) or os.getenv('DATABASE_PATH', 'src/database/data/feeds.db')

    # Route to appropriate handler
    if args.command in ["add", "remove", "list"]:
        # Feed management commands
        manager = FeedManager(db_path)

        if args.command == "add":
            # Use provided API key or fall back to environment variable
            api_key = args.api_key or os.getenv('YT_API_KEY')
            return 0 if manager.add_feed(
                channel_identifier=args.channel,
                output_filename=args.output,
                user_id=args.user,
                api_key=api_key,
                include_captions=args.include_captions,
                caption_language=args.caption_language,
                allow_generated_captions=args.allow_generated_captions,
                oldest_first=args.oldest_first,
                channel_url=args.channel_url
            ) else 1

        elif args.command == "remove":
            return 0 if manager.remove_feed(
                channel_identifier=args.channel,
                user_id=args.user
            ) else 1

        elif args.command == "list":
            manager.list_feeds(
                user_id=args.user,
                show_api_keys=args.show_api_keys
            )
            return 0

    elif args.command in ["update", "stats", "cleanup"]:
        # Update/stats commands - use feed updater
        updater = FeedUpdater(db_path)

        if args.command == "update":
            output_dir = args.output_directory or os.getenv('OUTPUT_DIRECTORY', './feeds')
            fallback_api_key = args.api_key or os.getenv('YT_API_KEY')
            return 0 if updater.update_all_feeds(
                output_directory=output_dir,
                fallback_api_key=fallback_api_key,
                loop=args.loop,
                interval=args.interval or 3600
            ) else 1

        elif args.command == "stats":
            updater.show_stats(send_to_discord=args.send_discord)
            return 0

        elif args.command == "cleanup":
            return 0 if updater.cleanup_old_videos(args.days) else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())