"""Telegram bot alert channel"""
import logging
import os
from ..engine import AlertChannel, Alert

logger = logging.getLogger(__name__)

class TelegramChannel(AlertChannel):
    """Telegram bot alert channel"""
    
    async def send(self, alert: Alert) -> bool:
        try:
            from telegram import Bot
            
            telegram_config = self.config.get('alerting', {}).get('channels', {}).get('telegram', {})
            bot_token = telegram_config.get('bot_token') or os.getenv('NETMON_TELEGRAM_TOKEN')
            chat_id = telegram_config.get('chat_id') or os.getenv('NETMON_TELEGRAM_CHAT_ID')
            
            if not bot_token or not chat_id:
                logger.warning("Telegram bot token or chat_id not configured")
                return False
            
            bot = Bot(token=bot_token)
            await bot.send_message(chat_id=chat_id, text=alert.message)
            
            return True
        except Exception as e:
            logger.error(f"Telegram send error: {e}")
            return False


