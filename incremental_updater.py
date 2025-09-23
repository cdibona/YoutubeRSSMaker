#!/usr/bin/env python3
"""
Incremental Feed Updater for YouTube RSS Maker
----------------------------------------------

Enhanced version of update_feeds.py that uses SQLite storage for:
- Incremental updates (only fetch new videos since last check)
- Persistent storage of video metadata
- Deduplication of video items
- Efficient RSS generation from stored data
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv

from youtube_channel_to_rss import generate_feed_for_channel, resolve_channel_id
from feed_storage import FeedStorage, StoredFeed, StoredVideo
from update_feeds import ChannelConfig, parse_channels_config, parse_bool
from discord_logger import get_logger, FeedReport, setup_logging


logger = logging.getLogger(__name__)


class IncrementalFeedUpdater:
    """Manages incremental feed updates with SQLite storage."""

    def __init__(self, db_path: str = "feeds.db"):
        self.storage = FeedStorage(db_path)
        self.discord_logger = get_logger()

    def update_feed_incremental(self, config: ChannelConfig, api_key: str,
                               user_id: str = "DefaultUser") -> bool:
        """
        Update a single feed incrementally.
        Only fetches new videos if this is not the first run.
        """
        try:
            # First, resolve the channel to get the canonical ID
            import requests
            with requests.Session() as session:
                try:
                    channel_id, channel_resource = resolve_channel_id(
                        session, api_key, config.channel
                    )
                except Exception as e:
                    if "not found" in str(e).lower():
                        logger.error(f"Channel not found: {config.channel}")
                        return False
                    else:
                        logger.error(f"Error resolving channel {config.channel}: {e}")
                        return False

            channel_title = channel_resource["snippet"].get("title", config.channel)

            # Check if we have this feed stored (don't increment counter for existence check)
            stored_feed = self.storage.get_feed(channel_id, increment_counter=False)
            is_first_run = stored_feed is None

            if is_first_run:
                logger.info(f"First run for {channel_title} - fetching all videos")
                # Register the feed
                feed_config = {
                    "include_captions": config.include_captions,
                    "caption_language": config.caption_language,
                    "allow_generated_captions": config.allow_generated_captions,
                    "oldest_first": config.oldest_first,
                    "channel_url": config.channel_url
                }
                stored_feed = self.storage.register_feed(
                    channel_id, config.channel, channel_title, feed_config, user_id, api_key
                )

                # Fetch all videos for first run
                feed_result = generate_feed_for_channel(
                    config.channel,
                    api_key,
                    include_captions=config.include_captions,
                    caption_language=config.caption_language,
                    allow_generated_captions=config.allow_generated_captions,
                    oldest_first=config.oldest_first,
                    channel_url_override=config.channel_url,
                )

                # Track API usage for initial fetch
                api_usage = self.discord_logger.track_api_usage("videos", len(feed_result.videos), channel_id, user_id)

                # Store all videos
                new_count, total_count = self.storage.store_videos(channel_id, feed_result.videos)
                logger.info(f"Stored {total_count} videos for {channel_title}")

                # Report successful initial add
                report = FeedReport(
                    action="add",
                    channel_title=channel_title,
                    channel_id=channel_id,
                    user_id=user_id,
                    videos_processed=total_count,
                    new_videos=new_count,
                    timestamp=datetime.now(timezone.utc),
                    api_usage=api_usage
                )
                self.discord_logger.report_feed_operation(report)

            else:
                logger.info(f"Incremental update for {channel_title} (last update: {stored_feed.last_updated})")

                # For incremental updates, we still need to fetch recent videos
                # to catch any that might have been published since last check
                # YouTube API doesn't have a "since" parameter, so we fetch recent videos
                # and let our storage deduplicate
                feed_result = generate_feed_for_channel(
                    config.channel,
                    api_key,
                    include_captions=config.include_captions,
                    caption_language=config.caption_language,
                    allow_generated_captions=config.allow_generated_captions,
                    oldest_first=False,  # Always get newest first for incremental
                    channel_url_override=config.channel_url,
                )

                # Track API usage for incremental update
                api_usage = self.discord_logger.track_api_usage("videos", len(feed_result.videos), channel_id, user_id)

                # Store videos (will deduplicate automatically)
                new_count, total_count = self.storage.store_videos(channel_id, feed_result.videos)

                if new_count > 0:
                    logger.info(f"Found {new_count} new videos for {channel_title} (total: {total_count})")
                else:
                    logger.info(f"No new videos for {channel_title} since last update")

                # Report update operation
                report = FeedReport(
                    action="update",
                    channel_title=channel_title,
                    channel_id=channel_id,
                    user_id=user_id,
                    videos_processed=len(feed_result.videos),
                    new_videos=new_count,
                    timestamp=datetime.now(timezone.utc),
                    api_usage=api_usage
                )
                self.discord_logger.report_feed_operation(report)

            return True

        except Exception as exc:
            logger.exception(f"Failed to update feed for {config.channel}: {exc}")
            return False

    def generate_rss_from_storage(self, channel_id: str, config: ChannelConfig,
                                 max_items: Optional[int] = None) -> Optional[str]:
        """Generate RSS feed from stored data."""
        try:
            stored_feed = self.storage.get_feed(channel_id)
            if not stored_feed:
                logger.error(f"No stored feed found for channel {channel_id}")
                return None

            # Get videos from storage
            videos = self.storage.get_videos_since(channel_id)

            # Apply oldest_first setting
            if config.oldest_first:
                videos.reverse()

            # Limit items if specified
            if max_items and len(videos) > max_items:
                videos = videos[:max_items]

            # Convert StoredVideo objects to the format expected by build_rss
            video_dicts = []
            for video in videos:
                video_dict = {
                    "id": video.video_id,
                    "snippet": {
                        "title": video.title,
                        "description": video.description,
                        "publishedAt": video.published_at.isoformat().replace("+00:00", "Z"),
                        "thumbnails": self._parse_thumbnail_data(video.thumbnail_url)
                    },
                    "contentDetails": {
                        "duration": self._seconds_to_iso8601(video.duration_seconds)
                    },
                    "statistics": {}
                }

                if video.view_count is not None:
                    video_dict["statistics"]["viewCount"] = str(video.view_count)
                if video.like_count is not None:
                    video_dict["statistics"]["likeCount"] = str(video.like_count)
                if video.captions:
                    video_dict["captions"] = video.captions

                video_dicts.append(video_dict)

            # Create channel resource for RSS generation
            channel_resource = {
                "id": channel_id,
                "snippet": {
                    "title": stored_feed.channel_title,
                    "description": f"Videos from {stored_feed.channel_title}",
                    "publishedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "thumbnails": {}
                },
                "statistics": {
                    "videoCount": str(len(videos))
                }
            }

            # Generate RSS using the existing function
            from youtube_channel_to_rss import build_rss
            channel_url = config.channel_url
            if not channel_url:
                if stored_feed.channel_identifier.startswith("@"):
                    channel_url = f"https://www.youtube.com/{stored_feed.channel_identifier}"
                else:
                    channel_url = f"https://www.youtube.com/channel/{channel_id}"

            rss_xml = build_rss(channel_resource, video_dicts, channel_url=channel_url)
            return rss_xml

        except Exception as exc:
            logger.exception(f"Failed to generate RSS for channel {channel_id}: {exc}")
            return None

    def update_all_feeds(self, configs: List[ChannelConfig], default_api_key: str,
                        base_dir: Path, default_user: str = "DefaultUser",
                        force_refresh: bool = False) -> bool:
        """Update all configured feeds and generate RSS files."""
        logger.info(f"Starting incremental update cycle for {len(configs)} channel(s)")
        success = True

        for config in configs:
            try:
                # For configs from .env, use default API key and user
                # (Feed manager adds feeds with their own API keys)
                api_key = default_api_key
                user_id = default_user

                # Update the feed data
                if not self.update_feed_incremental(config, api_key, user_id):
                    success = False
                    continue

                # Resolve channel ID for RSS generation
                import requests
                with requests.Session() as session:
                    channel_id, _ = resolve_channel_id(session, api_key, config.channel)

                # Generate RSS from stored data
                rss_xml = self.generate_rss_from_storage(channel_id, config)
                if not rss_xml:
                    success = False
                    continue

                # Write RSS file
                output_path = config.resolved_path(base_dir)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(rss_xml, encoding="utf-8")

                logger.info(f"Generated RSS for {config.channel} -> {output_path}")

            except Exception as exc:
                logger.exception(f"Failed to process {config.channel}: {exc}")
                success = False

        return success

    def update_all_stored_feeds(self, base_dir: Path, fallback_api_key: Optional[str] = None) -> bool:
        """Update all feeds using their stored API keys."""
        feeds = self.storage.get_all_feeds()
        logger.info(f"Starting update cycle for {len(feeds)} stored feed(s)")
        success = True

        for feed in feeds:
            try:
                # Use feed's stored API key, fallback to provided key
                api_key = feed.api_key or fallback_api_key
                if not api_key:
                    logger.error(f"No API key available for {feed.channel_title} (user: {feed.user_id})")
                    success = False
                    continue

                # Create config from stored feed data
                # Use channel title for filename (sanitized)
                from update_feeds import slugify_channel
                default_filename = slugify_channel(feed.channel_title)

                config = ChannelConfig(
                    channel=feed.channel_identifier,
                    output=feed.feed_config.get("output", default_filename),
                    include_captions=feed.feed_config.get("include_captions", False),
                    caption_language=feed.feed_config.get("caption_language", "en"),
                    allow_generated_captions=feed.feed_config.get("allow_generated_captions", False),
                    oldest_first=feed.feed_config.get("oldest_first", False),
                    channel_url=feed.feed_config.get("channel_url")
                )

                # Update the feed data
                if not self.update_feed_incremental(config, api_key, feed.user_id):
                    success = False
                    continue

                # Generate RSS from stored data
                rss_xml = self.generate_rss_from_storage(feed.channel_id, config)
                if not rss_xml:
                    success = False
                    continue

                # Write RSS file
                output_path = config.resolved_path(base_dir)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(rss_xml, encoding="utf-8")

                logger.info(f"Generated RSS for {feed.channel_title} -> {output_path}")

            except Exception as exc:
                logger.exception(f"Failed to process {feed.channel_title}: {exc}")
                success = False

        return success

    def _parse_thumbnail_data(self, thumbnail_url: str) -> Dict:
        """Convert thumbnail URL back to thumbnails dict format."""
        if not thumbnail_url:
            return {}
        return {
            "default": {"url": thumbnail_url}
        }

    def _seconds_to_iso8601(self, seconds: int) -> str:
        """Convert seconds to ISO 8601 duration format."""
        if seconds <= 0:
            return "PT0S"

        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        duration = "PT"
        if hours > 0:
            duration += f"{hours}H"
        if minutes > 0:
            duration += f"{minutes}M"
        if secs > 0 or (hours == 0 and minutes == 0):
            duration += f"{secs}S"

        return duration

    def get_feed_stats(self) -> Dict:
        """Get statistics about stored feeds."""
        feeds = self.storage.get_all_feeds()
        total_videos = 0

        stats = {
            "total_feeds": len(feeds),
            "feeds": []
        }

        for feed in feeds:
            videos = self.storage.get_videos_since(feed.channel_id)
            video_count = len(videos)
            total_videos += video_count

            newest_video = None
            if videos:
                newest_video = max(videos, key=lambda v: v.published_at)

            stats["feeds"].append({
                "channel_title": feed.channel_title,
                "channel_id": feed.channel_id,
                "user_id": feed.user_id,
                "video_count": video_count,
                "last_updated": feed.last_updated.isoformat(),
                "newest_video_date": newest_video.published_at.isoformat() if newest_video else None,
                "query_count": feed.query_count,
                "last_queried": feed.last_queried.isoformat() if feed.last_queried else None
            })

        stats["total_videos"] = total_videos

        # Add database file size info
        try:
            db_size = self.storage.db_path.stat().st_size
            stats["database_size_mb"] = round(db_size / (1024 * 1024), 2)
        except:
            stats["database_size_mb"] = 0

        return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Incremental YouTube RSS feed updater with SQLite storage")
    parser.add_argument("--channels", help="Override the CHANNELS environment variable")
    parser.add_argument("--output-directory", help="Directory for generated feeds")
    parser.add_argument("--api-key", help="Override the YT_API_KEY environment variable")
    parser.add_argument("--db-path", help="SQLite database path (defaults to DATABASE_PATH env or feeds.db)")
    parser.add_argument("--loop", action="store_true", help="Continuously refresh feeds")
    parser.add_argument("--interval", type=int, help="Refresh interval in seconds when using --loop")
    parser.add_argument("--log-level", help="Logging verbosity (DEBUG, INFO, WARNING, ERROR)")
    parser.add_argument("--stats", action="store_true", help="Show feed statistics and exit")
    parser.add_argument("--cleanup-days", type=int, help="Remove videos older than N days")
    parser.add_argument("--use-stored-feeds", action="store_true",
                       help="Update feeds from database using their stored API keys (ignores CHANNELS env)")
    parser.add_argument("--discord-webhook", help="Discord webhook URL for notifications")

    args = parser.parse_args()

    # Set up logging including Discord integration
    log_level_name = args.log_level or os.getenv("LOG_LEVEL", "INFO")

    # Override Discord webhook if provided via command line
    if args.discord_webhook:
        os.environ["DISCORD_WEBHOOK_URL"] = args.discord_webhook
        os.environ["LOG_TO_DISCORD"] = "true"

    discord_logger = setup_logging(log_level_name)
    numeric_level = getattr(logging, log_level_name.upper(), logging.INFO)
    logging.basicConfig(level=numeric_level, format="%(asctime)s %(levelname)s %(message)s")

    # Load environment
    load_dotenv()

    # Determine database path
    db_path = args.db_path or os.getenv("DATABASE_PATH", "feeds.db")

    # Create updater
    updater = IncrementalFeedUpdater(db_path)

    # Handle stats command
    if args.stats:
        stats = updater.get_feed_stats()

        # Print to console
        print(f"Total feeds: {stats['total_feeds']}")
        print(f"Total videos: {stats['total_videos']}")
        print()
        for feed_info in stats["feeds"]:
            print(f"{feed_info['channel_title']}: {feed_info['video_count']} videos")
            print(f"  Last updated: {feed_info['last_updated']}")
            if feed_info['newest_video_date']:
                print(f"  Newest video: {feed_info['newest_video_date']}")
            print()

        # Send comprehensive stats to Discord
        discord_logger.report_system_stats(stats)

        # Also send to testing webhook if available
        discord_logger.report_system_stats_to_testing(stats)

        return 0

    # Handle cleanup command
    if args.cleanup_days:
        deleted = updater.storage.cleanup_old_videos(args.cleanup_days)
        print(f"Cleaned up {deleted} videos older than {args.cleanup_days} days")
        return 0

    # Determine output directory
    output_dir_value = args.output_directory or os.getenv("OUTPUT_DIRECTORY", ".")
    base_dir = Path(output_dir_value).expanduser()
    base_dir.mkdir(parents=True, exist_ok=True)

    # Load configuration based on mode
    if args.use_stored_feeds:
        # Use stored feeds mode - feeds are managed via feed_manager.py
        configs = None
        api_key = args.api_key or os.getenv("YT_API_KEY")  # Fallback API key
        # Note: api_key can be None in this mode if all feeds have their own keys
    else:
        # Use legacy .env config mode
        try:
            channels_raw = args.channels if args.channels is not None else os.getenv("CHANNELS", "")
            if not channels_raw.strip():
                raise ValueError("CHANNELS environment variable is empty. Use --use-stored-feeds or set CHANNELS")

            configs = parse_channels_config(channels_raw)
            if not configs:
                raise ValueError("No channels configured")

            api_key = args.api_key or os.getenv("YT_API_KEY")
            if not api_key:
                raise ValueError("YT_API_KEY required for .env config mode")

        except Exception as exc:
            logger.error(f"Configuration error: {exc}")
            logger.info("Hint: Use --use-stored-feeds to update feeds managed via feed_manager.py")
            return 2

    # Handle loop mode
    loop_env = os.getenv("RUN_CONTINUOUSLY")
    loop_from_env = False
    if loop_env is not None:
        try:
            loop_from_env = parse_bool(loop_env, False)
        except ValueError:
            logger.warning(f"Invalid RUN_CONTINUOUSLY value '{loop_env}'. Ignoring.")

    loop = args.loop or loop_from_env
    interval_seconds = args.interval or int(os.getenv("REFRESH_INTERVAL_SECONDS", "3600"))

    # Log system start
    mode = "stored feeds" if args.use_stored_feeds else "env config"
    discord_logger.log_system_start(mode)

    # Run updates
    if not loop:
        if args.use_stored_feeds:
            success = updater.update_all_stored_feeds(base_dir, api_key)
        else:
            success = updater.update_all_feeds(configs, api_key, base_dir)

        # Send daily summary if not in loop mode
        discord_logger.report_daily_summary()

        return 0 if success else 1

    logger.info(f"Entering continuous mode with interval {interval_seconds} seconds")
    exit_code = 0
    try:
        while True:
            start_time = time.time()
            if args.use_stored_feeds:
                success = updater.update_all_stored_feeds(base_dir, api_key)
            else:
                success = updater.update_all_feeds(configs, api_key, base_dir)

            if not success:
                exit_code = 1

            elapsed = time.time() - start_time
            sleep_time = max(0, interval_seconds - elapsed)
            logger.info(f"Update cycle completed in {elapsed:.1f}s, sleeping {sleep_time:.1f}s")
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        logger.info("Received interrupt, stopping updater")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())