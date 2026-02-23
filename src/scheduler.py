#!/usr/bin/env python3
"""Background scheduler for periodic price checks."""

import asyncio
import signal
import sys
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .config import Config
from .storage import Database
from .alerts import EmailNotifier
from .watcher import check_all_products


async def run_check(config: Config):
    """Run a price check for all products."""
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting price check...")

    notifier = None
    if config.email:
        notifier = EmailNotifier(config.email)

    async with Database(config.db_path) as db:
        await check_all_products(db, notifier)

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Price check complete.")


def start_scheduler(config: Config = None):
    """Start the background scheduler."""
    if config is None:
        config = Config.load()

    scheduler = AsyncIOScheduler()

    # Schedule periodic checks
    scheduler.add_job(
        lambda: asyncio.create_task(run_check(config)),
        trigger=IntervalTrigger(hours=config.check_interval_hours),
        id='price_check',
        name='Check all product prices',
        next_run_time=datetime.now(),  # Run immediately on start
    )

    # Handle shutdown gracefully
    def shutdown(signum, frame):
        print("\nShutting down scheduler...")
        scheduler.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"ItemWatcher Scheduler Started")
    print(f"Checking prices every {config.check_interval_hours} hours")
    print(f"Press Ctrl+C to stop\n")

    scheduler.start()

    # Keep the main thread alive
    try:
        asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == '__main__':
    start_scheduler()
