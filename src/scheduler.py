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
from .alerts import EmailNotifier, TelegramNotifier
from .watcher import check_all_products

# Track last summary date to send Telegram summary only once per day
_last_summary_date = None


async def run_check(config: Config):
    """Run a price check for all products."""
    global _last_summary_date
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting price check...")

    notifier = None
    if config.email:
        notifier = EmailNotifier(config.email)

    telegram = None
    if config.telegram:
        telegram = TelegramNotifier(config.telegram)

    # Send Telegram summary only once per day
    today = datetime.now().date()
    send_summary = _last_summary_date != today
    if send_summary:
        _last_summary_date = today

    async with Database(config.db_path) as db:
        await check_all_products(
            db, notifier, telegram,
            send_telegram_summary=send_summary,
        )

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Price check complete.")


async def start_scheduler(config: Config = None):
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

    loop = asyncio.get_running_loop()

    # Handle shutdown gracefully
    stop_event = asyncio.Event()

    def shutdown(signum, frame):
        print("\nShutting down scheduler...")
        loop.call_soon_threadsafe(stop_event.set)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"ItemWatcher Scheduler Started")
    print(f"Checking prices every {config.check_interval_hours} hours")
    print(f"Press Ctrl+C to stop\n")

    scheduler.start()

    try:
        await stop_event.wait()
    finally:
        scheduler.shutdown()


if __name__ == '__main__':
    asyncio.run(start_scheduler())
