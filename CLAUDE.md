# ItemWatcher - Price Tracking Tool

## Project Overview
A personal, open-source price tracker for Amazon India and Flipkart. An alternative to pricehistory.in with full customization control.

## Status
🟢 **v0.2.0 - Web UI Added**

## Quick Start

```bash
# Install dependencies
pip install -e .

# Install Playwright browsers (one-time)
playwright install chromium

# Start Web UI (recommended)
itemwatcher web
# Then open http://localhost:8000 in your browser

# OR use CLI commands:
itemwatcher test "https://www.amazon.in/dp/B0EXAMPLE"
itemwatcher add "https://www.amazon.in/dp/B0EXAMPLE" --target 15000
itemwatcher list
itemwatcher check
itemwatcher history 1
```

## Project Structure
```
itemWatcher/
├── src/
│   ├── scrapers/
│   │   ├── base.py        # Base scraper class
│   │   ├── amazon.py      # Amazon.in scraper
│   │   └── flipkart.py    # Flipkart scraper
│   ├── storage/
│   │   └── database.py    # SQLite storage layer
│   ├── alerts/
│   │   └── notifier.py    # Email notifications
│   ├── web/
│   │   ├── app.py         # FastAPI web server
│   │   └── templates/     # HTML templates
│   ├── cli.py             # CLI interface
│   ├── config.py          # Configuration loader
│   ├── watcher.py         # Core checking logic
│   └── scheduler.py       # Background scheduler
├── pyproject.toml
├── requirements.txt
├── .env.example
└── CLAUDE.md
```

## Usage

### Web UI (Recommended)
```bash
itemwatcher web
# Open http://localhost:8000 in your browser
```

Features:
- Dashboard with all tracked products
- Add new products via web form
- Interactive price history charts (Chart.js)
- One-click price checks
- Set target prices
- Visual price trends

### CLI Commands

| Command | Description |
|---------|-------------|
| `itemwatcher web` | Start web UI server (port 8000) |
| `itemwatcher add <url>` | Add product to watchlist |
| `itemwatcher list` | Show all tracked products |
| `itemwatcher remove <id>` | Remove product from tracking |
| `itemwatcher check` | Check all prices now |
| `itemwatcher check --id <id>` | Check specific product |
| `itemwatcher history <id>` | Show price history |
| `itemwatcher target <id> <price>` | Set target price alert |
| `itemwatcher test <url>` | Test scraping without saving |

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
# Email alerts (Gmail example - use App Password)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=you@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM_EMAIL=you@gmail.com
ALERT_TO_EMAIL=you@gmail.com

# Check interval for scheduler
ITEMWATCHER_CHECK_INTERVAL_HOURS=6
```

## Running the Scheduler

For automatic price checks:

```bash
python -m src.scheduler
```

Or set up as a cron job / systemd service.

## Tech Stack
- **Python 3.10+**
- **Playwright** - Headless browser for scraping
- **BeautifulSoup** - HTML parsing
- **SQLite** - Local database (via aiosqlite)
- **FastAPI** - Web framework
- **Chart.js** - Price history charts
- **Click + Rich** - CLI interface
- **APScheduler** - Background scheduling
- **aiosmtplib** - Async email sending

## Architecture Notes

### Scrapers
- Each site has its own scraper class extending `BaseScraper`
- Uses Playwright with stealth settings to avoid detection
- Parses HTML with BeautifulSoup for reliability

### Database
- SQLite stored at `~/.itemwatcher/data.db`
- Two tables: `products` (watchlist) and `prices` (history)
- Soft-delete for products to preserve history

### Alerts
- Email notifications on price drops
- Back-in-stock alerts
- Target price alerts

## Known Limitations
- Amazon/Flipkart may block scrapers - use responsibly
- Site structure changes may break scrapers
- Personal use only (ToS considerations)

## Future Ideas
- [x] Web UI dashboard with charts ✅ (v0.2.0)
- [ ] Telegram notifications
- [ ] Random delays between requests (rate limiting)
- [ ] Proxy support
- [ ] Cookie persistence across sessions
- [ ] Price prediction using historical data
- [ ] Deal aggregator (find discounts across sites)
- [ ] Browser extension to quick-add products
- [ ] Export/import watchlists (CSV/JSON)
- [ ] Mobile-responsive UI improvements

## Maintenance
When scrapers break (sites change their HTML), check:
1. Price selectors in `amazon.py` / `flipkart.py`
2. Title/stock/seller selectors
3. Anti-bot measures (may need new stealth techniques)
