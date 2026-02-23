import aiosqlite
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class WatchedProduct:
    """A product being tracked."""
    id: int
    url: str
    title: str
    source: str  # 'amazon' or 'flipkart'
    target_price: Optional[float]  # Alert when price drops below this
    added_at: datetime
    last_checked: Optional[datetime]
    is_active: bool


@dataclass
class PriceRecord:
    """A single price data point."""
    id: int
    product_id: int
    price: float
    original_price: Optional[float]
    in_stock: bool
    recorded_at: datetime


class Database:
    """SQLite database for price tracking."""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = Path.home() / '.itemwatcher' / 'data.db'
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    async def __aenter__(self):
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._init_schema()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._conn.close()

    async def _init_schema(self):
        """Create tables if they don't exist."""
        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                source TEXT NOT NULL,
                target_price REAL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_checked TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                price REAL NOT NULL,
                original_price REAL,
                in_stock BOOLEAN DEFAULT 1,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            CREATE INDEX IF NOT EXISTS idx_prices_product_id ON prices(product_id);
            CREATE INDEX IF NOT EXISTS idx_prices_recorded_at ON prices(recorded_at);
        """)
        await self._conn.commit()

    async def add_product(self, url: str, title: str, source: str, target_price: Optional[float] = None) -> int:
        """Add a new product to track. Returns product ID."""
        cursor = await self._conn.execute(
            """
            INSERT INTO products (url, title, source, target_price)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                title = excluded.title,
                is_active = 1
            RETURNING id
            """,
            (url, title, source, target_price)
        )
        row = await cursor.fetchone()
        await self._conn.commit()
        return row[0]

    async def remove_product(self, product_id: int):
        """Soft-delete a product (keeps history)."""
        await self._conn.execute(
            "UPDATE products SET is_active = 0 WHERE id = ?",
            (product_id,)
        )
        await self._conn.commit()

    async def get_product(self, product_id: int) -> Optional[WatchedProduct]:
        """Get a single product by ID."""
        cursor = await self._conn.execute(
            "SELECT * FROM products WHERE id = ?",
            (product_id,)
        )
        row = await cursor.fetchone()
        if row:
            return self._row_to_product(row)
        return None

    async def get_product_by_url(self, url: str) -> Optional[WatchedProduct]:
        """Get a product by URL."""
        cursor = await self._conn.execute(
            "SELECT * FROM products WHERE url = ?",
            (url,)
        )
        row = await cursor.fetchone()
        if row:
            return self._row_to_product(row)
        return None

    async def get_active_products(self) -> list[WatchedProduct]:
        """Get all active products."""
        cursor = await self._conn.execute(
            "SELECT * FROM products WHERE is_active = 1 ORDER BY added_at DESC"
        )
        rows = await cursor.fetchall()
        return [self._row_to_product(row) for row in rows]

    async def record_price(self, product_id: int, price: float, original_price: Optional[float], in_stock: bool):
        """Record a price point for a product."""
        await self._conn.execute(
            """
            INSERT INTO prices (product_id, price, original_price, in_stock)
            VALUES (?, ?, ?, ?)
            """,
            (product_id, price, original_price, in_stock)
        )
        await self._conn.execute(
            "UPDATE products SET last_checked = CURRENT_TIMESTAMP WHERE id = ?",
            (product_id,)
        )
        await self._conn.commit()

    async def get_price_history(self, product_id: int, limit: int = 100) -> list[PriceRecord]:
        """Get price history for a product, most recent first."""
        cursor = await self._conn.execute(
            """
            SELECT * FROM prices
            WHERE product_id = ?
            ORDER BY recorded_at DESC
            LIMIT ?
            """,
            (product_id, limit)
        )
        rows = await cursor.fetchall()
        return [self._row_to_price(row) for row in rows]

    async def get_latest_price(self, product_id: int) -> Optional[PriceRecord]:
        """Get the most recent price for a product."""
        history = await self.get_price_history(product_id, limit=1)
        return history[0] if history else None

    async def get_lowest_price(self, product_id: int) -> Optional[float]:
        """Get the lowest recorded price for a product."""
        cursor = await self._conn.execute(
            "SELECT MIN(price) FROM prices WHERE product_id = ?",
            (product_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def set_target_price(self, product_id: int, target_price: Optional[float]):
        """Set or update the target price alert threshold."""
        await self._conn.execute(
            "UPDATE products SET target_price = ? WHERE id = ?",
            (target_price, product_id)
        )
        await self._conn.commit()

    def _row_to_product(self, row) -> WatchedProduct:
        return WatchedProduct(
            id=row['id'],
            url=row['url'],
            title=row['title'],
            source=row['source'],
            target_price=row['target_price'],
            added_at=datetime.fromisoformat(row['added_at']) if row['added_at'] else None,
            last_checked=datetime.fromisoformat(row['last_checked']) if row['last_checked'] else None,
            is_active=bool(row['is_active']),
        )

    def _row_to_price(self, row) -> PriceRecord:
        return PriceRecord(
            id=row['id'],
            product_id=row['product_id'],
            price=row['price'],
            original_price=row['original_price'],
            in_stock=bool(row['in_stock']),
            recorded_at=datetime.fromisoformat(row['recorded_at']) if row['recorded_at'] else None,
        )
