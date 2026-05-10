import httpx
import logging
from dataclasses import dataclass
from typing import List, Optional
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
    interactive_id: Optional[str] = None  # set when customer taps a button


def parse_incoming_message(value: dict) -> IncomingMessage:
    """Parse the Meta webhook payload into a clean IncomingMessage dataclass."""
    msg = value["messages"][0]
    contact = value.get("contacts", [{}])[0]
    metadata = value.get("metadata", {})

    msg_type = msg.get("type", "text")
    interactive_id: Optional[str] = None

    if msg_type == "text":
        text = msg.get("text", {}).get("body", "")
    elif msg_type == "interactive":
        interactive = msg.get("interactive", {})
        sub_type = interactive.get("type", "")
        if sub_type == "button_reply":
            button_reply = interactive.get("button_reply", {})
            text = button_reply.get("title", "")
            interactive_id = button_reply.get("id", "")
        elif sub_type == "list_reply":
            list_reply = interactive.get("list_reply", {})
            text = list_reply.get("title", "")
            interactive_id = list_reply.get("id", "")
        else:
            text = ""
    else:
        # audio, image, etc. — not yet supported
        text = f"[{msg_type} message]"

    return IncomingMessage(
        phone=msg["from"],
        name=contact.get("profile", {}).get("name", "Customer"),
        text=text,
        message_id=msg["id"],
        timestamp=int(msg["timestamp"]),
        whatsapp_phone_id=metadata.get("phone_number_id", settings.WHATSAPP_PHONE_ID),
        interactive_id=interactive_id,
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
                    f"[WhatsApp] Send failed {resp.status_code} to={to_phone}: {resp.text}"
                )
                return False
            logger.info(f"[WhatsApp] Message sent to={to_phone} len={len(text)}")
            return True
    except Exception as e:
        logger.error(f"[WhatsApp] Network error sending to={to_phone}: {e}", exc_info=True)
        return False


async def send_whatsapp_buttons(
    to_phone: str,
    body: str,
    buttons: List[dict],
    header: Optional[str] = None,
    footer: Optional[str] = None,
) -> bool:
    """
    Send an interactive button message (max 3 buttons).
    Each button: {"id": "unique_id", "title": "Button Label"}
    """
    url = f"{GRAPH_API_BASE}/{settings.WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    interactive: dict = {
        "type": "button",
        "body": {"text": body},
        "action": {
            "buttons": [
                {"type": "reply", "reply": {"id": b["id"], "title": b["title"][:20]}}
                for b in buttons[:3]  # WhatsApp max = 3 buttons
            ]
        },
    }
    if header:
        interactive["header"] = {"type": "text", "text": header}
    if footer:
        interactive["footer"] = {"text": footer}

    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "interactive",
        "interactive": interactive,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code != 200:
                logger.error(f"[WhatsApp] Buttons send failed {resp.status_code} to={to_phone}: {resp.text}")
                return False
            logger.info(f"[WhatsApp] Buttons sent to={to_phone} buttons={[b['id'] for b in buttons]}")
            return True
    except Exception as e:
        logger.error(f"[WhatsApp] Network error sending buttons to={to_phone}: {e}", exc_info=True)
        return False


async def send_whatsapp_list(
    to_phone: str,
    body: str,
    button_label: str,
    sections: List[dict],
    header: Optional[str] = None,
    footer: Optional[str] = None,
) -> bool:
    """
    Send an interactive list message (scrollable menu, max 10 items total).
    Each section: {"title": "Section Name", "rows": [{"id": "id", "title": "Item", "description": "desc"}]}
    """
    url = f"{GRAPH_API_BASE}/{settings.WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    interactive: dict = {
        "type": "list",
        "body": {"text": body},
        "action": {
            "button": button_label[:20],
            "sections": sections,
        },
    }
    if header:
        interactive["header"] = {"type": "text", "text": header}
    if footer:
        interactive["footer"] = {"text": footer}

    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "interactive",
        "interactive": interactive,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code != 200:
                logger.error(f"[WhatsApp] List send failed {resp.status_code} to={to_phone}: {resp.text}")
                return False
            logger.info(f"[WhatsApp] List sent to={to_phone} sections={len(sections)}")
            return True
    except Exception as e:
        logger.error(f"[WhatsApp] Network error sending list to={to_phone}: {e}", exc_info=True)
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
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code != 200:
                logger.warning(f"[WhatsApp] mark_as_read {resp.status_code} for msg={message_id}: {resp.text}")
    except Exception as e:
        logger.warning(f"[WhatsApp] mark_as_read network error for msg={message_id}: {e}")
