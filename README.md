A fully functional price tracker for Amazon India and Flipkart. Here's the quick rundown:

To get started:

cd /Users/astrotalk/projects/itenWatcher
pip install -e .
playwright install chromium
Usage:

# Test scraping
itemwatcher test "https://www.amazon.in/dp/BXXXXXXXX"

# Add to watchlist
itemwatcher add "https://www.flipkart.com/product-url" --target 15000

# See your watchlist
itemwatcher list

# Check prices manually
itemwatcher check

# Run background scheduler (checks every 6 hours)
python -m src.scheduler
What's included:
Scrapers for Amazon.in and Flipkart with stealth mode
SQLite database for price history (~/.itemwatcher/data.db)
Email alerts on price drops and back-in-stock
CLI with rich formatting (tables, colors)
Background scheduler for automatic checks
For email alerts:
Copy .env.example to .env and add your Gmail App Password.