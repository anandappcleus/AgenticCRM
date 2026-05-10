import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.utils.intent import classify_intent
from app.services.whatsapp import parse_incoming_message


# ── Intent classifier (no API calls needed) ──────────────────────────────

def test_intent_purchase():
    assert classify_intent("Bhaiya order karna hai") == "purchase"
    assert classify_intent("I want to buy this jacket") == "purchase"


def test_intent_price():
    assert classify_intent("Kitna price hai?") == "price_inquiry"
    assert classify_intent("Any discount available?") == "price_inquiry"


def test_intent_greeting():
    assert classify_intent("Namaste bhaiya") == "greeting"
    assert classify_intent("Hi there!") == "greeting"


def test_intent_complaint():
    assert classify_intent("Item damage tha, refund chahiye") == "complaint"


def test_intent_general_fallback():
    assert classify_intent("Theek hai dekhte hain") == "general"


# ── Message parsing ───────────────────────────────────────────────────────

def test_message_parsing():
    mock_value = {
        "messages": [
            {
                "from": "919876543210",
                "text": {"body": "Bhaiya jacket ka price kya hai?"},
                "type": "text",
                "id": "test_msg_001",
                "timestamp": "1700000000",
            }
        ],
        "contacts": [{"profile": {"name": "Rahul"}}],
        "metadata": {"phone_number_id": "123456"},
    }
    msg = parse_incoming_message(mock_value)
    assert msg.phone == "919876543210"
    assert msg.name == "Rahul"
    assert msg.text == "Bhaiya jacket ka price kya hai?"
    assert msg.message_id == "test_msg_001"
    assert msg.whatsapp_phone_id == "123456"


# ── Webhook verification ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_webhook_verification():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/webhook/",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "my_secret_verify_123",
                "hub.challenge": "9999",
            },
        )
    assert resp.status_code == 200
    assert resp.json() == 9999


@pytest.mark.asyncio
async def test_webhook_verification_wrong_token():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/webhook/",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong_token",
                "hub.challenge": "9999",
            },
        )
    assert resp.status_code == 403


# ── Health check ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_check():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"
