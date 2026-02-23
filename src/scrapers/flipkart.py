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
            # Try loading with retry logic
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

            # Wait for page content
            try:
                await page.wait_for_selector('h1, .B_NuCI, ._35KyD6', timeout=5000)
            except Exception:
                pass  # Continue anyway

            # Extra time for price to render
            await page.wait_for_timeout(4000)

            # --- Extract via Playwright JS for reliability ---
            # Flipkart now uses React Native Web with obfuscated classes that
            # change frequently. Instead of brittle CSS selectors, we use
            # JavaScript to read the page content structurally.

            # Title: grab from <title> tag or first h1
            title = await page.evaluate("""() => {
                // Try h1 first (most reliable on product pages)
                const h1 = document.querySelector('h1');
                if (h1 && h1.textContent.trim()) return h1.textContent.trim();
                // Fallback to legacy selectors
                const legacy = document.querySelector('.B_NuCI, ._35KyD6');
                if (legacy) return legacy.textContent.trim();
                // Fallback to page title minus " - Flipkart"
                const t = document.title.replace(/\\s*[-|].*Flipkart.*$/i, '').trim();
                return t || 'Unknown Product';
            }""")

            # Price: use JS to find the primary selling price.
            # Strategy: the main price is the first standalone ₹XX,XXX element
            # in the product info area, NOT inside "Buy at", "with Bank offer",
            # EMI, or "Lowest price" text.
            price_data = await page.evaluate("""() => {
                const results = { price: null, mrp: null };

                // Find all text nodes / elements containing ₹
                const allElems = document.querySelectorAll('div, span');
                const pricePattern = /^₹[\\d,]+$/;
                const mrpCandidates = [];
                const priceCandidates = [];

                for (const el of allElems) {
                    // Only check direct text content (not nested children text)
                    const directText = Array.from(el.childNodes)
                        .filter(n => n.nodeType === 3)
                        .map(n => n.textContent.trim())
                        .join('');

                    if (!pricePattern.test(directText)) continue;

                    // Skip elements inside "similar products" / recommendation sections
                    const ancestor = el.closest('[data-testid], [class*="similar"], [class*="recommend"]');

                    // Check if this looks like a struck-through / MRP price
                    const style = window.getComputedStyle(el);
                    const isStrikethrough = style.textDecorationLine.includes('line-through');

                    // Check parent context for offer/EMI text
                    const parentText = el.parentElement?.textContent || '';
                    const isOfferPrice = /bank offer|exchange|emi|lowest price|buy at/i.test(parentText);

                    const price = parseInt(directText.replace(/[₹,]/g, ''), 10);
                    if (isNaN(price)) continue;

                    if (isStrikethrough) {
                        mrpCandidates.push({ price, el_tag: el.tagName, classes: el.className });
                    } else if (!isOfferPrice) {
                        priceCandidates.push({ price, el_tag: el.tagName, classes: el.className });
                    }
                }

                // The selling price is typically the first non-strikethrough,
                // non-offer ₹XX,XXX on the page
                if (priceCandidates.length > 0) {
                    results.price = priceCandidates[0].price;
                }

                // MRP is the first strikethrough price
                if (mrpCandidates.length > 0) {
                    results.mrp = mrpCandidates[0].price;
                }

                return results;
            }""")

            price = price_data.get('price') if price_data else None
            original_price = price_data.get('mrp') if price_data else None

            # Fallback: parse HTML with BeautifulSoup if JS extraction failed
            if price is None:
                html = await page.content()
                soup = BeautifulSoup(html, 'html.parser')
                price, original_price = self._fallback_price_extract(soup)

            if price is None:
                raise ValueError(f"Could not extract price from {url}. Page may have changed or requires login.")

            # Ensure MRP > price, otherwise discard it
            if original_price and original_price <= price:
                original_price = None

            # Stock status
            is_out = await page.evaluate("""() => {
                const text = document.body.innerText || '';
                return /currently unavailable|out of stock|coming soon/i.test(text);
            }""")
            in_stock = not is_out

            # Seller
            seller = await page.evaluate("""() => {
                const el = document.querySelector('#sellerName span span, ._1RLviY');
                return el ? el.textContent.trim() : null;
            }""")

            # Image
            image_url = await page.evaluate("""() => {
                // Product images are usually the first large img
                const imgs = document.querySelectorAll('img[src*="rukminim"]');
                for (const img of imgs) {
                    const src = img.src || '';
                    if (src.includes('/image/') && !src.includes('icon')) return src;
                }
                return null;
            }""")

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

    def _fallback_price_extract(self, soup) -> tuple:
        """Fallback: extract price from HTML using BeautifulSoup."""
        price = None
        original_price = None

        # Try legacy CSS selectors first
        for selector in ['._30jeq3', '.Nx9bqj', '._1_WHN1', 'div._16Jk6d']:
            elem = soup.select_one(selector)
            if elem:
                price = self._parse_price(elem.get_text())
                if price:
                    break

        # If still no price, find first bare ₹XX,XXX text node
        if price is None:
            for elem in soup.find_all(string=re.compile(r'^₹[\d,]+$')):
                # Skip if parent text contains offer keywords
                parent_text = elem.parent.get_text() if elem.parent else ''
                if re.search(r'bank offer|exchange|emi|lowest price|buy at', parent_text, re.I):
                    continue
                candidate = self._parse_price(elem)
                if candidate:
                    price = candidate
                    break

        # MRP from legacy selectors
        for selector in ['._3I9_wc', '.yRaY8j', '._2p6lqe']:
            elem = soup.select_one(selector)
            if elem:
                original_price = self._parse_price(elem.get_text())
                if original_price:
                    break

        return price, original_price
