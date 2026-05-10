import httpx
import logging
from dataclasses import dataclass
from typing import Optional
from app.config import settings

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v19.0"


@dataclass
class IncomingMessage:
    phone: str
    name: str
    text: str
    message_id: str
    timestamp: int
    whatsapp_phone_id: str  # which business phone received this


def parse_incoming_message(value: dict) -> IncomingMessage:
    """Parse the Meta webhook payload into a clean IncomingMessage dataclass."""
    msg = value["messages"][0]
    contact = value.get("contacts", [{}])[0]
    metadata = value.get("metadata", {})

    return IncomingMessage(
        phone=msg["from"],
        name=contact.get("profile", {}).get("name", "Customer"),
        text=msg.get("text", {}).get("body", ""),
        message_id=msg["id"],
        timestamp=int(msg["timestamp"]),
        whatsapp_phone_id=metadata.get("phone_number_id", settings.WHATSAPP_PHONE_ID),
    )


async def send_whatsapp_message(to_phone: str, text: str) -> bool:
    """Send a text message via Meta WhatsApp Cloud API."""
    url = f"{GRAPH_API_BASE}/{settings.WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": text},
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code != 200:
                logger.error(
                    f"WhatsApp API error {resp.status_code}: {resp.text}"
                )
                return False
            return True
    except Exception as e:
        logger.error(f"Failed to send WhatsApp message to {to_phone}: {e}")
        return False


async def mark_as_read(message_id: str) -> None:
    """Mark an incoming message as read (shows double blue ticks)."""
    url = f"{GRAPH_API_BASE}/{settings.WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json=payload, headers=headers)
    except Exception as e:
        logger.warning(f"Could not mark message as read: {e}")
