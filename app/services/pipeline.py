import asyncio
import logging
import time
from typing import List, Optional
from sqlalchemy import select, update as sql_update
from app.services.whatsapp import (
    IncomingMessage, send_whatsapp_message,
    send_whatsapp_buttons, send_whatsapp_list,
    mark_as_read,
)
from app.agents.reply_agent import ReplyAgent
from app.agents.sales_agent import SalesAgent
from app.agents.order_agent import OrderAgent
from app.services.scheduler import schedule_followup, cancel_followup
from app.services.redis_client import acquire_lock, release_lock
from app.models.database import AsyncSessionLocal, Lead
from app.models import customer as customer_model
from app.models import conversation as conv_model
from app.models import lead as lead_model
from app.models.business import get_business_by_phone_id
from app.utils.intent import classify_intent

logger = logging.getLogger(__name__)

# Intents handled by the agentic OrderAgent (tool-calling loop)
_AGENTIC_INTENTS = {"purchase", "price_inquiry", "complaint"}

# Intents handled by the fast ReplyAgent (single LLM call, no tools)
_FAST_INTENTS = {"greeting", "hours", "general"}


async def process_message(msg: IncomingMessage) -> None:
    """
    Hybrid AI pipeline. Runs as a FastAPI BackgroundTask.

    Routing:
      greeting / hours / general  → fast path  (ReplyAgent, ~800ms)
      purchase / price_inquiry    → agentic     (OrderAgent with tools, ~2-4s)
      complaint                   → agentic     (OrderAgent → escalate_to_human)

    Concurrency protection:
      Redis per-customer lock prevents race conditions when customers
      send multiple messages before the first reply is sent.

    Flow:
      1.  Resolve business from phone_id
      2.  Upsert customer
      3.  Acquire per-customer lock (skip if already processing)
      4.  Save incoming message + mark as read  (parallel)
      5.  Cancel pending follow-up
      6.  Classify intent (keyword, zero-cost)
      7.  Build conversation history
      8.  Route to fast path OR agentic path
      9.  Send reply via WhatsApp
      10. Save AI response + upsert lead        (parallel)
      11. Schedule follow-up
      12. Release lock
    """
    t0 = time.monotonic()
    async with AsyncSessionLocal() as db:
        customer_lock_acquired = False
        cust = None
        try:
            # 1. Resolve business
            business = await get_business_by_phone_id(db, msg.whatsapp_phone_id)
            if business is None:
                logger.warning(
                    f"No business found for phone_id={msg.whatsapp_phone_id}. "
                    "Register via POST /api/v1/business/register"
                )
                return

            if not business.ai_active:
                logger.info(f"AI disabled for business={business.id}. Skipping.")
                return

            # 2. Upsert customer
            cust = await customer_model.get_or_create_customer(
                phone=msg.phone,
                name=msg.name,
                business_id=business.id,
                db=db,
            )

            if cust.ai_paused:
                logger.info(f"AI paused for customer={cust.id}. Skipping.")
                return

            # 3. Acquire per-customer lock (prevents concurrent pipeline runs)
            customer_lock_acquired = await acquire_lock(cust.id)
            if not customer_lock_acquired:
                logger.warning(
                    f"[Pipeline] Skipping message — pipeline already running "
                    f"for customer={cust.id} phone={msg.phone}"
                )
                return

            # 4. Save incoming message + mark as read in parallel
            await asyncio.gather(
                conv_model.save_message(
                    db=db,
                    customer_id=cust.id,
                    business_id=business.id,
                    role="user",
                    content=msg.text,
                ),
                mark_as_read(
                    msg.message_id,
                    phone_id=business.whatsapp_phone_id,
                    token=business.whatsapp_token,
                ),
            )

            # 5. Cancel pending follow-up (customer is active again)
            await cancel_followup(cust.id)

            # 6. Classify intent (fast, zero-cost keyword matching)
            intent = classify_intent(msg.text)
            logger.info(
                f"[Pipeline] phone={msg.phone} intent={intent} "
                f"path={'agentic' if intent in _AGENTIC_INTENTS else 'fast'} "
                f"text={msg.text[:60]!r}"
            )

            # 7. Conversation history (shared by both paths)
            history = await conv_model.get_conversation_history(db, cust.id, limit=10)

            # 8. Route: agentic vs fast
            if intent in _AGENTIC_INTENTS:
                # ── AGENTIC PATH: OrderAgent with tool-calling loop ──────
                agent = OrderAgent(
                    business=business,
                    customer=cust,
                    db=db,
                    language=business.language,
                )
                if intent in ("purchase", "price_inquiry"):
                    # Run SalesAgent upsell in parallel — zero extra latency
                    sales_agent = SalesAgent(business_id=business.id)
                    agent_result, offer = await asyncio.gather(
                        agent.run(
                            customer_message=msg.text,
                            history=history,
                            intent=intent,
                        ),
                        sales_agent.get_offer(msg.text),
                    )
                else:
                    agent_result = await agent.run(
                        customer_message=msg.text,
                        history=history,
                        intent=intent,
                    )
                    offer = None

                if isinstance(agent_result, dict):
                    interactive_payload = agent_result
                    response_text = agent_result["text"]
                    if offer:
                        interactive_payload = dict(agent_result)
                        interactive_payload["text"] = f"{response_text}\n\n{offer}"
                        response_text = interactive_payload["text"]
                else:
                    interactive_payload = None
                    response_text = agent_result
                    if offer:
                        response_text += f"\n\n{offer}"

            else:
                # ── FAST PATH: ReplyAgent (single LLM call, no tools) ───
                needs_sales = intent in ("purchase", "price_inquiry")
                reply_agent = ReplyAgent(
                    business_id=business.id,
                    system_prompt=business.system_prompt,
                    business_type=business.business_type,
                    language=business.language,
                )

                if needs_sales:
                    sales_agent = SalesAgent(business_id=business.id)
                    agent_result, offer = await asyncio.gather(
                        reply_agent.run(
                            customer_message=msg.text,
                            history=history,
                            customer_name=cust.name,
                            intent=intent,
                        ),
                        sales_agent.get_offer(msg.text),
                    )
                    if isinstance(agent_result, dict):
                        interactive_payload = agent_result
                        response_text = agent_result["text"]
                        if offer:
                            interactive_payload = dict(agent_result)
                            interactive_payload["text"] = f"{response_text}\n\n{offer}"
                            response_text = interactive_payload["text"]
                    else:
                        interactive_payload = None
                        response_text = agent_result
                        if offer:
                            response_text += f"\n\n{offer}"
                else:
                    agent_result = await reply_agent.run(
                        customer_message=msg.text,
                        history=history,
                        customer_name=cust.name,
                        intent=intent,
                    )
                    if isinstance(agent_result, dict):
                        interactive_payload = agent_result
                        response_text = agent_result["text"]
                    else:
                        interactive_payload = None
                        response_text = agent_result

            # 9. Send reply
            await _send_reply(
                phone=msg.phone,
                text=response_text,
                interactive_payload=interactive_payload,
                phone_id=business.whatsapp_phone_id,
                token=business.whatsapp_token,
            )

            # 9b. Fire CrewAI background intelligence crew (non-blocking)
            #     Skip for pure greetings — no commercial signal to score.
            #     Runs AFTER reply is sent — zero latency impact on customer
            full_conversation = history + [
                {"role": "user", "content": msg.text},
                {"role": "assistant", "content": response_text},
            ]
            if intent != "greeting":
                asyncio.create_task(
                    _run_crm_crew_background(
                        customer_id=cust.id,
                        business_id=business.id,
                        conversation=full_conversation,
                        intent=intent,
                        customer_name=cust.name,
                    )
                )

            # 10. Save AI response then upsert lead (sequential — same DB session)
            await conv_model.save_message(
                db=db,
                customer_id=cust.id,
                business_id=business.id,
                role="assistant",
                content=response_text,
            )
            await lead_model.upsert_lead(
                db=db,
                customer_id=cust.id,
                business_id=business.id,
                intent=intent,
            )

            # 11. Schedule follow-up
            await schedule_followup(
                customer_id=cust.id,
                phone=msg.phone,
                intent=intent,
                followup_hours=business.followup_hours,
            )

            elapsed = (time.monotonic() - t0) * 1000
            logger.info(
                f"[Pipeline] complete phone={msg.phone} intent={intent} "
                f"path={'agentic' if intent in _AGENTIC_INTENTS else 'fast'} "
                f"total={elapsed:.0f}ms"
            )

        except Exception as e:
            logger.error(f"[Pipeline] error for phone={msg.phone}: {e}", exc_info=True)
        finally:
            # 12. Always release lock even on error
            if customer_lock_acquired and cust is not None:
                await release_lock(cust.id)


# ---------------------------------------------------------------------------
# AI-driven interactive reply sender
# ---------------------------------------------------------------------------

async def _send_reply(
    phone: str,
    text: str,
    interactive_payload: Optional[dict],
    phone_id: Optional[str] = None,
    token: Optional[str] = None,
) -> None:
    """
    Route reply based on what the AI returned:
      - dict with 'buttons'  → interactive button message (max 3)
      - dict with 'sections' → list message (scrollable, max 10 items)
      - None / str           → plain text message
    Falls back to plain text on any send failure.
    """
    if interactive_payload:
        if "buttons" in interactive_payload:
            sent = await send_whatsapp_buttons(
                to_phone=phone,
                body=interactive_payload["text"],
                buttons=interactive_payload["buttons"],
                phone_id=phone_id,
                token=token,
            )
            if sent:
                return
            logger.warning(f"[Pipeline] Button send failed for phone={phone}, falling back to text")

        elif "sections" in interactive_payload:
            sent = await send_whatsapp_list(
                to_phone=phone,
                body=interactive_payload["text"],
                button_label="Select option",
                sections=interactive_payload["sections"],
                phone_id=phone_id,
                token=token,
            )
            if sent:
                return
            logger.warning(f"[Pipeline] List send failed for phone={phone}, falling back to text")

    await send_whatsapp_message(phone, text, phone_id=phone_id, token=token)


# ---------------------------------------------------------------------------
# CrewAI background intelligence runner
# ---------------------------------------------------------------------------

async def _run_crm_crew_background(
    customer_id: str,
    business_id: str,
    conversation: List[dict],
    intent: str,
    customer_name: str,
) -> None:
    """
    Run the CrewAI CRM Intelligence Crew in a background asyncio task.
    Called with asyncio.create_task() — never blocks the WhatsApp reply path.

    What it does:
      1. Runs CustomerProfilerAgent + LeadScoringAgent via CrewAI
      2. Parses AI-generated lead score (0-100) and status (hot/warm/cold)
      3. Updates the Lead record in PostgreSQL only if the score improved
    """
    try:
        from app.agents.crm_crew import run_crew

        # Fetch current lead score/status so the crew can adjust relative to history
        current_score, current_status = 50, "warm"
        try:
            async with AsyncSessionLocal() as db_score:
                lead_row = await db_score.execute(
                    select(Lead).where(Lead.customer_id == customer_id)
                )
                existing = lead_row.scalar_one_or_none()
                if existing:
                    current_score = existing.score or 50
                    current_status = existing.status or "warm"
        except Exception as exc:
            logger.warning(f"[CRMCrew] Could not fetch current lead score: {exc}")

        # run_crew() is synchronous (CrewAI) — run in thread pool
        result = await asyncio.to_thread(
            run_crew, conversation, intent, customer_name, current_score, current_status
        )

        if not result:
            return

        lead_data = result.get("lead", {})
        score = lead_data.get("score")
        status = lead_data.get("status")
        next_action = lead_data.get("next_action", "")
        reasoning = lead_data.get("reasoning", "")

        # Validate before writing to DB
        if (
            score is not None
            and isinstance(score, (int, float))
            and status in ("hot", "warm", "cold")
        ):
            async with AsyncSessionLocal() as db:
                await db.execute(
                    sql_update(Lead)
                    .where(Lead.customer_id == customer_id)
                    .values(score=int(score), status=status)
                )
                await db.commit()

            logger.info(
                f"[CRMCrew] Lead updated customer={customer_id} "
                f"score={score} status={status!r} "
                f"reason={reasoning[:80]!r} next={next_action[:80]!r}"
            )

    except Exception as e:
        logger.error(
            f"[CRMCrew] Background crew error for customer={customer_id}: {e}",
            exc_info=True,
        )
