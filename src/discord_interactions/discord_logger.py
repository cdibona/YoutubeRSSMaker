#!/usr/bin/env python3
"""
Discord Webhook Logger for YouTube RSS Maker
--------------------------------------------

Provides Discord webhook integration for logging and notifications:
- Structured logging with info/debug/error levels
- Discord webhook notifications
- Feed operation tracking
- API usage reporting
- Rich formatting for Discord messages
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
from pathlib import Path

import requests


@dataclass
class APIUsageReport:
    """Tracks YouTube API usage statistics."""
    endpoint: str
    requests_made: int
    quota_cost: int
    timestamp: datetime
    channel_id: Optional[str] = None
    user_id: Optional[str] = None


@dataclass
class FeedReport:
    """Reports on feed operations."""
    action: str  # "add", "update", "remove"
    channel_title: str
    channel_id: str
    user_id: str
    videos_processed: int
    new_videos: int
    timestamp: datetime
    api_usage: Optional[APIUsageReport] = None
    error: Optional[str] = None


class DiscordLogger:
    """Enhanced logger with Discord webhook support."""

    # YouTube API quota costs per endpoint
    API_QUOTA_COSTS = {
        "search": 100,
        "channels": 1,
        "playlistItems": 1,
        "videos": 1
    }

    def __init__(self, webhook_url: Optional[str] = None,
                 log_to_discord: bool = False,
                 discord_log_level: str = "INFO",
                 testing_webhook_url: Optional[str] = None,
                 developer_webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url
        self.testing_webhook_url = testing_webhook_url
        self.developer_webhook_url = developer_webhook_url
        self.log_to_discord = log_to_discord
        self.discord_log_level = getattr(logging, discord_log_level.upper(), logging.INFO)

        # Set up local logger
        self.logger = logging.getLogger("youtube_rss")

        # Track API usage in memory
        self.api_usage_today = []
        self.session_start = datetime.now(timezone.utc)

    def _send_discord_message(self, content: str, embeds: Optional[list] = None,
                             use_testing_webhook: bool = False, use_developer_webhook: bool = False) -> bool:
        """Send message to Discord webhook."""
        if use_developer_webhook:
            webhook_url = self.developer_webhook_url
        elif use_testing_webhook:
            webhook_url = self.testing_webhook_url
        else:
            webhook_url = self.webhook_url

        if not webhook_url:
            return False

        payload = {"content": content}
        if embeds:
            payload["embeds"] = embeds

        try:
            response = requests.post(
                webhook_url,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            return True
        except Exception as e:
            # Don't log Discord errors to avoid recursion, just print
            print(f"Discord webhook error: {e}")
            return False

    def _create_embed(self, title: str, description: str, color: int,
                     fields: Optional[list] = None) -> Dict[str, Any]:
        """Create Discord embed object."""
        embed = {
            "title": title,
            "description": description,
            "color": color,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": "YouTube RSS Maker"}
        }

        if fields:
            embed["fields"] = fields

        return embed

    def log_info(self, message: str, discord_message: Optional[str] = None):
        """Log info message."""
        self.logger.info(message)

        # Send to developer webhook if available, otherwise main webhook
        if self.developer_webhook_url and self.discord_log_level <= logging.INFO:
            discord_content = discord_message or f"ℹ️ **INFO**: {message}"
            self._send_discord_message(discord_content, use_developer_webhook=True)
        elif self.log_to_discord and self.discord_log_level <= logging.INFO:
            discord_content = discord_message or f"ℹ️ **INFO**: {message}"
            self._send_discord_message(discord_content)

    def log_debug(self, message: str, discord_message: Optional[str] = None):
        """Log debug message."""
        self.logger.debug(message)

        # Send to developer webhook if available, otherwise main webhook
        if self.developer_webhook_url and self.discord_log_level <= logging.DEBUG:
            discord_content = discord_message or f"🔍 **DEBUG**: {message}"
            self._send_discord_message(discord_content, use_developer_webhook=True)
        elif self.log_to_discord and self.discord_log_level <= logging.DEBUG:
            discord_content = discord_message or f"🔍 **DEBUG**: {message}"
            self._send_discord_message(discord_content)

    def log_error(self, message: str, discord_message: Optional[str] = None):
        """Log error message."""
        self.logger.error(message)

        # Send to developer webhook if available, otherwise main webhook
        if self.developer_webhook_url and self.discord_log_level <= logging.ERROR:
            discord_content = discord_message or f"❌ **ERROR**: {message}"
            self._send_discord_message(discord_content, use_developer_webhook=True)
        elif self.log_to_discord and self.discord_log_level <= logging.ERROR:
            discord_content = discord_message or f"❌ **ERROR**: {message}"
            self._send_discord_message(discord_content)

    def track_api_usage(self, endpoint: str, requests_made: int = 1,
                       channel_id: Optional[str] = None,
                       user_id: Optional[str] = None) -> APIUsageReport:
        """Track YouTube API usage."""
        quota_cost = self.API_QUOTA_COSTS.get(endpoint, 1) * requests_made

        report = APIUsageReport(
            endpoint=endpoint,
            requests_made=requests_made,
            quota_cost=quota_cost,
            timestamp=datetime.now(timezone.utc),
            channel_id=channel_id,
            user_id=user_id
        )

        self.api_usage_today.append(report)
        return report

    def get_daily_api_usage(self) -> Dict[str, Any]:
        """Get today's API usage statistics."""
        today = datetime.now(timezone.utc).date()
        today_usage = [u for u in self.api_usage_today
                      if u.timestamp.date() == today]

        total_requests = sum(u.requests_made for u in today_usage)
        total_quota = sum(u.quota_cost for u in today_usage)

        by_endpoint = {}
        for usage in today_usage:
            endpoint = usage.endpoint
            if endpoint not in by_endpoint:
                by_endpoint[endpoint] = {"requests": 0, "quota": 0}
            by_endpoint[endpoint]["requests"] += usage.requests_made
            by_endpoint[endpoint]["quota"] += usage.quota_cost

        return {
            "date": today.isoformat(),
            "total_requests": total_requests,
            "total_quota_used": total_quota,
            "by_endpoint": by_endpoint,
            "session_start": self.session_start.isoformat()
        }

    def report_feed_operation(self, report: FeedReport):
        """Report on feed operation with rich Discord embed."""
        # Log locally
        action_msg = f"Feed {report.action}: {report.channel_title} (user: {report.user_id})"
        if report.error:
            self.log_error(f"{action_msg} - Error: {report.error}")
        else:
            self.log_info(f"{action_msg} - {report.new_videos} new videos")

        # Send to Discord if enabled
        if not self.log_to_discord:
            return

        # Choose color based on action and success
        if report.error:
            color = 0xFF0000  # Red for errors
            status_icon = "❌"
        elif report.action == "add":
            color = 0x00FF00  # Green for new feeds
            status_icon = "➕"
        elif report.action == "update":
            color = 0x0099FF  # Blue for updates
            status_icon = "🔄"
        elif report.action == "remove":
            color = 0xFF9900  # Orange for removals
            status_icon = "➖"
        else:
            color = 0x888888  # Gray for other actions
            status_icon = "ℹ️"

        # Create compact fields (fewer rows, more columns)
        if report.error:
            description = f"**{report.channel_title}** • User: {report.user_id} • **Error**: {report.error}"
            fields = []
        else:
            # Compact success format
            video_info = f"{report.new_videos} new" if report.new_videos > 0 else "no new videos"
            api_info = f" • {report.api_usage.quota_cost} quota" if report.api_usage else ""
            description = f"**{report.channel_title}** • User: {report.user_id} • {video_info} ({report.videos_processed} processed){api_info}"
            fields = []

        embed = self._create_embed(
            title=f"{status_icon} Feed {report.action.title()}",
            description=description,
            color=color,
            fields=fields
        )

        self._send_discord_message("", [embed])

    def report_daily_summary(self):
        """Send daily API usage summary to Discord."""
        if not self.log_to_discord:
            return

        usage = self.get_daily_api_usage()

        # Create summary message
        fields = [
            {"name": "Total Requests", "value": str(usage["total_requests"]), "inline": True},
            {"name": "Quota Used", "value": f"{usage['total_quota_used']} / 10,000", "inline": True},
            {"name": "Session Duration", "value": self._format_duration(), "inline": True}
        ]

        # Add per-endpoint breakdown
        for endpoint, stats in usage["by_endpoint"].items():
            fields.append({
                "name": f"{endpoint.title()} API",
                "value": f"{stats['requests']} requests ({stats['quota']} quota)",
                "inline": True
            })

        embed = self._create_embed(
            title="📊 Daily API Usage Summary",
            description=f"Usage report for {usage['date']}",
            color=0x00AA00,
            fields=fields
        )

        self._send_discord_message("", [embed])

    def report_system_stats(self, stats_data: Dict[str, Any]):
        """Send comprehensive system statistics to Discord."""
        if not self.log_to_discord:
            return

        total_feeds = stats_data.get("total_feeds", 0)
        total_videos = stats_data.get("total_videos", 0)
        feeds = stats_data.get("feeds", [])

        # Compact main stats - fewer fields, more info per field
        main_fields = []

        # Core stats in one field
        db_size = stats_data.get("database_size_mb", 0)
        db_info = f" • {db_size} MB DB" if db_size > 0 else ""
        core_stats = f"📺 {total_feeds} feeds • 🎬 {total_videos:,} videos{db_info}"
        main_fields.append({"name": "System Overview", "value": core_stats, "inline": False})

        # Query statistics
        total_queries = sum(feed.get("query_count", 0) for feed in feeds)
        if total_queries > 0:
            avg_queries = total_queries / total_feeds if total_feeds > 0 else 0
            query_stats = f"🔍 {total_queries:,} total queries • 📊 {avg_queries:.1f} avg/feed"
            main_fields.append({"name": "Query Statistics", "value": query_stats, "inline": False})

        # API usage info
        usage = self.get_daily_api_usage()
        if usage["total_requests"] > 0:
            quota_percentage = (usage["total_quota_used"] / 10000) * 100
            efficiency = f"{total_videos}/{usage['total_requests']}" if usage['total_requests'] > 0 else "N/A"
            api_stats = f"🔧 {usage['total_requests']} requests • 📊 {usage['total_quota_used']}/10,000 quota ({quota_percentage:.1f}%) • 📈 {efficiency} videos/req"
            main_fields.append({"name": "API Usage Today", "value": api_stats, "inline": False})

        # Session info
        session_info = f"⏱️ Session: {self._format_duration()}"
        main_fields.append({"name": "Runtime", "value": session_info, "inline": False})

        main_embed = self._create_embed(
            title="📊 YouTube RSS System Statistics",
            description=f"Complete system overview as of {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            color=0x0099FF,
            fields=main_fields
        )

        embeds = [main_embed]

        # Feed details embed (if we have feeds)
        if feeds:
            feed_fields = []

            # Sort feeds by video count (descending) and take top 10
            sorted_feeds = sorted(feeds, key=lambda x: x.get("video_count", 0), reverse=True)
            top_feeds = sorted_feeds[:10]

            for i, feed in enumerate(top_feeds, 1):
                channel_title = feed.get("channel_title", "Unknown")
                video_count = feed.get("video_count", 0)
                last_updated = feed.get("last_updated", "")
                newest_video = feed.get("newest_video_date", "")
                query_count = feed.get("query_count", 0)
                last_queried = feed.get("last_queried", "")

                # Format last updated time
                try:
                    updated_dt = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
                    time_ago = self._format_time_ago(updated_dt)
                except:
                    time_ago = "Unknown"

                # Format newest video time
                newest_info = ""
                if newest_video:
                    try:
                        newest_dt = datetime.fromisoformat(newest_video.replace('Z', '+00:00'))
                        newest_ago = self._format_time_ago(newest_dt)
                        newest_info = f"\n🎬 Latest: {newest_ago}"
                    except:
                        pass

                # Format query info
                query_info = f"\n🔍 Queries: {query_count}"
                if last_queried:
                    try:
                        queried_dt = datetime.fromisoformat(last_queried.replace('Z', '+00:00'))
                        queried_ago = self._format_time_ago(queried_dt)
                        query_info += f" (last: {queried_ago})"
                    except:
                        pass

                feed_fields.append({
                    "name": f"{i}. {channel_title}",
                    "value": f"📊 {video_count:,} videos\n🔄 Updated: {time_ago}{newest_info}{query_info}",
                    "inline": True
                })

            feed_embed = self._create_embed(
                title="🎯 Top Feeds by Video Count",
                description=f"Showing top {len(top_feeds)} feeds out of {total_feeds} total",
                color=0x00AA00,
                fields=feed_fields
            )
            embeds.append(feed_embed)

        # User statistics embed
        if feeds:
            user_stats = {}
            for feed in feeds:
                user_id = feed.get("user_id", "Unknown")
                if user_id not in user_stats:
                    user_stats[user_id] = {"feeds": 0, "videos": 0}
                user_stats[user_id]["feeds"] += 1
                user_stats[user_id]["videos"] += feed.get("video_count", 0)

            if len(user_stats) > 1:  # Only show if multiple users
                user_fields = []
                for user_id, stats in sorted(user_stats.items(), key=lambda x: x[1]["videos"], reverse=True):
                    user_fields.append({
                        "name": f"👤 {user_id}",
                        "value": f"{stats['feeds']} feeds, {stats['videos']:,} videos",
                        "inline": True
                    })

                user_embed = self._create_embed(
                    title="👥 User Statistics",
                    description=f"Breakdown by {len(user_stats)} users",
                    color=0xFF9900,
                    fields=user_fields
                )
                embeds.append(user_embed)

        # System health and analytics embed
        if feeds:
            health_fields = []

            # Calculate freshness metrics
            now = datetime.now(timezone.utc)
            fresh_feeds = 0  # Updated in last 24 hours
            stale_feeds = 0  # Not updated in last 7 days

            for feed in feeds:
                try:
                    last_updated = datetime.fromisoformat(feed.get("last_updated", "").replace('Z', '+00:00'))
                    if (now - last_updated).days < 1:
                        fresh_feeds += 1
                    elif (now - last_updated).days > 7:
                        stale_feeds += 1
                except:
                    pass

            health_fields.extend([
                {"name": "🟢 Fresh Feeds", "value": f"{fresh_feeds} (updated <24h)", "inline": True},
                {"name": "🟡 Stale Feeds", "value": f"{stale_feeds} (>7 days old)", "inline": True}
            ])

            # Calculate video density
            if total_feeds > 0:
                avg_videos = total_videos / total_feeds
                health_fields.append({
                    "name": "📊 Avg Videos/Feed",
                    "value": f"{avg_videos:.1f}",
                    "inline": True
                })

            # Most/least active channels
            if len(feeds) > 1:
                most_active = max(feeds, key=lambda x: x.get("video_count", 0))
                least_active = min(feeds, key=lambda x: x.get("video_count", 0))

                health_fields.extend([
                    {"name": "🥇 Most Active", "value": f"{most_active.get('channel_title', 'Unknown')} ({most_active.get('video_count', 0):,} videos)", "inline": False},
                    {"name": "🎯 Least Active", "value": f"{least_active.get('channel_title', 'Unknown')} ({least_active.get('video_count', 0):,} videos)", "inline": False}
                ])

            health_embed = self._create_embed(
                title="🔍 System Health & Analytics",
                description="Feed freshness and activity metrics",
                color=0x9932CC,
                fields=health_fields
            )
            embeds.append(health_embed)

        # Send all embeds
        self._send_discord_message("", embeds)

    def report_system_stats_to_testing(self, stats_data: Dict[str, Any]):
        """Send system stats to testing webhook."""
        if not self.testing_webhook_url:
            return

        # Reuse the same logic but send to testing webhook
        total_feeds = stats_data.get("total_feeds", 0)
        total_videos = stats_data.get("total_videos", 0)
        feeds = stats_data.get("feeds", [])

        # Main stats embed
        main_fields = [
            {"name": "📺 Total Feeds", "value": str(total_feeds), "inline": True},
            {"name": "🎬 Total Videos", "value": f"{total_videos:,}", "inline": True},
            {"name": "⏱️ Session Duration", "value": self._format_duration(), "inline": True}
        ]

        # Add database size if available
        db_size = stats_data.get("database_size_mb", 0)
        if db_size > 0:
            main_fields.append({"name": "💾 Database Size", "value": f"{db_size} MB", "inline": True})

        # Add query statistics
        total_queries = sum(feed.get("query_count", 0) for feed in feeds)
        if total_queries > 0:
            avg_queries = total_queries / total_feeds if total_feeds > 0 else 0
            main_fields.extend([
                {"name": "🔍 Total Queries", "value": f"{total_queries:,}", "inline": True},
                {"name": "📊 Avg Queries/Feed", "value": f"{avg_queries:.1f}", "inline": True}
            ])

        main_embed = self._create_embed(
            title="🧪 Testing - YouTube RSS System Statistics",
            description=f"Testing webhook report - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            color=0xFF6B35,  # Orange color to distinguish testing reports
            fields=main_fields
        )

        self._send_discord_message("", [main_embed], use_testing_webhook=True)

    def _format_time_ago(self, dt: datetime) -> str:
        """Format datetime as time ago string."""
        now = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        diff = now - dt
        days = diff.days
        hours = diff.seconds // 3600
        minutes = (diff.seconds % 3600) // 60

        if days > 0:
            return f"{days}d ago"
        elif hours > 0:
            return f"{hours}h ago"
        elif minutes > 0:
            return f"{minutes}m ago"
        else:
            return "Just now"

    def _format_duration(self) -> str:
        """Format session duration in human-readable format."""
        duration = datetime.now(timezone.utc) - self.session_start
        hours = int(duration.total_seconds() // 3600)
        minutes = int((duration.total_seconds() % 3600) // 60)

        if hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"

    def log_system_start(self, mode: str):
        """Log system startup."""
        self.log_info(f"YouTube RSS Maker started in {mode} mode")

        if self.log_to_discord:
            embed = self._create_embed(
                title="🚀 System Started",
                description=f"YouTube RSS Maker initialized in **{mode}** mode",
                color=0x00FF00,
                fields=[
                    {"name": "Mode", "value": mode, "inline": True},
                    {"name": "Start Time", "value": self.session_start.strftime("%Y-%m-%d %H:%M:%S UTC"), "inline": True}
                ]
            )
            self._send_discord_message("", [embed])


# Global logger instance
_logger_instance = None


def get_logger() -> DiscordLogger:
    """Get or create the global Discord logger instance."""
    global _logger_instance

    if _logger_instance is None:
        # Load configuration from environment
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
        testing_webhook_url = os.getenv("DISCORD_TESTING_WEBHOOK_URL")
        developer_webhook_url = os.getenv("DISCORD_DEVELOPER_WEBHOOK_URL")
        log_to_discord = os.getenv("LOG_TO_DISCORD", "false").lower() == "true"
        discord_log_level = os.getenv("DISCORD_LOG_LEVEL", "INFO")

        _logger_instance = DiscordLogger(
            webhook_url=webhook_url,
            log_to_discord=log_to_discord and bool(webhook_url),
            discord_log_level=discord_log_level,
            testing_webhook_url=testing_webhook_url,
            developer_webhook_url=developer_webhook_url
        )

    return _logger_instance


def setup_logging(log_level: str = "INFO"):
    """Set up logging configuration."""
    # Configure Python logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Initialize Discord logger
    logger = get_logger()
    return logger