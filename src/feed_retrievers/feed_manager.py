#!/usr/bin/env python3
"""
Feed Management CLI for YouTube RSS Maker
-----------------------------------------

Command-line interface for managing feeds:
- Add new feeds with optional user and API key
- Remove existing feeds
- List feeds by user or all feeds
- Update feed configurations
"""

import argparse
import os
import sys
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
import requests

sys.path.append(str(Path(__file__).parent.parent))

from database.feed_storage import FeedStorage
from .youtube_channel_to_rss import resolve_channel_id
from discord_interactions.discord_logger import get_logger, FeedReport, APIUsageReport


class FeedManager:
    """Manages YouTube RSS feeds with user and API key support."""

    def __init__(self, db_path: str):
        self.storage = FeedStorage(db_path)
        self.logger = get_logger()

    def add_feed(self, channel_identifier: str, output_filename: str,
                 user_id: str = "DefaultUser", api_key: Optional[str] = None,
                 include_captions: bool = False, caption_language: str = "en",
                 allow_generated_captions: bool = False, oldest_first: bool = False,
                 channel_url: Optional[str] = None) -> bool:
        """Add a new feed to the system."""

        if not api_key:
            print("Error: API key is required to resolve channel information")
            return False

        try:
            print(f"Resolving channel: {channel_identifier}")
            self.logger.log_debug(f"Adding feed for {channel_identifier} (user: {user_id})")

            # Track API usage for channel resolution
            api_usage = self.logger.track_api_usage("channels", 1, user_id=user_id)

            # Resolve channel to get canonical ID and metadata
            with requests.Session() as session:
                try:
                    channel_id, channel_resource = resolve_channel_id(
                        session, api_key, channel_identifier
                    )
                except Exception as e:
                    error_msg = str(e)
                    if "not found" in error_msg.lower():
                        print(f"Error: Channel not found - {channel_identifier}")

                        # Report failed operation
                        report = FeedReport(
                            action="add",
                            channel_title=channel_identifier,
                            channel_id="",
                            user_id=user_id,
                            videos_processed=0,
                            new_videos=0,
                            timestamp=datetime.now(timezone.utc),
                            api_usage=api_usage,
                            error=f"Channel not found: {channel_identifier}"
                        )
                        self.logger.report_feed_operation(report)
                        return False
                    else:
                        raise

            channel_title = channel_resource["snippet"].get("title", channel_identifier)

            # Generate default output filename if none provided
            if not output_filename:
                # Generate slugified filename
                import re
                def slugify_channel(name):
                    clean = re.sub(r'[^\w\s-]', '', name)
                    return re.sub(r'[-\s]+', '-', clean).lower() + '.xml'
                output_filename = slugify_channel(channel_title)
                print(f"Using default filename: {output_filename}")

            # Validate that the channel has an uploads playlist
            try:
                from .youtube_channel_to_rss import get_uploads_playlist_id, fetch_all_playlist_video_ids
                uploads_playlist_id = get_uploads_playlist_id(channel_resource)

                # Track API usage for playlist items
                self.logger.track_api_usage("playlistItems", 1, channel_id, user_id)

                # Check if channel has any videos
                video_ids = fetch_all_playlist_video_ids(session, api_key, uploads_playlist_id)

                if not video_ids:
                    error_msg = f"Channel '{channel_title}' has no videos"
                    print(f"Error: {error_msg}")

                    # Report failed operation
                    report = FeedReport(
                        action="add",
                        channel_title=channel_title,
                        channel_id=channel_id,
                        user_id=user_id,
                        videos_processed=0,
                        new_videos=0,
                        timestamp=datetime.now(timezone.utc),
                        api_usage=api_usage,
                        error=error_msg
                    )
                    self.logger.report_feed_operation(report)
                    return False

                print(f"Found {len(video_ids)} videos in channel")

            except Exception as e:
                error_msg = f"Unable to access videos for channel '{channel_title}': {e}"
                print(f"Error: {error_msg}")

                # Report failed operation
                report = FeedReport(
                    action="add",
                    channel_title=channel_title,
                    channel_id=channel_id,
                    user_id=user_id,
                    videos_processed=0,
                    new_videos=0,
                    timestamp=datetime.now(timezone.utc),
                    api_usage=api_usage,
                    error=error_msg
                )
                self.logger.report_feed_operation(report)
                return False

            # Check if feed already exists
            existing_feed = self.storage.get_feed(channel_id, increment_counter=False)
            if existing_feed:
                print(f"Feed already exists for '{channel_title}' (added by {existing_feed.user_id})")
                print("Use --force to update the existing feed configuration")
                return False

            # Prepare feed configuration
            feed_config = {
                "output": output_filename,
                "include_captions": include_captions,
                "caption_language": caption_language,
                "allow_generated_captions": allow_generated_captions,
                "oldest_first": oldest_first,
                "channel_url": channel_url
            }

            # Register the feed
            stored_feed = self.storage.register_feed(
                channel_id=channel_id,
                channel_identifier=channel_identifier,
                channel_title=channel_title,
                feed_config=feed_config,
                user_id=user_id,
                api_key=api_key
            )

            print(f"✓ Successfully added feed:")
            print(f"  Channel: {channel_title}")
            print(f"  Channel ID: {channel_id}")
            print(f"  User: {user_id}")
            print(f"  Output: {output_filename}")

            # Report successful operation
            report = FeedReport(
                action="add",
                channel_title=channel_title,
                channel_id=channel_id,
                user_id=user_id,
                videos_processed=len(video_ids),
                new_videos=len(video_ids),  # All videos are "new" when adding
                timestamp=datetime.now(timezone.utc),
                api_usage=api_usage
            )
            self.logger.report_feed_operation(report)

            return True

        except Exception as exc:
            print(f"Error adding feed: {exc}")
            return False

    def remove_feed(self, channel_identifier: str, user_id: Optional[str] = None) -> bool:
        """Remove a feed from the system."""

        # If channel_identifier looks like a channel ID, use it directly
        if channel_identifier.startswith("UC") and len(channel_identifier) == 24:
            channel_id = channel_identifier
        else:
            # Find the feed by identifier
            feeds = self.storage.get_all_feeds()
            matching_feeds = [f for f in feeds if f.channel_identifier == channel_identifier]

            if not matching_feeds:
                print(f"No feed found for: {channel_identifier}")
                return False

            if len(matching_feeds) > 1:
                print(f"Multiple feeds found for {channel_identifier}:")
                for feed in matching_feeds:
                    print(f"  {feed.channel_title} (user: {feed.user_id})")
                print("Please specify --user to disambiguate or use the channel ID directly")
                return False

            channel_id = matching_feeds[0].channel_id

        # Get feed details for confirmation
        feed = self.storage.get_feed(channel_id, increment_counter=False)
        if not feed:
            print(f"Feed not found: {channel_identifier}")
            return False

        # Check user permission if specified
        if user_id and feed.user_id != user_id:
            print(f"Permission denied: Feed belongs to user '{feed.user_id}', not '{user_id}'")
            return False

        # Remove the feed
        success = self.storage.remove_feed(channel_id)
        if success:
            print(f"✓ Removed feed: {feed.channel_title} (user: {feed.user_id})")

            # Report successful removal
            report = FeedReport(
                action="remove",
                channel_title=feed.channel_title,
                channel_id=channel_id,
                user_id=feed.user_id,
                videos_processed=feed.last_video_count,
                new_videos=0,
                timestamp=datetime.now(timezone.utc)
            )
            self.logger.report_feed_operation(report)

            return True
        else:
            error_msg = f"Failed to remove feed: {channel_identifier}"
            print(error_msg)

            # Report failed removal
            report = FeedReport(
                action="remove",
                channel_title=feed.channel_title,
                channel_id=channel_id,
                user_id=feed.user_id,
                videos_processed=0,
                new_videos=0,
                timestamp=datetime.now(timezone.utc),
                error=error_msg
            )
            self.logger.report_feed_operation(report)

            return False

    def list_feeds(self, user_id: Optional[str] = None, show_api_keys: bool = False) -> None:
        """List all feeds or feeds for a specific user."""

        if user_id:
            feeds = self.storage.get_feeds_by_user(user_id)
            print(f"Feeds for user '{user_id}':")
        else:
            feeds = self.storage.get_all_feeds()
            print("All feeds:")

        if not feeds:
            print("  No feeds found")
            return

        for feed in feeds:
            print(f"\n  {feed.channel_title}")
            print(f"    Channel ID: {feed.channel_id}")
            print(f"    Identifier: {feed.channel_identifier}")
            print(f"    User: {feed.user_id}")
            print(f"    Output: {feed.feed_config.get('output', 'not configured')}")
            print(f"    Last updated: {feed.last_updated}")
            print(f"    Video count: {feed.last_video_count}")

            if show_api_keys and feed.api_key:
                # Show only first/last few chars for security
                masked_key = f"{feed.api_key[:8]}...{feed.api_key[-4:]}"
                print(f"    API key: {masked_key}")

    def update_feed_config(self, channel_identifier: str, user_id: Optional[str] = None,
                          **config_updates) -> bool:
        """Update configuration for an existing feed."""

        # Find the feed
        feeds = self.storage.get_all_feeds()
        matching_feeds = [f for f in feeds if
                         f.channel_identifier == channel_identifier or
                         f.channel_id == channel_identifier]

        if not matching_feeds:
            print(f"No feed found for: {channel_identifier}")
            return False

        if len(matching_feeds) > 1 and not user_id:
            print(f"Multiple feeds found for {channel_identifier}:")
            for feed in matching_feeds:
                print(f"  {feed.channel_title} (user: {feed.user_id})")
            print("Please specify --user to disambiguate")
            return False

        feed = matching_feeds[0]
        if user_id and feed.user_id != user_id:
            if len(matching_feeds) > 1:
                user_feeds = [f for f in matching_feeds if f.user_id == user_id]
                if user_feeds:
                    feed = user_feeds[0]
                else:
                    print(f"No feed found for user '{user_id}'")
                    return False
            else:
                print(f"Permission denied: Feed belongs to user '{feed.user_id}'")
                return False

        # Update the configuration
        updated_config = feed.feed_config.copy()
        updated_config.update(config_updates)

        self.storage.register_feed(
            channel_id=feed.channel_id,
            channel_identifier=feed.channel_identifier,
            channel_title=feed.channel_title,
            feed_config=updated_config,
            user_id=feed.user_id,
            api_key=feed.api_key
        )

        print(f"✓ Updated configuration for: {feed.channel_title}")
        return True


def main():
    parser = argparse.ArgumentParser(description="Manage YouTube RSS feeds")
    parser.add_argument("--db-path", help="Database path (defaults to DATABASE_PATH env or feeds.db)")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Add feed command
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

    # Remove feed command
    remove_parser = subparsers.add_parser("remove", help="Remove a feed")
    remove_parser.add_argument("channel", help="Channel identifier or channel ID")
    remove_parser.add_argument("--user", help="User ID (for permission check)")

    # List feeds command
    list_parser = subparsers.add_parser("list", help="List feeds")
    list_parser.add_argument("--user", help="Show feeds for specific user only")
    list_parser.add_argument("--show-api-keys", action="store_true", help="Show masked API keys")

    # Update feed command
    update_parser = subparsers.add_parser("update", help="Update feed configuration")
    update_parser.add_argument("channel", help="Channel identifier or channel ID")
    update_parser.add_argument("--user", help="User ID (for permission check)")
    update_parser.add_argument("--output", help="Update output filename")
    update_parser.add_argument("--include-captions", type=bool, help="Update caption inclusion")
    update_parser.add_argument("--caption-language", help="Update caption language")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Load environment and determine database path
    load_dotenv()
    db_path = args.db_path or os.getenv("DATABASE_PATH", "feeds.db")

    # Create manager
    manager = FeedManager(db_path)

    # Execute command
    if args.command == "add":
        api_key = args.api_key or os.getenv("YT_API_KEY")
        if not api_key:
            print("Error: API key required. Set YT_API_KEY or use --api-key")
            return 1

        success = manager.add_feed(
            channel_identifier=args.channel,
            output_filename=args.output,
            user_id=args.user,
            api_key=api_key,
            include_captions=args.include_captions,
            caption_language=args.caption_language,
            allow_generated_captions=args.allow_generated_captions,
            oldest_first=args.oldest_first,
            channel_url=args.channel_url
        )
        return 0 if success else 1

    elif args.command == "remove":
        success = manager.remove_feed(args.channel, args.user)
        return 0 if success else 1

    elif args.command == "list":
        manager.list_feeds(args.user, args.show_api_keys)
        return 0

    elif args.command == "update":
        config_updates = {}
        if args.output:
            config_updates["output"] = args.output
        if args.include_captions is not None:
            config_updates["include_captions"] = args.include_captions
        if args.caption_language:
            config_updates["caption_language"] = args.caption_language

        if not config_updates:
            print("No configuration updates specified")
            return 1

        success = manager.update_feed_config(args.channel, args.user, **config_updates)
        return 0 if success else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())