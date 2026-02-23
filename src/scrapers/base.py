from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from playwright.async_api import async_playwright, Browser, Page


@dataclass
class ProductInfo:
    """Scraped product information."""
    url: str
    title: str
    price: float
    currency: str
    original_price: Optional[float]  # MRP if discounted
    in_stock: bool
    seller: Optional[str]
    image_url: Optional[str]
    scraped_at: datetime
    source: str  # 'amazon' or 'flipkart'

    @property
    def discount_percent(self) -> Optional[float]:
        if self.original_price and self.original_price > self.price:
            return round((1 - self.price / self.original_price) * 100, 1)
        return None


class BaseScraper(ABC):
    """Base class for all scrapers."""

    def __init__(self):
        self._browser: Optional[Browser] = None
        self._playwright = None

    async def __aenter__(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
            ]
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def _new_page(self) -> Page:
        """Create a new page with stealth settings."""
        context = await self._browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='en-IN',
            extra_http_headers={
                'Accept-Language': 'en-IN,en;q=0.9',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
        )
        page = await context.new_page()

        # Enhanced stealth settings
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-IN', 'en']});
            window.chrome = { runtime: {} };
        """)

        return page

    @abstractmethod
    async def scrape(self, url: str) -> ProductInfo:
        """Scrape product info from URL."""
        pass

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Check if this scraper can handle the given URL."""
        pass
