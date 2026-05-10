# Agentic WhatsApp CRM

> Production-ready MVP — AI-powered WhatsApp CRM for Indian Tier-2/3 SMEs.

A SaaS platform that connects to a local business's WhatsApp number and uses AI agents to automatically reply to customers, follow up on cold leads, suggest products, and give the business owner a live CRM dashboard — without them writing a single message.

---

## Target Market

- Clothing stores, salons, restaurants, coaching centers, clinics, hardware shops in Tier-2/3 cities (Asansol, Durgapur, Dhanbad, Burdwan)
- Owners receiving 50–150 WhatsApp messages/day who reply manually and miss nights/weekends
- Willingness to pay ₹1,000–₹3,000/month if it saves time

---

## Core MVP Features

| # | Feature | Description |
|---|---------|-------------|
| 1 | **Auto-Reply Agent** | Reads incoming WhatsApp messages, understands intent, responds in Hindi/Hinglish using the business's product catalog and FAQs |
| 2 | **Follow-up Agent** | Detects when a customer goes quiet after showing interest; sends a warm follow-up after 12–24 hours automatically |
| 3 | **Sales Agent** | Proactively suggests products and promotes offers based on conversation context and customer history |
| 4 | **Customer CRM** | Stores customer name + number, tracks every conversation, tags leads as Hot/Warm/Cold automatically |
| 5 | **iOS Dashboard** | Business owner views all chats, lead status, follow-up queue, and daily stats from their iPhone |
| 6 | **Manual Override** | Owner can take over any conversation, pause AI for specific customers, and add custom replies |

---

## Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Backend | Python 3.11 + FastAPI | Async-native, auto OpenAPI docs |
| WhatsApp | Meta WhatsApp Cloud API | Free for first 1,000 conversations/month |
| AI Core | OpenAI GPT-4o | Best Hindi/Hinglish understanding; ~$0.005/1K input tokens |
| RAG | ChromaDB (local) | Zero-cost, embedded, no network latency |
| Embeddings | OpenAI text-embedding-3-small | ~₹2–5 one-time per client to embed full catalog |
| Database | Supabase (PostgreSQL) | Managed Postgres + built-in auth; free tier covers 5 clients |
| ORM | SQLAlchemy 2.0 + Alembic | Async support + migrations |
| Scheduler | APScheduler | In-process; no Redis needed for MVP |
| Task Queue | FastAPI BackgroundTasks | Built-in async processing |
| Mobile | Swift 5.9 + SwiftUI | Native iOS dashboard for business owners |
| HTTP Client | httpx (async) | Meta API + OpenAI calls |
| Hosting | Railway.app | $5–20/month; zero DevOps |
| Monitoring | Railway Logs + Sentry (free) | Error tracking at no cost |
| Dev Tunneling | ngrok | Expose localhost for WhatsApp webhook testing |

---

## Project Structure

```
whatsapp-crm/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app entry point
│   ├── config.py                # Settings from env vars
│   ├── api/
│   │   ├── webhook.py           # POST /webhook — WhatsApp handler
│   │   ├── dashboard.py         # GET endpoints for iOS app
│   │   └── business.py          # Business setup / catalog upload
│   ├── agents/
│   │   ├── reply_agent.py       # Reply Agent — GPT-4o + RAG
│   │   ├── followup_agent.py    # Follow-up Agent — scheduler
│   │   ├── sales_agent.py       # Sales Agent — offer suggester
│   │   └── base_agent.py        # Shared prompt builder / caller
│   ├── services/
│   │   ├── whatsapp.py          # Meta API send/receive helpers
│   │   ├── openai_client.py     # OpenAI call wrapper
│   │   ├── rag.py               # ChromaDB RAG pipeline
│   │   └── scheduler.py         # APScheduler setup
│   ├── models/
│   │   ├── database.py          # SQLAlchemy engine + session
│   │   ├── business.py          # Business model
│   │   ├── customer.py          # Customer model
│   │   ├── conversation.py      # Conversation + Message models
│   │   └── lead.py              # Lead tracking model
│   └── utils/
│       ├── intent.py            # Intent classifier helper
│       └── language.py          # Hindi/Hinglish text helpers
├── migrations/                  # Alembic migration files
├── chroma_db/                   # ChromaDB persistence folder
├── ios/                         # WhatsApp CRM iOS app (Xcode)
│   └── WhatsAppCRM.xcodeproj
├── .env                         # Environment variables (never commit!)
├── requirements.txt
├── Dockerfile
├── railway.json
└── README.md
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- Docker (for local PostgreSQL)
- ngrok (for webhook testing)
- Meta Developer account with WhatsApp Cloud API access
- OpenAI API key

### Local Setup

```bash
# 1. Clone and set up virtual environment
git clone https://github.com/yourname/whatsapp-crm
cd whatsapp-crm
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Create .env file
cat > .env << EOF
WHATSAPP_TOKEN=your_meta_token_here
WHATSAPP_VERIFY_TOKEN=my_secret_verify_123
WHATSAPP_PHONE_ID=your_phone_number_id
OPENAI_API_KEY=sk-...
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/wcrm
DEBUG=true
EOF

# 3. Start PostgreSQL
docker run -d -p 5432:5432 \
  -e POSTGRES_PASSWORD=pass \
  -e POSTGRES_DB=wcrm \
  postgres:15

# 4. Run migrations
alembic upgrade head

# 5. Start the server
uvicorn app.main:app --reload --port 8000

# 6. In a new terminal — start ngrok
ngrok http 8000
```

### Test the Webhook

```bash
# Verify webhook (replace with your ngrok URL)
curl "https://abc123.ngrok-free.app/webhook/?hub.mode=subscribe&hub.verify_token=my_secret_verify_123&hub.challenge=1234"
# Expected: 1234

# Simulate an incoming WhatsApp message
curl -X POST https://abc123.ngrok-free.app/webhook/ \
  -H "Content-Type: application/json" \
  -d '{
    "object": "whatsapp_business_account",
    "entry": [{
      "changes": [{
        "value": {
          "messages": [{
            "from": "919876543210",
            "text": {"body": "Bhaiya jacket ka price kya hai?"},
            "type": "text",
            "id": "test_msg_001"
          }]
        }
      }]
    }]
  }'
```

### Run Tests

```bash
pytest tests/ -v
```

---

## Deployment (Railway)

```bash
# 1. Install Railway CLI
npm install -g @railway/cli

# 2. Login and create project
railway login
railway init

# 3. Add PostgreSQL
railway add --plugin postgresql

# 4. Set environment variables
railway variables set WHATSAPP_TOKEN=your_token_here
railway variables set WHATSAPP_VERIFY_TOKEN=my_secret_123
railway variables set WHATSAPP_PHONE_ID=your_phone_id
railway variables set OPENAI_API_KEY=sk-...
railway variables set SECRET_KEY=super_secret_production_key
railway variables set DEBUG=false
railway variables set FOLLOWUP_HOURS=24

# 5. Deploy
railway up

# 6. Run DB migrations
railway run alembic upgrade head

# 7. Update Meta Webhook URL
# Go to: developers.facebook.com → Your App → WhatsApp → Configuration
# Callback URL: https://your-app.railway.app/webhook/
# Verify Token: my_secret_123
```

---

## Pricing

| Plan | Price | Includes |
|------|-------|---------|
| **Starter** | ₹999/month | Auto-reply, 500 AI messages/month, basic CRM, 24hr follow-up |
| **Growth** ⭐ | ₹1,999/month | Everything + 2,000 msgs, Sales Agent, iOS dashboard, lead scoring, 12hr follow-up |
| **Business** | ₹3,499/month | Everything + unlimited messages, multi-staff, custom AI persona, priority support |

**Setup fee:** ₹2,000 one-time (basic) · ₹5,000 premium onboarding  
**Annual prepay:** 2 months free (17% off)

### Unit Economics (Growth Plan)

| Cost Item | Monthly |
|-----------|---------|
| OpenAI (2,000 msgs × ~300 tokens) | ~₹300–₹500 |
| Railway hosting (shared) | ~₹100–₹200 |
| Supabase DB (free tier) | ₹0 |
| WhatsApp API (1,000 free/month) | ₹0–₹100 |
| **Total COGS** | **~₹500–₹800** |
| **Margin at ₹1,999** | **~60–75%** |

---

## Scaling Roadmap

| Phase | Timeline | Target |
|-------|----------|--------|
| Prove It Works | Month 1–2 | 3 clients · ₹6K MRR |
| Grow Local | Month 3–4 | 15 clients · ₹30K MRR |
| Regional Expansion | Month 5–8 | 50 clients · ₹1L MRR |
| Systematize | Month 9–12 | 100 clients · ₹2L+ MRR |

---

## 14–16 Week Build Timeline

| Weeks | Milestone |
|-------|-----------|
| 1–2 | FastAPI setup, WhatsApp webhook, PostgreSQL schema, message send/receive |
| 3–4 | Reply Agent (GPT-4o + RAG), intent classification |
| 5–6 | Follow-up Agent, Sales Agent, APScheduler, lead scoring |
| 7–8 | iOS SwiftUI dashboard — chats, leads, stats, manual override |
| 9–10 | Integration testing, ngrok, first beta client onboarding |
| 11–14 | Railway deploy, production webhooks, scale to 3–5 paying clients |

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `WHATSAPP_TOKEN` | Meta permanent access token |
| `WHATSAPP_VERIFY_TOKEN` | Custom string for webhook verification |
| `WHATSAPP_PHONE_ID` | Phone Number ID from Meta dashboard |
| `OPENAI_API_KEY` | OpenAI API key |
| `OPENAI_MODEL` | Model name (default: `gpt-4o`) |
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host/db` |
| `SECRET_KEY` | JWT signing secret |
| `DEBUG` | `true` / `false` |
| `FOLLOWUP_HOURS` | Hours before follow-up fires (default: `24`) |
| `CHROMA_PATH` | ChromaDB persistence path (default: `./chroma_db`) |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/webhook/` | Meta webhook verification |
| `POST` | `/webhook/` | Incoming WhatsApp messages |
| `GET` | `/api/v1/stats` | Dashboard stats |
| `GET` | `/api/v1/customers` | List customers |
| `GET` | `/api/v1/customers/{id}/messages` | Chat history |
| `GET` | `/api/v1/leads` | Lead list with status |
| `POST` | `/api/v1/manual-reply` | Send a manual reply |
| `POST` | `/api/v1/pause-ai/{customer_id}` | Pause AI for a customer |
| `GET` | `/` | Health check |

---

## Security Notes

- Never commit `.env` to version control
- Rotate `SECRET_KEY` and `WHATSAPP_VERIFY_TOKEN` before production
- Tighten `CORSMiddleware` `allow_origins` to your iOS app domain in production
- Webhook payloads should be signature-verified using the Meta `X-Hub-Signature-256` header

---

## License

MIT
