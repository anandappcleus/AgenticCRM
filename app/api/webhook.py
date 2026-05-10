import logging
from fastapi import APIRouter, Request, BackgroundTasks, HTTPException, Query
from app.config import settings
from app.services.whatsapp import parse_incoming_message
from app.services.pipeline import process_message

router = APIRouter(redirect_slashes=False)
logger = logging.getLogger(__name__)


# ── GET: Meta webhook verification ─────────────────────────────────────────
@router.get("/")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
):
    logger.info(f"[Webhook verify] mode={hub_mode!r} token={hub_verify_token!r} expected={settings.WHATSAPP_VERIFY_TOKEN!r}")
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        # Return as plain text integer — Meta sends numeric challenge strings
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(content=hub_challenge)
    raise HTTPException(status_code=403, detail="Invalid verify token")


# ── POST: Incoming WhatsApp messages ───────────────────────────────────────
@router.post("/")
async def receive_message(request: Request, bg: BackgroundTasks):
    payload = await request.json()

    try:
        entry = payload.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})

        # Skip status updates (delivery receipts, read receipts)
        if "messages" not in value:
            return {"status": "ok", "skipped": True}

        msg_data = parse_incoming_message(value)

        # Process in background — return 200 immediately so Meta doesn't retry
        bg.add_task(process_message, msg_data)

    except Exception as e:
        logger.error(f"Webhook parsing error: {e}", exc_info=True)

    # Always return 200 to Meta
    return {"status": "ok"}
