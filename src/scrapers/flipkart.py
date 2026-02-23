import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .base import BaseScraper, ProductInfo


class FlipkartScraper(BaseScraper):
    """Scraper for Flipkart (flipkart.com)."""

    SUPPORTED_DOMAINS = ['flipkart.com', 'www.flipkart.com']

    def can_handle(self, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.netloc in self.SUPPORTED_DOMAINS

    def _parse_price(self, text: str) -> Optional[float]:
        """Extract numeric price from text like '₹1,299' or '1,299'."""
        if not text:
            return None
        # Remove currency symbols, commas, spaces
        cleaned = re.sub(r'[₹,\s]', '', text)
        try:
            return float(cleaned)
        except ValueError:
            return None

    async def scrape(self, url: str) -> ProductInfo:
        """Scrape product info from Flipkart URL."""
        page = await self._new_page()

        try:
            # Try loading with retry logic like Amazon
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            except Exception as e:
                print(f"Retrying Flipkart page load... ({str(e)[:50]})")
                await page.wait_for_timeout(2000)
                await page.goto(url, wait_until='domcontentloaded', timeout=60000)

            # Close login popup if it appears
            try:
                close_btn = page.locator('button._2KpZ6l._2doB4z, button._2KpZ6l')
                if await close_btn.is_visible(timeout=2000):
                    await close_btn.click()
                    await page.wait_for_timeout(500)
            except Exception:
                pass  # No popup, continue

            # Wait for page content - try multiple indicators
            try:
                await page.wait_for_selector('.B_NuCI, ._35KyD6, h1', timeout=5000)
            except Exception:
                pass  # Continue anyway

            # Extra time for price to render
            await page.wait_for_timeout(3000)

            html = await page.content()
            soup = BeautifulSoup(html, 'html.parser')

            # Title - Flipkart uses various class names
            title = 'Unknown Product'
            title_selectors = ['.B_NuCI', '._35KyD6', 'h1 span']
            for selector in title_selectors:
                elem = soup.select_one(selector)
                if elem:
                    title = elem.get_text(strip=True)
                    break

            # Current price - try multiple selectors
            price = None
            price_selectors = [
                '._30jeq3',  # Common price class
                '.Nx9bqj',   # Alternative price class
                '._1_WHN1',  # Another variant
                'div._16Jk6d',  # Price container
            ]

            for selector in price_selectors:
                elem = soup.select_one(selector)
                if elem:
                    price = self._parse_price(elem.get_text())
                    if price:
                        break

            # If still no price, try finding any element with ₹ symbol
            if price is None:
                price_text = soup.find(string=re.compile(r'₹[\d,]+'))
                if price_text:
                    price = self._parse_price(price_text)

            if price is None:
                raise ValueError(f"Could not extract price from {url}. Page may have changed or requires login.")

            # Original price (MRP)
            original_price = None
            mrp_selectors = ['._3I9_wc', '.yRaY8j', '._2p6lqe']
            for selector in mrp_selectors:
                elem = soup.select_one(selector)
                if elem:
                    original_price = self._parse_price(elem.get_text())
                    if original_price:
                        break

            # Stock status
            in_stock = True
            out_of_stock = soup.select_one('._16FRp0')
            if out_of_stock and 'out of stock' in out_of_stock.get_text(strip=True).lower():
                in_stock = False

            # Also check for "Currently unavailable"
            unavailable = soup.find(string=re.compile(r'currently unavailable', re.I))
            if unavailable:
                in_stock = False

            # Seller
            seller = None
            seller_elem = soup.select_one('#sellerName span span, ._1RLviY')
            if seller_elem:
                seller = seller_elem.get_text(strip=True)

            # Image
            image_url = None
            img_selectors = ['._396cs4', '._2r_T1I img', '.CXW8mj img']
            for selector in img_selectors:
                elem = soup.select_one(selector)
                if elem:
                    image_url = elem.get('src')
                    if image_url:
                        break

            return ProductInfo(
                url=url,
                title=title,
                price=price,
                currency='INR',
                original_price=original_price,
                in_stock=in_stock,
                seller=seller,
                image_url=image_url,
                scraped_at=datetime.now(),
                source='flipkart',
            )

        finally:
            await page.close()
