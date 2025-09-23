#!/usr/bin/env python3
"""
YouTube RSS Maker - Main Entry Point
------------------------------------

Modern YouTube RSS feed generator with incremental updates and multi-user support.

This is now the default entry point that provides:
- Incremental feed updates (only fetch new videos)
- Per-user API key management
- SQLite storage for efficient operations
- Feed management commands

Usage:
    # Add a new feed
    python youtube_rss.py add @TechnologyConnections tech-connections.xml --user alice --api-key KEY

    # Update all feeds
    python youtube_rss.py update

    # List feeds
    python youtube_rss.py list

    # Legacy single-channel mode
    python youtube_rss.py channel @TechnologyConnections --out feed.xml
"""

import sys
import argparse
from pathlib import Path

# Import all the modules we need
from feed_manager import FeedManager
from incremental_updater import main as incremental_main
from youtube_channel_to_rss import main as single_channel_main


def main():
    parser = argparse.ArgumentParser(
        description="YouTube RSS Maker - Generate RSS feeds from YouTube channels",
        epilog="""
Examples:
  # Add a new feed (modern approach)
  youtube_rss.py add @TechnologyConnections tech-connections.xml --user alice

  # Update all feeds using stored configurations
  youtube_rss.py update

  # List all feeds
  youtube_rss.py list

  # Generate single channel RSS (legacy mode)
  youtube_rss.py channel @TechnologyConnections --out feed.xml
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Add command - delegate to feed_manager
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

    # Remove command - delegate to feed_manager
    remove_parser = subparsers.add_parser("remove", help="Remove a feed")
    remove_parser.add_argument("channel", help="Channel identifier or channel ID")
    remove_parser.add_argument("--user", help="User ID (for permission check)")
    remove_parser.add_argument("--db-path", help="Database path")

    # List command - delegate to feed_manager
    list_parser = subparsers.add_parser("list", help="List feeds")
    list_parser.add_argument("--user", help="Show feeds for specific user only")
    list_parser.add_argument("--show-api-keys", action="store_true", help="Show masked API keys")
    list_parser.add_argument("--db-path", help="Database path")

    # Update command - delegate to incremental_updater
    update_parser = subparsers.add_parser("update", help="Update all feeds (incremental)")
    update_parser.add_argument("--use-env-config", action="store_true",
                              help="Use legacy .env CHANNELS config instead of stored feeds")
    update_parser.add_argument("--channels", help="Override the CHANNELS environment variable")
    update_parser.add_argument("--output-directory", help="Directory for generated feeds")
    update_parser.add_argument("--api-key", help="Fallback API key for feeds without stored keys")
    update_parser.add_argument("--db-path", help="Database path")
    update_parser.add_argument("--loop", action="store_true", help="Continuously refresh feeds")
    update_parser.add_argument("--interval", type=int, help="Refresh interval in seconds when using --loop")
    update_parser.add_argument("--log-level", help="Logging verbosity")

    # Stats command - delegate to incremental_updater
    stats_parser = subparsers.add_parser("stats", help="Show feed statistics")
    stats_parser.add_argument("--db-path", help="Database path")

    # Cleanup command - delegate to incremental_updater
    cleanup_parser = subparsers.add_parser("cleanup", help="Remove old videos")
    cleanup_parser.add_argument("days", type=int, help="Remove videos older than N days")
    cleanup_parser.add_argument("--db-path", help="Database path")

    # Channel command - delegate to original single-channel script (legacy mode)
    channel_parser = subparsers.add_parser("channel", help="Generate RSS for single channel (legacy mode)")
    channel_parser.add_argument("channel", help="Channel URL, @handle, /channel/ID, /user/NAME, /c/NAME, or search query")
    channel_parser.add_argument("--api-key", help="YouTube Data API v3 key")
    channel_parser.add_argument("--out", default="-", help="Output RSS file path (default: stdout)")
    channel_parser.add_argument("--oldest-first", action="store_true", help="Sort oldest uploads first")
    channel_parser.add_argument("--include-captions", action="store_true", help="Include video captions")
    channel_parser.add_argument("--caption-language", default="en", help="Caption language code")
    channel_parser.add_argument("--allow-generated-captions", action="store_true", help="Allow auto-generated captions")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        print("\nHint: Start with 'python youtube_rss.py add' to add your first feed")
        return 1

    # Route to appropriate handler
    if args.command in ["add", "remove", "list"]:
        # Feed management commands - use feed_manager module
        from feed_manager import main as feed_manager_main

        # Reconstruct argv for feed_manager
        feed_args = [args.command]

        if args.command == "add":
            feed_args.append(args.channel)
            if args.output:
                feed_args.extend(["--output", args.output])
            if args.user != "DefaultUser":
                feed_args.extend(["--user", args.user])
            if args.api_key:
                feed_args.extend(["--api-key", args.api_key])
            if args.include_captions:
                feed_args.append("--include-captions")
            if args.caption_language != "en":
                feed_args.extend(["--caption-language", args.caption_language])
            if args.allow_generated_captions:
                feed_args.append("--allow-generated-captions")
            if args.oldest_first:
                feed_args.append("--oldest-first")
            if args.channel_url:
                feed_args.extend(["--channel-url", args.channel_url])

        elif args.command == "remove":
            feed_args.append(args.channel)
            if args.user:
                feed_args.extend(["--user", args.user])

        elif args.command == "list":
            if args.user:
                feed_args.extend(["--user", args.user])
            if args.show_api_keys:
                feed_args.append("--show-api-keys")

        # Add db-path if specified
        if hasattr(args, 'db_path') and args.db_path:
            feed_args.extend(["--db-path", args.db_path])

        # Replace sys.argv and call feed_manager main
        old_argv = sys.argv[:]
        sys.argv = ["feed_manager.py"] + feed_args
        try:
            return feed_manager_main()
        finally:
            sys.argv = old_argv

    elif args.command in ["update", "stats", "cleanup"]:
        # Update/stats commands - use incremental_updater module
        updater_args = []

        if args.command == "update":
            if args.use_env_config:
                # Use legacy .env mode
                pass  # Don't add --use-stored-feeds flag
            else:
                # Use stored feeds mode (default)
                updater_args.append("--use-stored-feeds")

            if args.channels:
                updater_args.extend(["--channels", args.channels])
            if args.output_directory:
                updater_args.extend(["--output-directory", args.output_directory])
            if args.api_key:
                updater_args.extend(["--api-key", args.api_key])
            if args.loop:
                updater_args.append("--loop")
            if args.interval:
                updater_args.extend(["--interval", str(args.interval)])
            if args.log_level:
                updater_args.extend(["--log-level", args.log_level])

        elif args.command == "stats":
            updater_args.append("--stats")

        elif args.command == "cleanup":
            updater_args.extend(["--cleanup-days", str(args.days)])

        # Add db-path if specified
        if hasattr(args, 'db_path') and args.db_path:
            updater_args.extend(["--db-path", args.db_path])

        # Replace sys.argv and call incremental_updater main
        old_argv = sys.argv[:]
        sys.argv = ["incremental_updater.py"] + updater_args
        try:
            return incremental_main()
        finally:
            sys.argv = old_argv

    elif args.command == "channel":
        # Single channel mode - use original script
        channel_args = ["--channel", args.channel]

        if args.api_key:
            channel_args.extend(["--api-key", args.api_key])
        if args.out != "-":
            channel_args.extend(["--out", args.out])
        if args.oldest_first:
            channel_args.append("--oldest-first")
        if args.include_captions:
            channel_args.append("--include-captions")
        if args.caption_language != "en":
            channel_args.extend(["--caption-language", args.caption_language])
        if args.allow_generated_captions:
            channel_args.append("--allow-generated-captions")

        # Replace sys.argv and call original main
        old_argv = sys.argv[:]
        sys.argv = ["youtube_channel_to_rss.py"] + channel_args
        try:
            return single_channel_main()
        finally:
            sys.argv = old_argv

    return 0


if __name__ == "__main__":
    sys.exit(main())