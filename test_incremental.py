#!/usr/bin/env python3
"""
Test script for the incremental feed update system.
"""

import os
import tempfile
from pathlib import Path
from feed_storage import FeedStorage
from incremental_updater import IncrementalFeedUpdater
from update_feeds import ChannelConfig

def test_storage_system():
    """Test basic storage functionality."""
    print("Testing storage system...")

    # Use temporary database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    try:
        storage = FeedStorage(db_path)

        # Test feed registration
        feed = storage.register_feed(
            "UC123test",
            "@testchannel",
            "Test Channel",
            {"include_captions": False}
        )
        print(f"✓ Registered feed: {feed.channel_title}")

        # Test retrieval
        retrieved = storage.get_feed("UC123test")
        assert retrieved is not None
        assert retrieved.channel_title == "Test Channel"
        print("✓ Feed retrieval works")

        # Test video storage (mock data)
        mock_videos = [
            {
                "id": "video123",
                "snippet": {
                    "title": "Test Video",
                    "description": "Test description",
                    "publishedAt": "2024-01-01T12:00:00Z",
                    "thumbnails": {"default": {"url": "http://example.com/thumb.jpg"}}
                },
                "contentDetails": {
                    "duration": "PT5M30S"
                },
                "statistics": {
                    "viewCount": "1000",
                    "likeCount": "50"
                }
            }
        ]

        new_count, total_count = storage.store_videos("UC123test", mock_videos)
        print(f"✓ Stored videos: {new_count} new, {total_count} total")

        # Test video retrieval
        videos = storage.get_videos_since("UC123test")
        assert len(videos) == 1
        assert videos[0].title == "Test Video"
        print("✓ Video retrieval works")

        print("✓ All storage tests passed!")

    finally:
        # Cleanup
        Path(db_path).unlink(missing_ok=True)

def test_with_real_api():
    """Test with a real YouTube channel (requires API key)."""
    api_key = os.getenv("YT_API_KEY")
    if not api_key:
        print("⚠ Skipping real API test - no YT_API_KEY found")
        return

    print("Testing with real YouTube API...")

    # Use temporary database and output directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        db_path = temp_path / "test.db"
        output_dir = temp_path / "feeds"

        updater = IncrementalFeedUpdater(str(db_path))

        # Test with a small, reliable channel (Technology Connections has short handle)
        config = ChannelConfig(
            channel="@TechnologyConnections",
            output="tech-connections.xml",
            include_captions=False
        )

        print(f"Testing with channel: {config.channel}")

        # First update (should fetch all videos)
        success = updater.update_feed_incremental(config, api_key)
        if success:
            print("✓ First incremental update successful")

            # Generate RSS
            import requests
            from youtube_channel_to_rss import resolve_channel_id

            with requests.Session() as session:
                channel_id, _ = resolve_channel_id(session, api_key, config.channel)

            rss_xml = updater.generate_rss_from_storage(channel_id, config)
            if rss_xml:
                print("✓ RSS generation from storage successful")

                # Write to file
                output_dir.mkdir(parents=True, exist_ok=True)
                output_file = output_dir / config.output
                output_file.write_text(rss_xml, encoding="utf-8")
                print(f"✓ RSS written to {output_file}")

                # Show some stats
                stats = updater.get_feed_stats()
                print(f"✓ Storage stats: {stats['total_feeds']} feeds, {stats['total_videos']} videos")

            else:
                print("✗ RSS generation failed")
        else:
            print("✗ Incremental update failed")

if __name__ == "__main__":
    print("=== Testing Incremental Feed System ===\n")

    test_storage_system()
    print()
    test_with_real_api()
    print("\n=== Test Complete ===")