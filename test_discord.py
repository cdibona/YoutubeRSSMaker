#!/usr/bin/env python3
"""
Test Discord webhook integration
-------------------------------

Simple script to test Discord webhook functionality.
"""

import os
import sys
from discord_logger import get_logger, setup_logging

def main():
    if len(sys.argv) > 1:
        # Allow webhook URL override from command line
        webhook_url = sys.argv[1]
        os.environ["DISCORD_WEBHOOK_URL"] = webhook_url
        os.environ["LOG_TO_DISCORD"] = "true"

    # Set up logger
    logger = setup_logging("INFO")

    # Test basic logging
    logger.log_info("🧪 Discord webhook test - Info level message")
    logger.log_error("🚨 Discord webhook test - Error level message")

    # Test system startup
    logger.log_system_start("test mode")

    # Test daily summary
    logger.report_daily_summary()

    print("✅ Discord webhook test messages sent!")
    print("Check your Discord channel for the messages.")

if __name__ == "__main__":
    main()