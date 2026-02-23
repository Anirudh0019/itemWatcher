import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from .alerts.notifier import AlertConfig, TelegramConfig


@dataclass
class Config:
    """Application configuration."""
    db_path: str
    check_interval_hours: int
    email: Optional[AlertConfig]
    telegram: Optional[TelegramConfig]

    @classmethod
    def load(cls, env_file: Optional[str] = None) -> 'Config':
        """Load configuration from environment variables."""
        if env_file:
            load_dotenv(env_file)
        else:
            # Try common locations
            for path in ['.env', Path.home() / '.itemwatcher' / '.env']:
                if Path(path).exists():
                    load_dotenv(path)
                    break

        # Database path
        db_path = os.getenv('ITEMWATCHER_DB_PATH')
        if not db_path:
            db_path = str(Path.home() / '.itemwatcher' / 'data.db')

        # Check interval
        check_interval = int(os.getenv('ITEMWATCHER_CHECK_INTERVAL_HOURS', '6'))

        # Email config (optional)
        email = None
        smtp_host = os.getenv('SMTP_HOST')
        if smtp_host:
            email = AlertConfig(
                smtp_host=smtp_host,
                smtp_port=int(os.getenv('SMTP_PORT', '587')),
                username=os.getenv('SMTP_USERNAME', ''),
                password=os.getenv('SMTP_PASSWORD', ''),
                from_email=os.getenv('SMTP_FROM_EMAIL', ''),
                to_email=os.getenv('ALERT_TO_EMAIL', ''),
                use_tls=os.getenv('SMTP_USE_TLS', 'true').lower() == 'true',
            )

        # Telegram config (optional)
        telegram = None
        telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')
        if telegram_bot_token and telegram_chat_id:
            telegram = TelegramConfig(
                bot_token=telegram_bot_token,
                chat_id=telegram_chat_id,
            )

        return cls(
            db_path=db_path,
            check_interval_hours=check_interval,
            email=email,
            telegram=telegram,
        )
