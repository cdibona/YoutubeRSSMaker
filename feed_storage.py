#!/usr/bin/env python3
"""
Feed Storage System for YouTube RSS Maker
-----------------------------------------

SQLite-based storage system that:
- Stores feed metadata and video items
- Tracks last update times for incremental fetching
- Deduplicates video items by video ID
- Provides efficient querying for new items only
"""

import sqlite3
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class StoredFeed:
    """Represents a stored feed configuration."""
    channel_id: str
    channel_identifier: str  # Original input (@handle, URL, etc.)
    channel_title: str
    last_updated: datetime
    last_video_count: int
    feed_config: Dict  # Store caption settings, etc.
    user_id: str = "DefaultUser"
    api_key: Optional[str] = None
    query_count: int = 0
    last_queried: Optional[datetime] = None


@dataclass
class StoredVideo:
    """Represents a stored video item."""
    video_id: str
    channel_id: str
    title: str
    description: str
    published_at: datetime
    duration_seconds: int
    view_count: Optional[int]
    like_count: Optional[int]
    thumbnail_url: str
    captions: Optional[str]
    first_seen: datetime  # When we first discovered this video


class FeedStorage:
    """SQLite-based storage for YouTube feed data."""

    def __init__(self, db_path: str = "feeds.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _init_database(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            # Create feeds table with user support and query tracking
            conn.execute("""
                CREATE TABLE IF NOT EXISTS feeds (
                    channel_id TEXT PRIMARY KEY,
                    channel_identifier TEXT NOT NULL,
                    channel_title TEXT NOT NULL,
                    last_updated TEXT NOT NULL,
                    last_video_count INTEGER NOT NULL DEFAULT 0,
                    feed_config TEXT NOT NULL DEFAULT '{}',
                    user_id TEXT NOT NULL DEFAULT 'DefaultUser',
                    api_key TEXT,
                    query_count INTEGER NOT NULL DEFAULT 0,
                    last_queried TEXT
                )
            """)

            # Add user_id and api_key columns to existing feeds table if they don't exist
            try:
                conn.execute("ALTER TABLE feeds ADD COLUMN user_id TEXT NOT NULL DEFAULT 'DefaultUser'")
            except sqlite3.OperationalError:
                pass  # Column already exists

            try:
                conn.execute("ALTER TABLE feeds ADD COLUMN api_key TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists

            # Add query tracking columns to existing feeds table if they don't exist
            try:
                conn.execute("ALTER TABLE feeds ADD COLUMN query_count INTEGER NOT NULL DEFAULT 0")
            except sqlite3.OperationalError:
                pass  # Column already exists

            try:
                conn.execute("ALTER TABLE feeds ADD COLUMN last_queried TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists

            conn.execute("""
                CREATE TABLE IF NOT EXISTS videos (
                    video_id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    published_at TEXT NOT NULL,
                    duration_seconds INTEGER NOT NULL DEFAULT 0,
                    view_count INTEGER,
                    like_count INTEGER,
                    thumbnail_url TEXT,
                    captions TEXT,
                    first_seen TEXT NOT NULL,
                    FOREIGN KEY (channel_id) REFERENCES feeds (channel_id)
                )
            """)

            # Index for efficient querying
            conn.execute("CREATE INDEX IF NOT EXISTS idx_videos_channel_published ON videos (channel_id, published_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_videos_first_seen ON videos (first_seen)")

            conn.commit()

    def register_feed(self, channel_id: str, channel_identifier: str, channel_title: str,
                     feed_config: Optional[Dict] = None, user_id: str = "DefaultUser",
                     api_key: Optional[str] = None) -> StoredFeed:
        """Register or update a feed configuration."""
        now = datetime.now(timezone.utc)
        config = feed_config or {}

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO feeds
                (channel_id, channel_identifier, channel_title, last_updated, last_video_count, feed_config, user_id, api_key)
                VALUES (?, ?, ?, ?, 0, ?, ?, ?)
            """, (channel_id, channel_identifier, channel_title, now.isoformat(), json.dumps(config), user_id, api_key))
            conn.commit()

        return StoredFeed(
            channel_id=channel_id,
            channel_identifier=channel_identifier,
            channel_title=channel_title,
            last_updated=now,
            last_video_count=0,
            feed_config=config,
            user_id=user_id,
            api_key=api_key
        )

    def get_feed(self, channel_id: str, increment_counter: bool = True) -> Optional[StoredFeed]:
        """Get feed information by channel ID."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("""
                SELECT channel_id, channel_identifier, channel_title, last_updated, last_video_count,
                       feed_config, user_id, api_key, query_count, last_queried
                FROM feeds WHERE channel_id = ?
            """, (channel_id,)).fetchone()

            if not row:
                return None

            # Increment query counter if requested
            if increment_counter:
                now = datetime.now(timezone.utc)
                conn.execute("""
                    UPDATE feeds
                    SET query_count = query_count + 1, last_queried = ?
                    WHERE channel_id = ?
                """, (now.isoformat(), channel_id))
                conn.commit()

                query_count = (row[8] or 0) + 1
                last_queried = now
            else:
                query_count = row[8] or 0
                last_queried = datetime.fromisoformat(row[9]) if row[9] else None

            return StoredFeed(
                channel_id=row[0],
                channel_identifier=row[1],
                channel_title=row[2],
                last_updated=datetime.fromisoformat(row[3]),
                last_video_count=row[4],
                feed_config=json.loads(row[5]),
                user_id=row[6] if row[6] is not None else "DefaultUser",
                api_key=row[7],
                query_count=query_count,
                last_queried=last_queried
            )

    def store_videos(self, channel_id: str, videos: List[Dict]) -> Tuple[int, int]:
        """
        Store videos for a channel.
        Returns (new_videos_count, total_videos_count).
        """
        now = datetime.now(timezone.utc)
        new_count = 0

        with sqlite3.connect(self.db_path) as conn:
            for video in videos:
                video_id = video["id"]
                snippet = video["snippet"]
                content_details = video.get("contentDetails", {})
                statistics = video.get("statistics", {})

                # Parse published date
                published_str = snippet.get("publishedAt", "")
                try:
                    published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                except ValueError:
                    published_at = now

                # Extract duration
                duration_iso = content_details.get("duration", "PT0S")
                duration_seconds = self._iso8601_duration_to_seconds(duration_iso)

                # Get best thumbnail
                thumbnails = snippet.get("thumbnails", {})
                thumbnail_url = self._get_best_thumbnail_url(thumbnails)

                # Check if video already exists
                existing = conn.execute(
                    "SELECT video_id FROM videos WHERE video_id = ?",
                    (video_id,)
                ).fetchone()

                if not existing:
                    new_count += 1
                    first_seen = now
                else:
                    # Get existing first_seen
                    first_seen_row = conn.execute(
                        "SELECT first_seen FROM videos WHERE video_id = ?",
                        (video_id,)
                    ).fetchone()
                    first_seen = datetime.fromisoformat(first_seen_row[0]) if first_seen_row else now

                # Insert or update video
                conn.execute("""
                    INSERT OR REPLACE INTO videos
                    (video_id, channel_id, title, description, published_at, duration_seconds,
                     view_count, like_count, thumbnail_url, captions, first_seen)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    video_id,
                    channel_id,
                    snippet.get("title", ""),
                    snippet.get("description", ""),
                    published_at.isoformat(),
                    duration_seconds,
                    statistics.get("viewCount"),
                    statistics.get("likeCount"),
                    thumbnail_url,
                    video.get("captions"),
                    first_seen.isoformat()
                ))

            # Update feed last_updated and video count
            total_count = conn.execute(
                "SELECT COUNT(*) FROM videos WHERE channel_id = ?",
                (channel_id,)
            ).fetchone()[0]

            conn.execute("""
                UPDATE feeds
                SET last_updated = ?, last_video_count = ?
                WHERE channel_id = ?
            """, (now.isoformat(), total_count, channel_id))

            conn.commit()

        return new_count, total_count

    def get_videos_since(self, channel_id: str, since: Optional[datetime] = None) -> List[StoredVideo]:
        """Get videos for a channel since a specific time (or all if since=None)."""
        with sqlite3.connect(self.db_path) as conn:
            if since:
                rows = conn.execute("""
                    SELECT video_id, channel_id, title, description, published_at,
                           duration_seconds, view_count, like_count, thumbnail_url, captions, first_seen
                    FROM videos
                    WHERE channel_id = ? AND published_at > ?
                    ORDER BY published_at DESC
                """, (channel_id, since.isoformat())).fetchall()
            else:
                rows = conn.execute("""
                    SELECT video_id, channel_id, title, description, published_at,
                           duration_seconds, view_count, like_count, thumbnail_url, captions, first_seen
                    FROM videos
                    WHERE channel_id = ?
                    ORDER BY published_at DESC
                """, (channel_id,)).fetchall()

            return [StoredVideo(
                video_id=row[0],
                channel_id=row[1],
                title=row[2],
                description=row[3],
                published_at=datetime.fromisoformat(row[4]),
                duration_seconds=row[5],
                view_count=row[6],
                like_count=row[7],
                thumbnail_url=row[8],
                captions=row[9],
                first_seen=datetime.fromisoformat(row[10])
            ) for row in rows]

    def get_new_videos_since_last_update(self, channel_id: str) -> List[StoredVideo]:
        """Get videos that are new since the last feed update."""
        feed = self.get_feed(channel_id, increment_counter=False)
        if not feed:
            return []

        return self.get_videos_since(channel_id, feed.last_updated)

    def get_all_feeds(self) -> List[StoredFeed]:
        """Get all registered feeds."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("""
                SELECT channel_id, channel_identifier, channel_title, last_updated, last_video_count,
                       feed_config, user_id, api_key, query_count, last_queried
                FROM feeds
                ORDER BY channel_title
            """).fetchall()

            return [StoredFeed(
                channel_id=row[0],
                channel_identifier=row[1],
                channel_title=row[2],
                last_updated=datetime.fromisoformat(row[3]),
                last_video_count=row[4],
                feed_config=json.loads(row[5]),
                user_id=row[6] if row[6] is not None else "DefaultUser",
                api_key=row[7],
                query_count=row[8] or 0,
                last_queried=datetime.fromisoformat(row[9]) if row[9] else None
            ) for row in rows]

    def get_feeds_by_user(self, user_id: str) -> List[StoredFeed]:
        """Get all feeds for a specific user."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("""
                SELECT channel_id, channel_identifier, channel_title, last_updated, last_video_count,
                       feed_config, user_id, api_key, query_count, last_queried
                FROM feeds
                WHERE user_id = ?
                ORDER BY channel_title
            """, (user_id,)).fetchall()

            return [StoredFeed(
                channel_id=row[0],
                channel_identifier=row[1],
                channel_title=row[2],
                last_updated=datetime.fromisoformat(row[3]),
                last_video_count=row[4],
                feed_config=json.loads(row[5]),
                user_id=row[6],
                api_key=row[7],
                query_count=row[8] or 0,
                last_queried=datetime.fromisoformat(row[9]) if row[9] else None
            ) for row in rows]

    def remove_feed(self, channel_id: str) -> bool:
        """Remove a feed and all its videos."""
        with sqlite3.connect(self.db_path) as conn:
            # Remove videos first
            conn.execute("DELETE FROM videos WHERE channel_id = ?", (channel_id,))

            # Remove feed
            result = conn.execute("DELETE FROM feeds WHERE channel_id = ?", (channel_id,))
            conn.commit()

            return result.rowcount > 0

    def cleanup_old_videos(self, days: int = 365) -> int:
        """Remove videos older than specified days. Returns count of removed videos."""
        cutoff = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff = cutoff.replace(day=cutoff.day - days)

        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute("""
                DELETE FROM videos
                WHERE published_at < ?
            """, (cutoff.isoformat(),))

            deleted_count = result.rowcount
            conn.commit()

            logger.info(f"Cleaned up {deleted_count} videos older than {days} days")
            return deleted_count

    def _iso8601_duration_to_seconds(self, iso_dur: str) -> int:
        """Convert ISO 8601 duration (e.g., PT1H2M3S) to seconds."""
        import re
        pattern = re.compile(
            r"^P(?:(?P<years>\d+)Y)?(?:(?P<months>\d+)M)?(?:(?P<weeks>\d+)W)?(?:(?P<days>\d+)D)?"
            r"(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
        )
        m = pattern.match(iso_dur)
        if not m:
            return 0
        parts = {k: int(v) if v else 0 for k, v in m.groupdict().items()}
        total = (
            parts["weeks"] * 7 * 24 * 3600
            + parts["days"] * 24 * 3600
            + parts["hours"] * 3600
            + parts["minutes"] * 60
            + parts["seconds"]
        )
        return total

    def _get_best_thumbnail_url(self, thumbs: Dict) -> str:
        """Get the best available thumbnail URL."""
        if not thumbs:
            return ""
        order = ["maxres", "standard", "high", "medium", "default"]
        for k in order:
            if k in thumbs:
                return thumbs[k].get("url", "")
        # Fallback to first available
        k, t = next(iter(thumbs.items()))
        return t.get("url", "")