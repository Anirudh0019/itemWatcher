"""Core watcher logic - checks prices and triggers alerts."""

import asyncio
from typing import Optional

from .scrapers import AmazonScraper, FlipkartScraper, BaseScraper, ProductInfo
from .storage import Database, WatchedProduct
from .alerts import EmailNotifier, AlertConfig, TelegramNotifier


def get_scraper_for_url(url: str) -> Optional[BaseScraper]:
    """Get the appropriate scraper for a URL."""
    scrapers = [AmazonScraper(), FlipkartScraper()]
    for scraper in scrapers:
        if scraper.can_handle(url):
            return scraper
    return None


async def scrape_product(url: str) -> ProductInfo:
    """Scrape a single product URL."""
    scraper = get_scraper_for_url(url)
    if not scraper:
        raise ValueError(f"No scraper available for URL: {url}")

    async with scraper:
        return await scraper.scrape(url)


async def check_product(
    db: Database,
    product: WatchedProduct,
    notifier: Optional[EmailNotifier] = None,
    telegram: Optional[TelegramNotifier] = None,
) -> Optional[ProductInfo]:
    """Check a single product for price changes.

    Returns a tuple of (ProductInfo, below_target: bool) or None on error.
    The below_target flag is used by check_all_products for summary logic.
    """
    try:
        info = await scrape_product(product.url)

        # Get previous price for comparison
        previous = await db.get_latest_price(product.id)
        lowest = await db.get_lowest_price(product.id)

        # Record new price
        await db.record_price(
            product.id,
            info.price,
            info.original_price,
            info.in_stock,
        )

        # Email alerts (existing behavior — on price drop only)
        if notifier and previous:
            if info.price < previous.price:
                await notifier.send_price_alert(
                    product_title=product.title,
                    product_url=product.url,
                    current_price=info.price,
                    previous_price=previous.price,
                    target_price=product.target_price,
                    lowest_price=lowest,
                )

            if info.in_stock and not previous.in_stock:
                await notifier.send_back_in_stock_alert(
                    product_title=product.title,
                    product_url=product.url,
                    price=info.price,
                )

        # Telegram: immediate alert if at or below target (every check, no dedup)
        if telegram and product.target_price and info.price <= product.target_price:
            await telegram.send_price_alert(
                product_title=product.title,
                product_url=product.url,
                current_price=info.price,
                target_price=product.target_price,
            )

        # Telegram: back in stock
        if telegram and previous and info.in_stock and not previous.in_stock:
            await telegram.send_back_in_stock_alert(
                product_title=product.title,
                product_url=product.url,
                price=info.price,
            )

        return info

    except Exception as e:
        print(f"Error checking {product.url}: {e}")
        return None


async def check_all_products(
    db: Database,
    notifier: Optional[EmailNotifier] = None,
    telegram: Optional[TelegramNotifier] = None,
    delay_between: float = 5.0,
    send_telegram_summary: bool = True,
):
    """Check all active products.

    Args:
        send_telegram_summary: If True, send a Telegram daily summary for
            products that are all above target. Set to False to skip the
            summary (useful if you only want summaries once per day).
    """
    products = await db.get_active_products()

    # Track which products with targets were above target, for summary
    above_target_products = []
    any_below_target = False

    for i, product in enumerate(products):
        print(f"[{i+1}/{len(products)}] Checking: {product.title[:50]}...")
        info = await check_product(db, product, notifier, telegram)

        if info and product.target_price:
            if info.price <= product.target_price:
                any_below_target = True
            else:
                gap = info.price - product.target_price
                above_target_products.append((product, info, gap))

        # Delay between requests to avoid rate limiting
        if i < len(products) - 1:
            await asyncio.sleep(delay_between)

    print(f"Checked {len(products)} products.")

    # Telegram daily summary: only if all targeted products are above target
    if telegram and send_telegram_summary and not any_below_target and above_target_products:
        # Find the product closest to its target
        closest = min(above_target_products, key=lambda x: x[2])
        await telegram.send_daily_summary(
            total_checked=len(products),
            closest_product=closest[0].title,
            closest_price=closest[1].price,
            closest_gap=closest[2],
        )
    elif telegram and send_telegram_summary and not any_below_target and not above_target_products:
        # All products checked but none have targets set
        await telegram.send_daily_summary(total_checked=len(products))
