#!/usr/bin/env python3
"""Batch updater for YouTube RSS feeds defined in a .env file."""

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from dotenv import load_dotenv

from youtube_channel_to_rss import FeedResult, generate_feed_for_channel


@dataclass
class ChannelConfig:
    channel: str
    output: str
    include_captions: bool = False
    caption_language: str = "en"
    allow_generated_captions: bool = False
    oldest_first: bool = False
    channel_url: Optional[str] = None

    def resolved_path(self, base_directory: Path) -> Path:
        path = Path(self.output).expanduser()
        if not path.is_absolute():
            path = base_directory / path
        return path


def slugify_channel(channel: str) -> str:
    """Create a default filename from a channel identifier."""
    sanitized = re.sub(r"[^A-Za-z0-9]+", "-", channel.strip())
    sanitized = sanitized.strip("-") or "feed"
    return f"{sanitized}.xml"


def parse_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "f", "no", "n", "off"}:
        return False
    raise ValueError(f"Cannot interpret boolean value from '{value}'.")


def parse_channels_config(raw: str) -> List[ChannelConfig]:
    raw = (raw or "").strip()
    if not raw:
        return []

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return _parse_simple_channels(raw)

    if not isinstance(parsed, list):
        raise ValueError("CHANNELS must be a JSON array or a newline/comma separated list of 'channel>output' pairs.")

    configs: List[ChannelConfig] = []
    for entry in parsed:
        if isinstance(entry, str):
            channel = entry.strip()
            if not channel:
                continue
            configs.append(ChannelConfig(channel=channel, output=slugify_channel(channel)))
            continue
        if not isinstance(entry, dict):
            raise ValueError("Each entry in CHANNELS must be an object with at least a 'channel' key or a plain string.")

        channel_value = (entry.get("channel") or entry.get("id") or "").strip()
        if not channel_value:
            raise ValueError("Channel entry missing 'channel' field.")

        output_value = (entry.get("output") or entry.get("filename") or entry.get("file") or "").strip()
        if not output_value:
            output_value = slugify_channel(channel_value)

        include_captions = parse_bool(entry.get("include_captions"), False)
        allow_generated = parse_bool(entry.get("allow_generated_captions"), False)
        oldest_first = parse_bool(entry.get("oldest_first"), False)
        caption_language = (entry.get("caption_language") or "en").strip() or "en"
        channel_url = (entry.get("channel_url") or entry.get("link") or None)
        if channel_url is not None:
            channel_url = str(channel_url).strip() or None

        configs.append(
            ChannelConfig(
                channel=channel_value,
                output=output_value,
                include_captions=include_captions,
                caption_language=caption_language,
                allow_generated_captions=allow_generated,
                oldest_first=oldest_first,
                channel_url=channel_url,
            )
        )

    return configs


def _parse_simple_channels(raw: str) -> List[ChannelConfig]:
    configs: List[ChannelConfig] = []
    for piece in re.split(r"[\n,;]+", raw):
        entry = piece.strip()
        if not entry:
            continue
        if ">" not in entry:
            raise ValueError(
                "Simple CHANNELS format requires 'channel>output' pairs separated by commas or newlines."
            )
        channel_value, output_value = entry.split(">", 1)
        channel_value = channel_value.strip()
        output_value = output_value.strip()
        if not channel_value:
            raise ValueError("Channel identifier cannot be empty.")
        if not output_value:
            raise ValueError("Output filename cannot be empty.")
        configs.append(ChannelConfig(channel=channel_value, output=output_value))
    return configs


def ensure_unique_outputs(configs: Iterable[ChannelConfig], base_dir: Path) -> None:
    seen = {}
    for config in configs:
        resolved = config.resolved_path(base_dir).resolve()
        key = resolved.as_posix().lower()
        if key in seen:
            other = seen[key]
            raise ValueError(
                f"Duplicate output target '{resolved}' configured for '{config.channel}' and '{other}'."
            )
        seen[key] = config.channel


def update_channel_feed(config: ChannelConfig, base_dir: Path, api_key: str, logger: logging.Logger) -> bool:
    output_path = config.resolved_path(base_dir)
    logger.info("Updating feed for %s -> %s", config.channel, output_path)

    try:
        result: FeedResult = generate_feed_for_channel(
            config.channel,
            api_key,
            include_captions=config.include_captions,
            caption_language=config.caption_language,
            allow_generated_captions=config.allow_generated_captions,
            oldest_first=config.oldest_first,
            channel_url_override=config.channel_url,
        )
    except Exception as exc:  # noqa: BLE001 - propagate readable message
        logger.exception("Failed to generate feed for %s: %s", config.channel, exc)
        return False

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result.rss, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - logging for troubleshooting
        logger.exception("Failed to write feed for %s to %s: %s", config.channel, output_path, exc)
        return False

    channel_title = result.channel.get("snippet", {}).get("title") or config.channel
    logger.info("Wrote %d items for channel '%s'", len(result.videos), channel_title)
    return True


def run_update_cycle(configs: List[ChannelConfig], base_dir: Path, api_key: str, logger: logging.Logger) -> bool:
    logger.info("Starting update cycle for %d channel(s)", len(configs))
    success = True
    for config in configs:
        if not update_channel_feed(config, base_dir, api_key, logger):
            success = False
    return success


def determine_interval(args_interval: Optional[int], logger: logging.Logger) -> int:
    if args_interval is not None:
        if args_interval <= 0:
            logger.warning("Interval must be a positive number of seconds. Falling back to 3600 seconds.")
            return 3600
        return args_interval

    env_seconds = os.getenv("REFRESH_INTERVAL_SECONDS")
    if env_seconds:
        try:
            seconds = int(float(env_seconds))
            if seconds > 0:
                return seconds
            logger.warning("REFRESH_INTERVAL_SECONDS must be positive. Falling back to default.")
        except ValueError:
            logger.warning("Could not parse REFRESH_INTERVAL_SECONDS='%s'. Using default.", env_seconds)

    env_minutes = os.getenv("REFRESH_INTERVAL_MINUTES")
    if env_minutes:
        try:
            minutes = float(env_minutes)
            if minutes > 0:
                return int(minutes * 60)
            logger.warning("REFRESH_INTERVAL_MINUTES must be positive. Falling back to default.")
        except ValueError:
            logger.warning("Could not parse REFRESH_INTERVAL_MINUTES='%s'. Using default.", env_minutes)

    return 3600


def load_configuration(args: argparse.Namespace, logger: logging.Logger, *, override_env: bool = False) -> tuple[List[ChannelConfig], Path, str]:
    load_dotenv(override=override_env)

    channels_raw = args.channels if args.channels is not None else os.getenv("CHANNELS", "")
    if not channels_raw.strip():
        raise ValueError("CHANNELS environment variable is empty. Add channel mappings to .env or pass --channels.")

    configs = parse_channels_config(channels_raw)
    if not configs:
        raise ValueError("No channels configured. Check the CHANNELS value in your .env file.")

    output_dir_value = args.output_directory or os.getenv("OUTPUT_DIRECTORY", "feeds")
    base_dir = Path(output_dir_value).expanduser()
    base_dir.mkdir(parents=True, exist_ok=True)

    ensure_unique_outputs(configs, base_dir)

    api_key = args.api_key or os.getenv("YT_API_KEY")
    if not api_key:
        raise ValueError("You must set YT_API_KEY in the environment or pass --api-key.")

    return configs, base_dir, api_key


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate multiple YouTube RSS feeds using settings from .env")
    parser.add_argument("--channels", help="Override the CHANNELS environment variable with an explicit value.")
    parser.add_argument("--output-directory", help="Directory for generated feeds. Defaults to OUTPUT_DIRECTORY or ./feeds.")
    parser.add_argument("--api-key", help="Override the YT_API_KEY environment variable.")
    parser.add_argument("--loop", action="store_true", help="Continuously refresh feeds using the configured interval.")
    parser.add_argument(
        "--interval",
        type=int,
        help="Refresh interval in seconds when --loop is used. Defaults to REFRESH_INTERVAL_SECONDS (or minutes) or 3600.",
    )
    parser.add_argument("--log-level", help="Logging verbosity (DEBUG, INFO, WARNING, ERROR). Defaults to LOG_LEVEL env or INFO.")
    args = parser.parse_args()

    log_level_name = args.log_level or os.getenv("LOG_LEVEL", "INFO")
    numeric_level = getattr(logging, log_level_name.upper(), logging.INFO)
    logging.basicConfig(level=numeric_level, format="%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger("youtube_rss_updater")

    loop_env = os.getenv("RUN_CONTINUOUSLY")
    loop_from_env = False
    if loop_env is not None:
        try:
            loop_from_env = parse_bool(loop_env, False)
        except ValueError:
            logger.warning("Invalid RUN_CONTINUOUSLY value '%s'. Ignoring.", loop_env)

    loop = args.loop or loop_from_env
    interval_seconds = determine_interval(args.interval, logger)

    try:
        configs, base_dir, api_key = load_configuration(args, logger, override_env=False)
    except Exception as exc:  # noqa: BLE001
        logger.error("Configuration error: %s", exc)
        return 2

    if not loop:
        success = run_update_cycle(configs, base_dir, api_key, logger)
        return 0 if success else 1

    logger.info("Entering continuous mode with interval %s seconds", interval_seconds)
    exit_code = 0
    try:
        while True:
            try:
                configs, base_dir, api_key = load_configuration(args, logger, override_env=True)
            except Exception as exc:  # noqa: BLE001
                logger.error("Configuration error during reload: %s", exc)
                exit_code = 1
            else:
                if not run_update_cycle(configs, base_dir, api_key, logger):
                    exit_code = 1
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        logger.info("Received interrupt, stopping updater.")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
