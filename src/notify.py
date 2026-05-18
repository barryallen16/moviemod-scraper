from __future__ import annotations

import asyncio
import logging

from telegram import Bot

log = logging.getLogger(__name__)


def send_telegram_message(bot_token: str, group_chat_id: str, message_text: str) -> None:
    """Send a message to a Telegram group. Blocks until complete."""
    loop = asyncio.new_event_loop()
    try:
        bot = Bot(token=bot_token)
        loop.run_until_complete(bot.send_message(chat_id=group_chat_id, text=message_text))
    except Exception:
        log.exception("Failed to send Telegram message")
    finally:
        loop.close()


def notify_error(bot_token: str, group_chat_id: str, error_message: str) -> None:
    """Send an error notification to Telegram."""
    send_telegram_message(bot_token, group_chat_id, f"Error: {error_message}")


def notify_complete(bot_token: str, group_chat_id: str, total_time: float) -> None:
    """Send a completion notification with elapsed time."""
    send_telegram_message(bot_token, group_chat_id, f"Total time taken: {total_time:.1f} seconds")


def notify_no_season(bot_token: str, group_chat_id: str, description: str, links: str) -> None:
    """Notify when a zip entry has no season info."""
    send_telegram_message(
        bot_token, group_chat_id, f"no season mentioned : {description}\n{links}"
    )


def notify_links(
    bot_token: str, group_chat_id: str, title: str, links: list[str]
) -> None:
    """Send final download links to Telegram."""
    if not links:
        return
    send_telegram_message(bot_token, group_chat_id, f"{title}\n" + "\n".join(links))
    log.debug("Sent %d links to Telegram for %s", len(links), title[:60])
