"""
crm_crew.py — Background CRM Intelligence Crew (CrewAI 1.14.x)

Runs NON-BLOCKING after the WhatsApp reply is already sent.
Zero impact on reply latency.

Two-agent sequential crew:
  1. CustomerProfilerAgent  → extracts interests, budget, sentiment from conversation
  2. LeadScoringAgent       → AI-powered lead score 0-100 + next action recommendation

Output is used to update Lead.score + Lead.status in PostgreSQL.
Called via asyncio.to_thread() since CrewAI's kickoff() is synchronous.
"""

import json
import logging
import os
from typing import Dict, List

from crewai import Agent, Task, Crew, Process, LLM
from app.config import settings

# Disable CrewAI's anonymous telemetry
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")

logger = logging.getLogger(__name__)


def _make_llm() -> "LLM":
    """
    Build a CrewAI LLM instance for NVIDIA NIM (OpenAI-compatible).
    Uses the 'hosted_vllm' native provider prefix — works without litellm.
    Falls back gracefully if CrewAI LLM init fails.
    """
    raw_model = settings.OPENAI_MODEL
    # hosted_vllm is CrewAI's native provider for OpenAI-compatible endpoints
    # (does not require the litellm extra package)
    crew_model = (
        raw_model
        if raw_model.startswith(("gpt-", "o1-", "o3-", "hosted_vllm/"))
        else f"hosted_vllm/{raw_model}"
    )
    return LLM(
        model=crew_model,
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
        temperature=0.2,
        max_tokens=400,
    )


def _make_agents(llm: "LLM"):
    profiler = Agent(
        role="Customer Behavior Analyst",
        goal="Extract a structured JSON customer profile from a WhatsApp sales conversation.",
        backstory=(
            "You are an expert at analyzing sales conversations for Indian SME businesses. "
            "You understand Hinglish, Hindi, and English. You identify what the customer wants, "
            "their budget, sentiment, and purchase likelihood from casual chat."
        ),
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )
    scorer = Agent(
        role="Sales Lead Scoring Specialist",
        goal="Score sales leads 0-100 with clear reasoning and recommend the next best action.",
        backstory=(
            "You are a CRM specialist for Indian small businesses. "
            "You score leads based on purchase intent, engagement, and budget signals. "
            "Your scores help business owners prioritise who to follow up with first."
        ),
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )
    return profiler, scorer


# ---------------------------------------------------------------------------
# Crew builder — fresh tasks per request, shared agents
# ---------------------------------------------------------------------------

def _build_crew(profiler_agent: Agent, scorer_agent: Agent) -> Crew:
    """Build a crew with parameterized task descriptions (inputs via kickoff)."""

    profile_task = Task(
        description="""Analyze the WhatsApp conversation below and extract a customer profile.

Customer name: {customer_name}
Detected intent: {intent}

Conversation:
{conversation}

Return ONLY a valid JSON object — no markdown, no explanation:
{{
  "interests": ["list of products or categories the customer mentioned"],
  "budget": <max budget in INR as integer, or null if not mentioned>,
  "preferred_sizes": ["S", "M", "L", "XL"] or [],
  "sentiment": "positive|neutral|negative",
  "purchase_likelihood": "high|medium|low",
  "language": "hindi|english|hinglish"
}}""",
        expected_output="Valid JSON object with the customer profile fields",
        agent=profiler_agent,
    )

    score_task = Task(
        description="""Using the customer profile from the previous task, score this lead.

Customer: {customer_name} | Intent: {intent}

Return ONLY a valid JSON object — no markdown, no explanation:
{{
  "score": <integer 0-100>,
  "status": "hot|warm|cold",
  "reasoning": "one clear sentence explaining this score",
  "next_action": "one specific action the business owner should take"
}}

Scoring guide:
- 90-100: Customer is ready to buy NOW                       → hot
- 70-89:  Strong interest, just needs a small nudge          → hot
- 50-69:  Browsing, can convert with a targeted follow-up    → warm
- 30-49:  Low intent, early research stage                   → warm
- 0-29:   Just a greeting or unresolved complaint            → cold""",
        expected_output="Valid JSON object with score, status, reasoning, next_action",
        agent=scorer_agent,
        context=[profile_task],
    )

    return Crew(
        agents=[profiler_agent, scorer_agent],
        tasks=[profile_task, score_task],
        process=Process.sequential,
        verbose=False,
    )


# ---------------------------------------------------------------------------
# Public API — called via asyncio.to_thread() from pipeline
# ---------------------------------------------------------------------------

def run_crew(conversation: List[Dict], intent: str, customer_name: str) -> dict:
    """
    Run the CRM intelligence crew synchronously.
    Called via asyncio.to_thread() from the async pipeline — does not block the
    event loop.

    Returns:
        {
            "profile": { interests, budget, sentiment, purchase_likelihood, ... },
            "lead":    { score, status, reasoning, next_action }
        }
        or {} on failure.
    """
    # Lazy-initialize LLM and agents inside the function so import never fails.
    try:
        llm = _make_llm()
        profiler_agent, scorer_agent = _make_agents(llm)
    except Exception as exc:
        logger.warning(f"[CRMCrew] LLM init failed — crew disabled: {exc}")
        return {}

    # Format conversation list as readable text for the agents
    lines = []
    for msg in conversation:
        label = "Customer" if msg["role"] == "user" else "Assistant"
        lines.append(f"{label}: {msg['content']}")
    conversation_text = "\n".join(lines) or "(no prior conversation)"

    try:
        crew = _build_crew(profiler_agent, scorer_agent)
        result = crew.kickoff(inputs={
            "conversation": conversation_text,
            "customer_name": customer_name,
            "intent": intent,
        })

        # task_outputs[0] = profiler output, result.raw = scorer output (last task)
        task_outputs = result.tasks_output or []
        profile_data = _safe_json(task_outputs[0].raw if task_outputs else "")
        lead_data = _safe_json(result.raw or "")

        logger.info(
            f"[CRMCrew] customer={customer_name!r} intent={intent} "
            f"score={lead_data.get('score')} status={lead_data.get('status')!r} "
            f"likelihood={profile_data.get('purchase_likelihood')!r}"
        )
        return {"profile": profile_data, "lead": lead_data}

    except Exception as e:
        logger.error(
            f"[CRMCrew] Crew failed for customer={customer_name!r} intent={intent}: {e}",
            exc_info=True,
        )
        return {}


def _safe_json(text: str) -> dict:
    """Parse JSON from LLM output, stripping markdown code fences if present."""
    text = (text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, ValueError):
        return {}
