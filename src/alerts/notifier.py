import aiosmtplib
import httpx
from dataclasses import dataclass
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional


@dataclass
class AlertConfig:
    """Email configuration for alerts."""
    smtp_host: str
    smtp_port: int
    username: str
    password: str
    from_email: str
    to_email: str
    use_tls: bool = True


@dataclass
class TelegramConfig:
    """Telegram Bot configuration for alerts."""
    bot_token: str
    chat_id: str


class TelegramNotifier:
    """Send Telegram notifications for price alerts."""

    TELEGRAM_API = "https://api.telegram.org"

    def __init__(self, config: TelegramConfig):
        self.config = config

    async def send_price_alert(
        self,
        product_title: str,
        product_url: str,
        current_price: float,
        target_price: float,
    ):
        """Send a Telegram alert when price is at or below target."""
        diff = target_price - current_price
        text = (
            f"\U0001f6a8 PRICE ALERT: {product_title} is "
            f"\u20b9{current_price:,.2f} "
            f"(\u20b9{diff:,.2f} below your target of \u20b9{target_price:,.2f})! "
            f"Buy now: {product_url}"
        )
        await self._send_message(text)

    async def send_daily_summary(
        self,
        total_checked: int,
        closest_product: Optional[str] = None,
        closest_price: Optional[float] = None,
        closest_gap: Optional[float] = None,
    ):
        """Send a daily summary when all products are above target."""
        if closest_product and closest_price is not None and closest_gap is not None:
            text = (
                f"\U0001f4ca ItemWatcher: {total_checked} products checked, "
                f"all above target. Lowest gap: {closest_product} at "
                f"\u20b9{closest_price:,.2f} "
                f"(\u20b9{closest_gap:,.2f} above target)"
            )
        else:
            text = (
                f"\U0001f4ca ItemWatcher: {total_checked} products checked, "
                f"all above target."
            )
        await self._send_message(text)

    async def send_back_in_stock_alert(
        self,
        product_title: str,
        product_url: str,
        price: float,
    ):
        """Send alert when product is back in stock."""
        text = (
            f"\U0001f389 Back in Stock: {product_title} "
            f"at \u20b9{price:,.2f}! "
            f"Buy now: {product_url}"
        )
        await self._send_message(text)

    async def _send_message(self, text: str):
        """Send a message via Telegram Bot API."""
        url = f"{self.TELEGRAM_API}/bot{self.config.bot_token}/sendMessage"
        payload = {
            "chat_id": self.config.chat_id,
            "text": text,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=30)
            resp.raise_for_status()


class EmailNotifier:
    """Send email notifications for price drops."""

    def __init__(self, config: AlertConfig):
        self.config = config

    async def send_price_alert(
        self,
        product_title: str,
        product_url: str,
        current_price: float,
        previous_price: float,
        target_price: Optional[float],
        lowest_price: Optional[float],
    ):
        """Send an email alert for a price drop."""
        drop_amount = previous_price - current_price
        drop_percent = (drop_amount / previous_price) * 100

        subject = f"💰 Price Drop: {product_title[:50]}..."

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #2e7d32;">Price Drop Alert!</h2>

            <div style="background: #f5f5f5; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <h3 style="margin-top: 0;">{product_title}</h3>

                <p style="font-size: 24px; color: #2e7d32; margin: 10px 0;">
                    <strong>₹{current_price:,.2f}</strong>
                    <span style="font-size: 16px; color: #666; text-decoration: line-through; margin-left: 10px;">
                        ₹{previous_price:,.2f}
                    </span>
                </p>

                <p style="color: #d32f2f;">
                    ↓ ₹{drop_amount:,.2f} ({drop_percent:.1f}% off)
                </p>

                {f'<p><strong>Your target price:</strong> ₹{target_price:,.2f} {"✅ REACHED!" if current_price <= target_price else ""}</p>' if target_price else ''}

                {f'<p><strong>All-time lowest:</strong> ₹{lowest_price:,.2f}</p>' if lowest_price else ''}

                <a href="{product_url}"
                   style="display: inline-block; background: #ff9800; color: white; padding: 12px 24px;
                          text-decoration: none; border-radius: 4px; margin-top: 15px;">
                    View Product →
                </a>
            </div>

            <p style="color: #666; font-size: 12px;">
                Sent by ItemWatcher - Your personal price tracker
            </p>
        </body>
        </html>
        """

        text_body = f"""
Price Drop Alert!

{product_title}

Current Price: ₹{current_price:,.2f}
Previous Price: ₹{previous_price:,.2f}
Drop: ₹{drop_amount:,.2f} ({drop_percent:.1f}% off)

{"Target Price: ₹" + f"{target_price:,.2f}" + (" - REACHED!" if current_price <= target_price else "") if target_price else ""}
{"All-time Lowest: ₹" + f"{lowest_price:,.2f}" if lowest_price else ""}

View: {product_url}
        """

        await self._send_email(subject, text_body, html_body)

    async def send_back_in_stock_alert(self, product_title: str, product_url: str, price: float):
        """Send alert when product is back in stock."""
        subject = f"🎉 Back in Stock: {product_title[:50]}..."

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #1976d2;">Back in Stock!</h2>

            <div style="background: #f5f5f5; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <h3 style="margin-top: 0;">{product_title}</h3>

                <p style="font-size: 24px; color: #1976d2; margin: 10px 0;">
                    <strong>₹{price:,.2f}</strong>
                </p>

                <a href="{product_url}"
                   style="display: inline-block; background: #1976d2; color: white; padding: 12px 24px;
                          text-decoration: none; border-radius: 4px; margin-top: 15px;">
                    Buy Now →
                </a>
            </div>

            <p style="color: #666; font-size: 12px;">
                Sent by ItemWatcher - Your personal price tracker
            </p>
        </body>
        </html>
        """

        text_body = f"""
Back in Stock!

{product_title}
Price: ₹{price:,.2f}

Buy Now: {product_url}
        """

        await self._send_email(subject, text_body, html_body)

    async def _send_email(self, subject: str, text_body: str, html_body: str):
        """Send an email with both plain text and HTML versions."""
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = self.config.from_email
        msg['To'] = self.config.to_email

        msg.attach(MIMEText(text_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))

        await aiosmtplib.send(
            msg,
            hostname=self.config.smtp_host,
            port=self.config.smtp_port,
            username=self.config.username,
            password=self.config.password,
            start_tls=self.config.use_tls,
        )
