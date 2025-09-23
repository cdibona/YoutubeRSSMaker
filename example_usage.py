#!/usr/bin/env python3
"""
Example usage of the incremental YouTube RSS feed system.

This demonstrates how to:
1. Set up feeds for incremental updates
2. Run initial and subsequent updates
3. Generate RSS feeds from stored data
4. View feed statistics
"""

import os
from pathlib import Path
from feed_storage import FeedStorage
from incremental_updater import IncrementalFeedUpdater
from update_feeds import ChannelConfig

def example_basic_usage():
    """Basic usage example."""
    # Initialize with database path from environment or default
    db_path = os.getenv("DATABASE_PATH", "example_feeds.db")
    updater = IncrementalFeedUpdater(db_path)

    # Get API key from environment
    api_key = os.getenv("YT_API_KEY")
    if not api_key:
        print("Error: Please set YT_API_KEY environment variable")
        return

    # Define some channels to track
    channels = [
        ChannelConfig(
            channel="@TechnologyConnections",
            output="technology-connections.xml",
            include_captions=False
        ),
        ChannelConfig(
            channel="@ThisOldTony",
            output="this-old-tony.xml",
            include_captions=False
        ),
    ]

    print("=== Initial Feed Setup ===")

    # Update feeds (first run will fetch all videos)
    output_dir = Path("./example_feeds")
    output_dir.mkdir(exist_ok=True)

    for config in channels:
        print(f"\nUpdating {config.channel}...")

        # Update the feed data in storage
        success = updater.update_feed_incremental(config, api_key)
        if not success:
            print(f"Failed to update {config.channel}")
            continue

        # Generate RSS from storage
        import requests
        from youtube_channel_to_rss import resolve_channel_id

        with requests.Session() as session:
            channel_id, _ = resolve_channel_id(session, api_key, config.channel)

        rss_xml = updater.generate_rss_from_storage(channel_id, config)
        if rss_xml:
            output_file = output_dir / config.output
            output_file.write_text(rss_xml, encoding="utf-8")
            print(f"✓ Generated RSS: {output_file}")
        else:
            print(f"Failed to generate RSS for {config.channel}")

    print("\n=== Feed Statistics ===")
    stats = updater.get_feed_stats()
    print(f"Total feeds: {stats['total_feeds']}")
    print(f"Total videos stored: {stats['total_videos']}")

    for feed_info in stats["feeds"]:
        print(f"\n{feed_info['channel_title']}:")
        print(f"  Videos: {feed_info['video_count']}")
        print(f"  Last updated: {feed_info['last_updated']}")
        if feed_info['newest_video_date']:
            print(f"  Newest video: {feed_info['newest_video_date']}")

def example_subsequent_update():
    """Example of running subsequent updates (incremental)."""
    print("\n=== Subsequent Update (Incremental) ===")

    # This would typically be run later (hours/days after initial setup)
    db_path = os.getenv("DATABASE_PATH", "example_feeds.db")
    updater = IncrementalFeedUpdater(db_path)
    api_key = os.getenv("YT_API_KEY")

    if not api_key:
        print("Error: Please set YT_API_KEY environment variable")
        return

    # Check what feeds we have
    feeds = updater.storage.get_all_feeds()
    print(f"Found {len(feeds)} configured feeds")

    for feed in feeds:
        print(f"\nChecking for updates: {feed.channel_title}")
        print(f"Last updated: {feed.last_updated}")

        # Simulate the config (in real usage, you'd load this from .env)
        config = ChannelConfig(
            channel=feed.channel_identifier,
            output=f"{feed.channel_id}.xml",  # Use channel ID as filename
            **feed.feed_config  # Expand stored config
        )

        # This will only store new videos since last update
        success = updater.update_feed_incremental(config, api_key)
        if success:
            print("✓ Update completed")
        else:
            print("✗ Update failed")

def example_stats_and_cleanup():
    """Example of viewing stats and cleaning up old data."""
    print("\n=== Statistics and Cleanup ===")

    db_path = os.getenv("DATABASE_PATH", "example_feeds.db")
    updater = IncrementalFeedUpdater(db_path)

    # Show current stats
    stats = updater.get_feed_stats()
    print(f"Current storage: {stats['total_videos']} videos across {stats['total_feeds']} feeds")

    # Clean up videos older than 180 days (6 months)
    deleted_count = updater.storage.cleanup_old_videos(180)
    print(f"Cleaned up {deleted_count} videos older than 180 days")

    # Show updated stats
    stats = updater.get_feed_stats()
    print(f"After cleanup: {stats['total_videos']} videos remaining")

if __name__ == "__main__":
    print("YouTube RSS Incremental Updater - Example Usage")
    print("=" * 50)

    # Check for API key
    if not os.getenv("YT_API_KEY"):
        print("Please set YT_API_KEY environment variable to run examples")
        print("export YT_API_KEY='your-api-key-here'")
        exit(1)

    # Run examples
    try:
        example_basic_usage()
        example_subsequent_update()
        example_stats_and_cleanup()

        print("\n" + "=" * 50)
        print("Example complete!")
        print("\nGenerated files:")
        print("- example_feeds.db (SQLite database)")
        print("- example_feeds/*.xml (RSS feed files)")

    except Exception as e:
        print(f"\nError during example: {e}")
        import traceback
        traceback.print_exc()