import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .base import BaseScraper, ProductInfo


class AmazonScraper(BaseScraper):
    """Scraper for Amazon India (amazon.in)."""

    SUPPORTED_DOMAINS = ['amazon.in', 'www.amazon.in']

    def can_handle(self, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.netloc in self.SUPPORTED_DOMAINS

    def _parse_price(self, text: str) -> Optional[float]:
        """Extract numeric price from text like '₹1,299' or '1,299.00'."""
        if not text:
            return None
        # Remove currency symbols, commas, spaces
        cleaned = re.sub(r'[₹,\s]', '', text)
        try:
            return float(cleaned)
        except ValueError:
            return None

    async def scrape(self, url: str) -> ProductInfo:
        """Scrape product info from Amazon URL."""
        page = await self._new_page()

        try:
            # Try with a simpler wait strategy first
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            except Exception as e:
                # Fallback: try one more time with longer timeout
                print(f"Retrying page load... ({str(e)[:50]})")
                await page.wait_for_timeout(2000)
                await page.goto(url, wait_until='domcontentloaded', timeout=60000)

            # Wait for product title to appear (indicates main content loaded)
            try:
                await page.wait_for_selector('#productTitle', timeout=10000)
            except Exception:
                pass  # Continue anyway, might still get content

            # Extra time for dynamic price elements to render
            await page.wait_for_timeout(4000)

            html = await page.content()
            soup = BeautifulSoup(html, 'html.parser')

            # Title
            title_elem = soup.select_one('#productTitle')
            title = title_elem.get_text(strip=True) if title_elem else 'Unknown Product'

            # Price - Amazon has multiple possible locations
            price = None
            price_selectors = [
                '.a-price[data-a-color="price"] .a-offscreen',  # Modern Amazon
                '.a-price .a-offscreen',
                '#corePrice_feature_div .a-offscreen',
                '#corePriceDisplay_desktop_feature_div .a-offscreen',
                '#priceblock_ourprice',
                '#priceblock_dealprice',
                '.a-price-whole',
            ]

            for selector in price_selectors:
                elem = soup.select_one(selector)
                if elem:
                    price = self._parse_price(elem.get_text())
                    if price:
                        break

            # If still no price, try finding any .a-price element
            if price is None:
                price_divs = soup.select('.a-price .a-offscreen')
                for div in price_divs:
                    price = self._parse_price(div.get_text())
                    if price:
                        break

            if price is None:
                raise ValueError(f"Could not extract price from {url}")

            # Original price (MRP)
            original_price = None
            mrp_selectors = [
                '.a-price[data-a-color="secondary"] .a-offscreen',
                '.a-price[data-a-strike="true"] .a-offscreen',
                '.a-text-price .a-offscreen',
                '#priceblock_mrp',
                '.basisPrice .a-offscreen',
            ]

            for selector in mrp_selectors:
                elem = soup.select_one(selector)
                if elem:
                    original_price = self._parse_price(elem.get_text())
                    if original_price and original_price > price:
                        break
                    original_price = None  # Reset if MRP is not greater than price

            # Stock status
            in_stock = True
            availability = soup.select_one('#availability')
            if availability:
                text = availability.get_text(strip=True).lower()
                if 'unavailable' in text or 'out of stock' in text:
                    in_stock = False

            # Seller
            seller = None
            seller_elem = soup.select_one('#sellerProfileTriggerId, #merchant-info a')
            if seller_elem:
                seller = seller_elem.get_text(strip=True)

            # Image
            image_url = None
            img_elem = soup.select_one('#landingImage, #imgBlkFront')
            if img_elem:
                image_url = img_elem.get('src') or img_elem.get('data-old-hires')

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
                source='amazon',
            )

        finally:
            await page.close()
