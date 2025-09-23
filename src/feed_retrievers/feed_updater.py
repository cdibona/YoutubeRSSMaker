#!/usr/bin/env python3
"""
Feed Updater for YouTube RSS Maker
----------------------------------

Handles updating all feeds with incremental fetching and RSS generation.
"""

import os
import sys
import time
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

sys.path.append(str(Path(__file__).parent.parent))

from database.feed_storage import FeedStorage, StoredFeed, StoredVideo
from discord_interactions.discord_logger import get_logger, FeedReport, APIUsageReport
from .youtube_channel_to_rss import yt_get, fetch_all_playlist_video_ids, fetch_video_details, build_rss, get_uploads_playlist_id, iso8601_duration_to_seconds
import requests


class FeedUpdater:
    """Handles updating all stored feeds with incremental fetching."""

    def __init__(self, db_path: str):
        self.storage = FeedStorage(db_path)
        self.logger = get_logger()

    def update_all_feeds(self, output_directory: str = "./feeds",
                        fallback_api_key: Optional[str] = None,
                        loop: bool = False, interval: int = 3600) -> bool:
        """Update all stored feeds."""

        if loop:
            print(f"Starting continuous update loop (interval: {interval}s)")
            while True:
                success = self._update_feeds_once(output_directory, fallback_api_key)
                if not success:
                    print("Update cycle failed, waiting before retry...")

                print(f"Waiting {interval} seconds until next update...")
                time.sleep(interval)
        else:
            return self._update_feeds_once(output_directory, fallback_api_key)

    def _update_feeds_once(self, output_directory: str, fallback_api_key: Optional[str]) -> bool:
        """Perform one update cycle for all feeds."""

        # Ensure output directory exists
        Path(output_directory).mkdir(parents=True, exist_ok=True)

        feeds = self.storage.get_all_feeds()
        if not feeds:
            print("No feeds found. Add feeds with: python youtube_rss.py add")
            return True

        print(f"Updating {len(feeds)} feeds...")
        success_count = 0
        total_new_videos = 0

        for feed in feeds:
            try:
                api_key = feed.api_key or fallback_api_key
                if not api_key:
                    print(f"Warning: No API key for {feed.channel_title}, skipping")
                    continue

                print(f"Updating {feed.channel_title}...")

                # Get new videos since last update
                new_videos = self._fetch_new_videos(feed, api_key)

                if new_videos:
                    # Store new videos
                    for video_data in new_videos:
                        stored_video = StoredVideo(
                            video_id=video_data['video_id'],
                            channel_id=video_data['channel_id'],
                            title=video_data['title'],
                            description=video_data['description'],
                            published_at=video_data['published_at'],
                            duration_seconds=video_data['duration_seconds'],
                            view_count=video_data['view_count'],
                            like_count=video_data['like_count'],
                            thumbnail_url=video_data['thumbnail_url'],
                            captions=video_data['captions'],
                            first_seen=video_data['first_seen']
                        )
                        self.storage.store_video(stored_video)

                    total_new_videos += len(new_videos)
                    print(f"  Found {len(new_videos)} new videos")
                else:
                    print("  No new videos")

                # Generate RSS from all stored videos
                self._generate_rss_file(feed, output_directory)

                # Update feed metadata
                self.storage.update_feed_last_updated(feed.channel_id)

                success_count += 1

                # Report success
                report = FeedReport(
                    action="update",
                    channel_title=feed.channel_title,
                    channel_id=feed.channel_id,
                    user_id=feed.user_id,
                    videos_processed=len(new_videos),
                    new_videos=len(new_videos),
                    timestamp=datetime.now(timezone.utc),
                    api_usage=self.logger.track_api_usage("videos", 1, feed.channel_id, feed.user_id)
                )
                self.logger.report_feed_operation(report)

            except Exception as e:
                print(f"Error updating {feed.channel_title}: {e}")

                # Report error
                report = FeedReport(
                    action="update",
                    channel_title=feed.channel_title,
                    channel_id=feed.channel_id,
                    user_id=feed.user_id,
                    videos_processed=0,
                    new_videos=0,
                    timestamp=datetime.now(timezone.utc),
                    error=str(e)
                )
                self.logger.report_feed_operation(report)

        print(f"Update complete: {success_count}/{len(feeds)} feeds updated, {total_new_videos} new videos total")

        # Send stats to Discord after update
        try:
            self._send_update_stats_to_discord(feeds, success_count, total_new_videos)
        except Exception as e:
            print(f"Note: Could not send Discord stats: {e}")

        return success_count > 0

    def _fetch_new_videos(self, feed: StoredFeed, api_key: str) -> List[Dict[str, Any]]:
        """Fetch new videos for a feed since last update."""

        # Get existing video IDs to filter out duplicates
        existing_video_ids = set(self.storage.get_video_ids_for_channel(feed.channel_id))

        # Fetch recent videos from YouTube
        with requests.Session() as session:
            try:
                # Get channel uploads playlist
                channel_resource = yt_get(session, "channels", {
                    "key": api_key,
                    "id": feed.channel_id,
                    "part": "contentDetails"
                })

                if not channel_resource.get('items'):
                    return []

                uploads_playlist_id = get_uploads_playlist_id(channel_resource['items'][0])

                # Get recent video IDs from playlist (last 50)
                video_ids = fetch_all_playlist_video_ids(session, api_key, uploads_playlist_id)[:50]

                # Filter to only new videos
                new_video_ids = [vid for vid in video_ids if vid not in existing_video_ids]

                if not new_video_ids:
                    return []

                # Fetch detailed video information
                video_details = fetch_video_details(session, api_key, new_video_ids)

                # Convert to storage format
                new_videos = []
                for video in video_details:
                    video_data = {
                        'video_id': video['id'],
                        'channel_id': feed.channel_id,
                        'title': video['snippet']['title'],
                        'description': video['snippet'].get('description', ''),
                        'published_at': datetime.fromisoformat(video['snippet']['publishedAt'].replace('Z', '+00:00')),
                        'duration_seconds': iso8601_duration_to_seconds(video['contentDetails']['duration']),
                        'view_count': int(video['statistics'].get('viewCount', 0)),
                        'like_count': int(video['statistics'].get('likeCount', 0)),
                        'thumbnail_url': video['snippet']['thumbnails'].get('high', {}).get('url', ''),
                        'captions': '',  # Will be fetched separately if needed
                        'first_seen': datetime.now(timezone.utc)
                    }
                    new_videos.append(video_data)

                return new_videos

            except Exception as e:
                print(f"Error fetching videos for {feed.channel_title}: {e}")
                return []

    def _generate_rss_file(self, feed: StoredFeed, output_directory: str):
        """Generate RSS file from stored videos."""

        # Get all videos for this channel
        videos = self.storage.get_videos_for_channel(feed.channel_id,
                                                   oldest_first=feed.feed_config.get('oldest_first', False))

        # Convert stored videos to RSS format
        rss_videos = []
        for video in videos:
            # Convert StoredVideo to dict format expected by build_rss
            video_dict = {
                'id': video.video_id,
                'snippet': {
                    'title': video.title,
                    'description': video.description,
                    'publishedAt': video.published_at.isoformat(),
                    'thumbnails': {
                        'high': {'url': video.thumbnail_url, 'width': 480, 'height': 360}
                    }
                },
                'contentDetails': {
                    'duration': f"PT{video.duration_seconds}S"
                },
                'statistics': {
                    'viewCount': str(video.view_count or 0),
                    'likeCount': str(video.like_count or 0)
                }
            }
            rss_videos.append(video_dict)

        # Create channel info for RSS
        channel_info = {
            'id': feed.channel_id,
            'snippet': {
                'title': feed.channel_title,
                'description': f"Videos from {feed.channel_title}"
            }
        }

        # Generate RSS content
        rss_content = build_rss(channel_info, rss_videos, f"https://www.youtube.com/channel/{feed.channel_id}")

        # Write RSS file
        output_file = Path(output_directory) / self._get_output_filename(feed)
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(rss_content)

    def _get_output_filename(self, feed: StoredFeed) -> str:
        """Get output filename for a feed."""
        # Try to get from feed config first
        if 'output_filename' in feed.feed_config:
            return feed.feed_config['output_filename']

        # Generate from channel title
        import re
        clean_title = re.sub(r'[^\w\s-]', '', feed.channel_title)
        clean_title = re.sub(r'[-\s]+', '-', clean_title)
        return f"{clean_title.lower()}.xml"

    def show_stats(self, send_to_discord: bool = False):
        """Show feed statistics."""

        feeds = self.storage.get_all_feeds()
        total_videos = sum(self.storage.get_video_count_for_channel(f.channel_id) for f in feeds)

        print(f"Total feeds: {len(feeds)}")
        print(f"Total videos: {total_videos}")
        print()

        for feed in feeds:
            video_count = self.storage.get_video_count_for_channel(feed.channel_id)
            last_updated = feed.last_updated.strftime('%Y-%m-%d %H:%M:%S') if feed.last_updated else 'Never'

            print(f"{feed.channel_title}: {video_count} videos")
            print(f"  Last updated: {last_updated}")
            print(f"  User: {feed.user_id}")

            # Get newest video
            videos = self.storage.get_videos_for_channel(feed.channel_id, limit=1)
            if videos:
                newest = videos[0].published_at.strftime('%Y-%m-%d %H:%M:%S')
                print(f"  Newest video: {newest}")
            print()

        # Optionally send stats to Discord
        if send_to_discord:
            try:
                print("Sending stats to Discord...")
                self._send_update_stats_to_discord(feeds, len(feeds), 0)
                print("✓ Stats sent to Discord testing channel")
            except Exception as e:
                print(f"✗ Error sending stats to Discord: {e}")

    def cleanup_old_videos(self, days: int) -> bool:
        """Remove videos older than specified days."""

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        try:
            removed_count = self.storage.cleanup_old_videos(cutoff_date)
            print(f"Removed {removed_count} videos older than {days} days")
            return True
        except Exception as e:
            print(f"Error during cleanup: {e}")
            return False

    def _send_update_stats_to_discord(self, feeds: List[StoredFeed], success_count: int, total_new_videos: int):
        """Send update statistics to Discord testing webhook."""

        # Prepare stats data in the format expected by discord_logger
        feeds_data = []
        total_videos = 0

        for feed in feeds:
            video_count = self.storage.get_video_count_for_channel(feed.channel_id)
            total_videos += video_count

            feeds_data.append({
                "channel_title": feed.channel_title,
                "channel_id": feed.channel_id,
                "user_id": feed.user_id,
                "video_count": video_count,
                "last_updated": feed.last_updated.isoformat() if feed.last_updated else None,
                "query_count": getattr(feed, 'query_count', 0)
            })

        stats_data = {
            "total_feeds": len(feeds),
            "total_videos": total_videos,
            "feeds": feeds_data,
            "update_summary": {
                "successful_feeds": success_count,
                "total_feeds": len(feeds),
                "new_videos_found": total_new_videos,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        }

        # Send to testing webhook (stats channel)
        self.logger.report_system_stats_to_testing(stats_data)