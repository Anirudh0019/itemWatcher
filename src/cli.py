#!/usr/bin/env python3
"""ItemWatcher CLI - Track prices on Amazon & Flipkart."""

import asyncio
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from datetime import datetime

from .config import Config
from .storage import Database
from .alerts import EmailNotifier
from .watcher import scrape_product, check_product, check_all_products, get_scraper_for_url


console = Console()


def run_async(coro):
    """Helper to run async functions."""
    return asyncio.get_event_loop().run_until_complete(coro)


@click.group()
@click.option('--db', 'db_path', envvar='ITEMWATCHER_DB_PATH', help='Database path')
@click.pass_context
def cli(ctx, db_path):
    """ItemWatcher - Track prices on Amazon & Flipkart."""
    ctx.ensure_object(dict)
    config = Config.load()
    if db_path:
        config.db_path = db_path
    ctx.obj['config'] = config


@cli.command()
@click.argument('url')
@click.option('--target', '-t', type=float, help='Target price to alert on')
@click.pass_context
def add(ctx, url: str, target: float):
    """Add a product to track."""
    config = ctx.obj['config']

    # Validate URL
    if not get_scraper_for_url(url):
        console.print(f"[red]Unsupported URL. Only Amazon.in and Flipkart.com are supported.[/red]")
        return

    async def _add():
        console.print(f"[yellow]Fetching product info...[/yellow]")

        try:
            info = await scrape_product(url)
        except Exception as e:
            console.print(f"[red]Failed to fetch product: {e}[/red]")
            return

        async with Database(config.db_path) as db:
            product_id = await db.add_product(
                url=url,
                title=info.title,
                source=info.source,
                target_price=target,
            )

            # Record initial price
            await db.record_price(
                product_id,
                info.price,
                info.original_price,
                info.in_stock,
            )

        # Display result
        console.print(Panel(
            f"[bold]{info.title}[/bold]\n\n"
            f"Price: [green]₹{info.price:,.2f}[/green]"
            + (f" [dim](MRP: ₹{info.original_price:,.2f})[/dim]" if info.original_price else "")
            + (f"\nTarget: [yellow]₹{target:,.2f}[/yellow]" if target else "")
            + f"\nSource: {info.source.capitalize()}"
            + f"\nStock: {'✅ In Stock' if info.in_stock else '❌ Out of Stock'}",
            title="[green]✓ Product Added[/green]",
            border_style="green",
        ))

    run_async(_add())


@cli.command()
@click.pass_context
def list(ctx):
    """List all tracked products."""
    config = ctx.obj['config']

    async def _list():
        async with Database(config.db_path) as db:
            products = await db.get_active_products()

            if not products:
                console.print("[dim]No products being tracked. Use 'add' to add one.[/dim]")
                return

            table = Table(title="Tracked Products", show_lines=True)
            table.add_column("ID", style="cyan", width=4)
            table.add_column("Product", width=40)
            table.add_column("Current", justify="right", style="green")
            table.add_column("Lowest", justify="right", style="blue")
            table.add_column("Target", justify="right", style="yellow")
            table.add_column("Source", width=8)
            table.add_column("Last Check")

            for p in products:
                latest = await db.get_latest_price(p.id)
                lowest = await db.get_lowest_price(p.id)

                current_price = f"₹{latest.price:,.0f}" if latest else "-"
                lowest_price = f"₹{lowest:,.0f}" if lowest else "-"
                target_price = f"₹{p.target_price:,.0f}" if p.target_price else "-"

                last_check = "-"
                if p.last_checked:
                    delta = datetime.now() - p.last_checked
                    if delta.days > 0:
                        last_check = f"{delta.days}d ago"
                    elif delta.seconds > 3600:
                        last_check = f"{delta.seconds // 3600}h ago"
                    else:
                        last_check = f"{delta.seconds // 60}m ago"

                table.add_row(
                    str(p.id),
                    p.title[:38] + "..." if len(p.title) > 40 else p.title,
                    current_price,
                    lowest_price,
                    target_price,
                    p.source,
                    last_check,
                )

            console.print(table)

    run_async(_list())


@cli.command()
@click.argument('product_id', type=int)
@click.pass_context
def remove(ctx, product_id: int):
    """Remove a product from tracking."""
    config = ctx.obj['config']

    async def _remove():
        async with Database(config.db_path) as db:
            product = await db.get_product(product_id)
            if not product:
                console.print(f"[red]Product #{product_id} not found.[/red]")
                return

            await db.remove_product(product_id)
            console.print(f"[green]✓ Removed: {product.title[:50]}...[/green]")

    run_async(_remove())


@cli.command()
@click.argument('product_id', type=int)
@click.option('--limit', '-n', default=20, help='Number of records to show')
@click.pass_context
def history(ctx, product_id: int, limit: int):
    """Show price history for a product."""
    config = ctx.obj['config']

    async def _history():
        async with Database(config.db_path) as db:
            product = await db.get_product(product_id)
            if not product:
                console.print(f"[red]Product #{product_id} not found.[/red]")
                return

            prices = await db.get_price_history(product_id, limit=limit)
            lowest = await db.get_lowest_price(product_id)

            if not prices:
                console.print("[dim]No price history yet.[/dim]")
                return

            console.print(f"\n[bold]{product.title}[/bold]\n")

            table = Table(show_header=True)
            table.add_column("Date", style="dim")
            table.add_column("Price", justify="right")
            table.add_column("MRP", justify="right", style="dim")
            table.add_column("Stock")

            for p in prices:
                price_style = "green bold" if p.price == lowest else "green"
                stock = "✅" if p.in_stock else "❌"
                mrp = f"₹{p.original_price:,.0f}" if p.original_price else "-"

                table.add_row(
                    p.recorded_at.strftime("%Y-%m-%d %H:%M"),
                    f"[{price_style}]₹{p.price:,.0f}[/{price_style}]",
                    mrp,
                    stock,
                )

            console.print(table)
            console.print(f"\n[blue]Lowest price: ₹{lowest:,.0f}[/blue]")

    run_async(_history())


@cli.command()
@click.argument('product_id', type=int)
@click.argument('target_price', type=float)
@click.pass_context
def target(ctx, product_id: int, target_price: float):
    """Set a target price alert for a product."""
    config = ctx.obj['config']

    async def _target():
        async with Database(config.db_path) as db:
            product = await db.get_product(product_id)
            if not product:
                console.print(f"[red]Product #{product_id} not found.[/red]")
                return

            await db.set_target_price(product_id, target_price)
            console.print(f"[green]✓ Target set to ₹{target_price:,.0f} for: {product.title[:50]}...[/green]")

    run_async(_target())


@cli.command()
@click.option('--id', 'product_id', type=int, help='Check specific product')
@click.pass_context
def check(ctx, product_id: int):
    """Check prices now (runs scraper)."""
    config = ctx.obj['config']

    # Set up notifier if configured
    notifier = None
    if config.email:
        notifier = EmailNotifier(config.email)

    async def _check():
        async with Database(config.db_path) as db:
            if product_id:
                product = await db.get_product(product_id)
                if not product:
                    console.print(f"[red]Product #{product_id} not found.[/red]")
                    return

                console.print(f"[yellow]Checking: {product.title[:50]}...[/yellow]")
                info = await check_product(db, product, notifier)

                if info:
                    console.print(f"[green]✓ ₹{info.price:,.0f}[/green]" +
                                  (f" [dim](was ₹{info.original_price:,.0f})[/dim]" if info.original_price else ""))
            else:
                console.print("[yellow]Checking all products...[/yellow]\n")
                await check_all_products(db, notifier)
                console.print("\n[green]✓ Done![/green]")

    run_async(_check())


@cli.command()
@click.argument('url')
@click.pass_context
def test(ctx, url: str):
    """Test scraping a URL without adding it."""
    if not get_scraper_for_url(url):
        console.print(f"[red]Unsupported URL. Only Amazon.in and Flipkart.com are supported.[/red]")
        return

    async def _test():
        console.print(f"[yellow]Testing scraper...[/yellow]\n")

        try:
            info = await scrape_product(url)

            console.print(Panel(
                f"[bold]{info.title}[/bold]\n\n"
                f"Price: [green]₹{info.price:,.2f}[/green]"
                + (f"\nMRP: [dim]₹{info.original_price:,.2f}[/dim]" if info.original_price else "")
                + (f"\nDiscount: [red]{info.discount_percent}% off[/red]" if info.discount_percent else "")
                + f"\nStock: {'✅ In Stock' if info.in_stock else '❌ Out of Stock'}"
                + (f"\nSeller: {info.seller}" if info.seller else "")
                + f"\nSource: {info.source.capitalize()}",
                title="[green]✓ Scrape Successful[/green]",
                border_style="green",
            ))

        except Exception as e:
            console.print(f"[red]Scrape failed: {e}[/red]")

    run_async(_test())


@cli.command()
@click.option('--host', default='0.0.0.0', help='Host to bind to')
@click.option('--port', default=8000, type=int, help='Port to bind to')
@click.pass_context
def web(ctx, host: str, port: int):
    """Start the web UI server."""
    console.print(f"[green]Starting ItemWatcher Web UI...[/green]")
    console.print(f"[yellow]Open http://localhost:{port} in your browser[/yellow]\n")

    from .web.app import start_server
    start_server(host=host, port=port)


def main():
    cli(obj={})


if __name__ == '__main__':
    main()
