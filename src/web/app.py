#!/usr/bin/env python3
"""FastAPI web application for ItemWatcher."""

import traceback
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
from datetime import datetime
from typing import Optional

from ..config import Config
from ..storage import Database
from ..watcher import scrape_product, check_product, get_scraper_for_url
from ..alerts import EmailNotifier, TelegramNotifier


# Initialize FastAPI
app = FastAPI(title="ItemWatcher", description="Price tracking for Amazon & Flipkart")

# Global exception handler to prevent crashes
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch all unhandled exceptions to prevent server crashes."""
    error_trace = traceback.format_exc()
    print(f"Unhandled exception: {error_trace}")

    # Return user-friendly error page
    return HTMLResponse(
        content=f"""
        <html>
        <body style="font-family: Arial; padding: 40px; max-width: 800px; margin: 0 auto;">
            <h1 style="color: #e53e3e;">Something went wrong</h1>
            <p>An unexpected error occurred. The server is still running.</p>
            <p><a href="/" style="color: #667eea;">← Back to Home</a></p>
            <details style="margin-top: 20px;">
                <summary style="cursor: pointer; color: #666;">Technical Details</summary>
                <pre style="background: #f5f5f5; padding: 15px; overflow: auto; border-radius: 5px;">{error_trace}</pre>
            </details>
        </body>
        </html>
        """,
        status_code=500
    )

# Set up templates and static files
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Load config
config = Config.load()

# Template helper functions
def format_time_ago(dt: datetime) -> str:
    """Format datetime as 'X minutes/hours/days ago'."""
    if not dt:
        return "Never"

    # Handle timezone-naive datetime (SQLite stores as UTC but without tz info)
    from datetime import timezone

    # If datetime is naive (no timezone), assume it's UTC and convert to local
    if dt.tzinfo is None:
        dt_utc = dt.replace(tzinfo=timezone.utc)
        dt_local = dt_utc.astimezone()
        dt = dt_local.replace(tzinfo=None)  # Make naive again for comparison

    delta = datetime.now() - dt
    seconds = delta.total_seconds()

    # Handle negative deltas (clock skew)
    if seconds < 0:
        seconds = 0

    if seconds < 60:
        return "Just now"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes}m ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours}h ago"
    else:
        days = int(seconds / 86400)
        return f"{days}d ago"

templates.env.globals['format_time_ago'] = format_time_ago


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Homepage - show all tracked products."""
    async with Database(config.db_path) as db:
        products = await db.get_active_products()

        # Enhance products with latest price info
        product_list = []
        for p in products:
            latest = await db.get_latest_price(p.id)
            lowest = await db.get_lowest_price(p.id)

            product_list.append({
                'id': p.id,
                'title': p.title,
                'url': p.url,
                'source': p.source,
                'target_price': p.target_price,
                'current_price': latest.price if latest else None,
                'lowest_price': lowest,
                'last_checked': p.last_checked,
                'in_stock': latest.in_stock if latest else True,
            })

    return templates.TemplateResponse("index.html", {
        "request": request,
        "products": product_list,
    })


@app.get("/product/{product_id}", response_class=HTMLResponse)
async def product_detail(request: Request, product_id: int):
    """Product detail page with price history chart."""
    async with Database(config.db_path) as db:
        product = await db.get_product(product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        price_history = await db.get_price_history(product_id, limit=100)
        lowest = await db.get_lowest_price(product_id)
        latest = await db.get_latest_price(product_id)

        # Convert price_history to JSON-serializable dicts
        price_history_dicts = [
            {
                "id": p.id,
                "price": p.price,
                "original_price": p.original_price,
                "in_stock": p.in_stock,
                "recorded_at": p.recorded_at.isoformat() if p.recorded_at else None,
            }
            for p in price_history
        ]

        return templates.TemplateResponse("product_detail.html", {
            "request": request,
            "product": product,
            "latest_price": latest,
            "lowest_price": lowest,
            "price_history": price_history,
            "price_history_json": price_history_dicts,
        })


@app.post("/add")
async def add_product(request: Request, url: str = Form(...), target_price: Optional[float] = Form(None)):
    """Add a new product to track."""
    # Validate URL
    if not get_scraper_for_url(url):
        async with Database(config.db_path) as db:
            products = await db.get_active_products()
            product_list = []
            for p in products:
                latest = await db.get_latest_price(p.id)
                lowest = await db.get_lowest_price(p.id)
                product_list.append({
                    'id': p.id,
                    'title': p.title,
                    'url': p.url,
                    'source': p.source,
                    'target_price': p.target_price,
                    'current_price': latest.price if latest else None,
                    'lowest_price': lowest,
                    'last_checked': p.last_checked,
                    'in_stock': latest.in_stock if latest else True,
                })

        return templates.TemplateResponse("index.html", {
            "request": request,
            "products": product_list,
            "error": "Unsupported URL. Only Amazon.in and Flipkart.com are supported."
        })

    try:
        # Scrape product info
        info = await scrape_product(url)

        async with Database(config.db_path) as db:
            # Add to database
            product_id = await db.add_product(
                url=url,
                title=info.title,
                source=info.source,
                target_price=target_price,
            )

            # Record initial price
            await db.record_price(
                product_id,
                info.price,
                info.original_price,
                info.in_stock,
            )

        return RedirectResponse(url="/", status_code=303)

    except Exception as e:
        # Return to homepage with error message instead of crashing
        async with Database(config.db_path) as db:
            products = await db.get_active_products()
            product_list = []
            for p in products:
                latest = await db.get_latest_price(p.id)
                lowest = await db.get_lowest_price(p.id)
                product_list.append({
                    'id': p.id,
                    'title': p.title,
                    'url': p.url,
                    'source': p.source,
                    'target_price': p.target_price,
                    'current_price': latest.price if latest else None,
                    'lowest_price': lowest,
                    'last_checked': p.last_checked,
                    'in_stock': latest.in_stock if latest else True,
                })

        error_msg = str(e)
        if "Timeout" in error_msg:
            error_msg = "Timeout while loading page. The site may be slow or blocking scrapers. Try again later."
        elif "Could not extract price" in error_msg:
            error_msg = "Could not extract price. The page structure may have changed or requires login."
        else:
            error_msg = f"Failed to add product: {error_msg[:100]}"

        return templates.TemplateResponse("index.html", {
            "request": request,
            "products": product_list,
            "error": error_msg
        })


@app.post("/remove/{product_id}")
async def remove_product(product_id: int):
    """Remove a product from tracking."""
    async with Database(config.db_path) as db:
        product = await db.get_product(product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        await db.remove_product(product_id)

    return RedirectResponse(url="/", status_code=303)


@app.post("/check/{product_id}")
async def check_product_now(product_id: int):
    """Check price for a specific product now."""
    async with Database(config.db_path) as db:
        product = await db.get_product(product_id)
        if not product:
            return JSONResponse({
                "status": "error",
                "message": "Product not found"
            }, status_code=404)

        notifier = None
        if config.email:
            notifier = EmailNotifier(config.email)

        telegram = None
        if config.telegram:
            telegram = TelegramNotifier(config.telegram)

        try:
            info = await check_product(db, product, notifier, telegram)
            return JSONResponse({
                "status": "success",
                "price": info.price if info else None,
                "in_stock": info.in_stock if info else None,
            })
        except Exception as e:
            error_msg = str(e)
            if "Timeout" in error_msg:
                error_msg = "Timeout - site may be slow or blocking"
            elif "Could not extract" in error_msg:
                error_msg = "Could not extract price - page may have changed"
            else:
                error_msg = error_msg[:100]

            return JSONResponse({
                "status": "error",
                "message": error_msg
            }, status_code=200)  # Return 200 so frontend can display error properly


@app.post("/check-all")
async def check_all_products():
    """Check prices for all products."""
    from ..watcher import check_all_products

    notifier = None
    if config.email:
        notifier = EmailNotifier(config.email)

    telegram = None
    if config.telegram:
        telegram = TelegramNotifier(config.telegram)

    async with Database(config.db_path) as db:
        try:
            await check_all_products(db, notifier, telegram, delay_between=3.0)
            return JSONResponse({"status": "success", "message": "All products checked successfully"})
        except Exception as e:
            error_msg = str(e)
            if "Timeout" in error_msg:
                error_msg = "Some products timed out. Try checking them individually."
            else:
                error_msg = error_msg[:100]

            return JSONResponse({
                "status": "error",
                "message": f"Error checking products: {error_msg}"
            }, status_code=200)


@app.post("/target/{product_id}")
async def set_target_price(product_id: int, target_price: Optional[float] = Form(None)):
    """Set or update target price for a product."""
    async with Database(config.db_path) as db:
        product = await db.get_product(product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        await db.set_target_price(product_id, target_price)

    return RedirectResponse(url=f"/product/{product_id}", status_code=303)


@app.get("/api/products")
async def api_list_products():
    """API endpoint to list all products."""
    async with Database(config.db_path) as db:
        products = await db.get_active_products()
        return [
            {
                "id": p.id,
                "title": p.title,
                "url": p.url,
                "source": p.source,
                "target_price": p.target_price,
                "last_checked": p.last_checked.isoformat() if p.last_checked else None,
            }
            for p in products
        ]


@app.get("/api/product/{product_id}/history")
async def api_price_history(product_id: int, limit: int = 50):
    """API endpoint to get price history."""
    async with Database(config.db_path) as db:
        product = await db.get_product(product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        history = await db.get_price_history(product_id, limit=limit)
        return [
            {
                "date": h.recorded_at.isoformat(),
                "price": h.price,
                "original_price": h.original_price,
                "in_stock": h.in_stock,
            }
            for h in history
        ]


def start_server(host: str = "0.0.0.0", port: int = 8000):
    """Start the web server."""
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_server()
