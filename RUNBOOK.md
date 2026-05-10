# AgenticCRM — Operations Runbook

## Key IDs & URLs

| Item | Value |
|------|-------|
| Railway URL | `https://agenticcrm-api-production.up.railway.app` |
| Railway Project ID | `98143bfa-2303-4ed3-9ca7-f794f396557a` |
| Railway Service ID | `769fdf8e-8fa7-4c9b-b8ba-96bdd3319282` |
| WhatsApp Phone ID | `1083207094886888` |
| WhatsApp WABA ID | `1336121438577268` |
| Business ID (Railway DB) | `b8e1f709-ec72-417f-bbdf-28461476051c` |
| Verify Token | `my_secret_verify_123` |
| Webhook URL | `https://agenticcrm-api-production.up.railway.app/api/v1/webhook/` |

---

## Daily: Refresh WhatsApp Token (expires every 24h)

Meta test tokens expire daily. When you see `401` errors in logs:

1. Go to [Meta Developer Console](https://developers.facebook.com) → WhatsApp → API Setup
2. Copy the temporary access token
3. Run:
```bash
export PATH="$HOME/.railway/bin:$PATH"
cd /Users/anand.pandey2/Documents/Personal/AgenticCRM/AgenticCRM
railway variables set WHATSAPP_TOKEN=<paste_new_token>
```
4. Railway auto-redeploys (~2 min). After redeploy, re-subscribe the WABA (see below).

---

## After Every Redeploy: Re-subscribe WABA

Every time Railway redeploys, run this to keep message events flowing:

```bash
curl -s -X POST "https://graph.facebook.com/v19.0/1336121438577268/subscribed_apps" \
  -H "Authorization: Bearer $WHATSAPP_TOKEN"
```

Replace `$WHATSAPP_TOKEN` with the current token value. Expected response: `{"success":true}`

Verify subscription:
```bash
curl -s "https://graph.facebook.com/v19.0/1336121438577268/subscribed_apps?access_token=<TOKEN>"
```
Should show `AgenticCRM` in the data array.

---

## After Every Redeploy: Re-verify Webhook in Meta Console

1. Meta Developer Console → WhatsApp → Configuration
2. Webhook section → click **Edit**
3. Set:
   - Callback URL: `https://agenticcrm-api-production.up.railway.app/api/v1/webhook/`
   - Verify token: `my_secret_verify_123`
4. Click **Verify and Save**
5. Under Webhook fields → **messages** → click **Subscribe**

Confirm in logs:
```bash
export PATH="$HOME/.railway/bin:$PATH"
railway logs --tail 10 2>&1 | grep "GET /api/v1/webhook"
```
Should show `200 OK`.

---

## Upload / Refresh Product Catalog

To add or update products for RAG search:

```bash
curl -s -X POST "https://agenticcrm-api-production.up.railway.app/api/v1/business/catalog" \
  -H "Content-Type: application/json" \
  -d '{
    "business_id": "b8e1f709-ec72-417f-bbdf-28461476051c",
    "items": [
      {"name": "Blue Denim Jacket", "price": 850, "description": "Stylish blue denim jacket sizes S/M/L/XL machine washable", "category": "Jackets"},
      {"name": "Red Cotton Kurti", "price": 450, "description": "Red cotton kurti ladies sizes XS-XXL festive wear", "category": "Kurti"},
      {"name": "Black Formal Trouser", "price": 650, "description": "Black slim-fit formal trouser for men sizes 28-38", "category": "Trousers"},
      {"name": "White Linen Shirt", "price": 550, "description": "White breathable linen shirt summer full sleeves M/L/XL", "category": "Shirts"},
      {"name": "Printed Saree", "price": 1200, "description": "Floral printed synthetic saree 5.5 metres with blouse piece", "category": "Sarees"}
    ]
  }'
```

Expected response: `{"status":"ok","ingested":5}`

---

## Monitor Live Logs

```bash
export PATH="$HOME/.railway/bin:$PATH"
cd /Users/anand.pandey2/Documents/Personal/AgenticCRM/AgenticCRM

# All meaningful logs
railway logs --tail 50 2>&1 | grep -E "POST /api/v1/webhook|Intent|reply_len|ERROR:app|graph.facebook|401"

# Full raw logs
railway logs --tail 100
```

Healthy message flow looks like:
```
POST /api/v1/webhook/ → 200 OK
Intent: price_inquiry
[ReplyAgent] reply_len=XX
POST https://graph.facebook.com/.../messages → 200 OK
Follow-up scheduled for customer ...
```

---

## Test Pipeline Without WhatsApp

Simulate a webhook message hit:

```bash
curl -s -X POST "https://agenticcrm-api-production.up.railway.app/api/v1/webhook/" \
  -H "Content-Type: application/json" \
  -d '{
    "object": "whatsapp_business_account",
    "entry": [{"id": "1336121438577268", "changes": [{"value": {
      "messaging_product": "whatsapp",
      "metadata": {"display_phone_number": "15556394146", "phone_number_id": "1083207094886888"},
      "contacts": [{"profile": {"name": "Test User"}, "wa_id": "918618237552"}],
      "messages": [{"from": "918618237552", "id": "wamid.test001", "timestamp": "1778408126", "text": {"body": "Jacket ka price kya hai?"}, "type": "text"}]
    }, "field": "messages"}]}]
  }'
```

Expected: `{"status":"ok"}` — then check logs for pipeline output.

---

## Register a New Business

```bash
curl -s -X POST "https://agenticcrm-api-production.up.railway.app/api/v1/business/register" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Shop",
    "phone_number": "+91XXXXXXXXXX",
    "whatsapp_phone_id": "1083207094886888",
    "business_type": "clothing",
    "owner_email": "owner@myshop.com"
  }'
```

Save the `id` from the response — use it for catalog uploads.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| No POST in Railway logs after WhatsApp message | WABA not subscribed | Run `subscribed_apps` POST |
| `401` on graph.facebook.com | Token expired | Refresh token + `railway variables set` |
| `400` on mark_as_read | Fake/test message ID | Harmless — ignore in tests |
| `500` on `/business/register` | Duplicate phone | Now fixed (idempotent upsert) |
| No RAG results | Catalog on wrong business ID | Re-upload with correct `business_id` |
| Logs stuck at old deployment | Stale deployment ID | Run `railway logs` without `--deployment` flag |

---

## Security Reminders

- **Rotate NVIDIA API key** at [build.nvidia.com](https://build.nvidia.com) — it was exposed in chat
- **Use a permanent System User token** from Meta Business Manager for production (eliminates daily token refresh)
- Update `.env` `SECRET_KEY` from `change-me-in-production` before going live
