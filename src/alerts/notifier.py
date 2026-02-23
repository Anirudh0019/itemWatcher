import aiosmtplib
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
