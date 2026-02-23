"""Core watcher logic - checks prices and triggers alerts."""

import asyncio
from typing import Optional

from .scrapers import AmazonScraper, FlipkartScraper, BaseScraper, ProductInfo
from .storage import Database, WatchedProduct
from .alerts import EmailNotifier, AlertConfig


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
) -> Optional[ProductInfo]:
    """Check a single product for price changes."""
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

        # Check for alerts
        if notifier and previous:
            # Price drop alert
            if info.price < previous.price:
                await notifier.send_price_alert(
                    product_title=product.title,
                    product_url=product.url,
                    current_price=info.price,
                    previous_price=previous.price,
                    target_price=product.target_price,
                    lowest_price=lowest,
                )

            # Back in stock alert
            if info.in_stock and not previous.in_stock:
                await notifier.send_back_in_stock_alert(
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
    delay_between: float = 5.0,
):
    """Check all active products."""
    products = await db.get_active_products()

    for i, product in enumerate(products):
        print(f"[{i+1}/{len(products)}] Checking: {product.title[:50]}...")
        await check_product(db, product, notifier)

        # Delay between requests to avoid rate limiting
        if i < len(products) - 1:
            await asyncio.sleep(delay_between)

    print(f"Checked {len(products)} products.")
