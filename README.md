# 🏟️ Event Radar

Automated event aggregation tool for sports venues and concert halls.
Uses Claude AI (with live web search) to pull all upcoming events, exports
a polished Excel file, and optionally uploads directly to SharePoint.

---

## What it does

1. Queries Claude AI with web search for every venue / team on your list
2. Collects: venue, address, event name, type, date, local time, GMT+2, duration, capacity/tickets
3. Displays results in a filterable, sortable dashboard
4. Exports a formatted Excel file ready to upload to SharePoint
5. **Or** auto-uploads to SharePoint via Microsoft Graph API

---

## Quick start (local)

```bash
git clone <your-repo>
cd event-radar

# Install dependencies
pip install -r requirements.txt

# Copy and fill in env vars
cp .env.example .env
# → edit .env, add your ANTHROPIC_API_KEY

# Run
python app.py
# Open http://localhost:5000
```

---

## Deploy to Render.com (free hosting)

1. Push this folder to a **GitHub repo**
2. Go to [render.com](https://render.com) → New → Web Service
3. Connect your GitHub repo
4. Render auto-detects `render.yaml` — click **Deploy**
5. In the Render dashboard → Environment → add:
   ```
   ANTHROPIC_API_KEY = sk-ant-api03-...
   ```
6. Done — your app is live at `https://event-radar-xxxx.onrender.com`

> **Note:** Render free tier spins down after 15 min of inactivity.
> First request after spin-down takes ~30s to wake up. Upgrade to paid ($7/mo)
> to keep it always-on.

---

## SharePoint auto-upload (optional)

### Step 1 — Register Azure AD App

1. Go to [portal.azure.com](https://portal.azure.com) → **Azure Active Directory**
2. **App registrations** → **New registration**
   - Name: `Event Radar`
   - Supported account types: *Single tenant*
   - Click **Register**
3. Copy the **Application (client) ID** → `SP_CLIENT_ID`
4. Copy the **Directory (tenant) ID** → `SP_TENANT_ID`

### Step 2 — Add API permissions

1. **API permissions** → **Add a permission** → **Microsoft Graph**
2. **Application permissions** → search `Sites.ReadWrite.All` → Add
3. Click **Grant admin consent for [your org]** ✓

### Step 3 — Create client secret

1. **Certificates & secrets** → **New client secret**
2. Set expiry (e.g. 24 months) → **Add**
3. Copy the **Value** (not the ID!) → `SP_CLIENT_SECRET`

### Step 4 — Set env vars

```env
SP_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
SP_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
SP_CLIENT_SECRET=your_secret_value
SP_SITE_URL=https://yourcompany.sharepoint.com/sites/YourSite
SP_FOLDER_PATH=Shared Documents/Events
```

After this, the **Upload to SharePoint** button in the UI becomes active.

---

## Workflow for your team

```
Every Monday:
  1. Open the Event Radar URL
  2. Click ⚡ FETCH EVENTS  (takes ~60-90 seconds)
  3. Review the dashboard
  4. Click 📊 Download Excel  OR  ☁️ Upload to SharePoint
  5. File is now in SharePoint → Shared Documents/Events/events_YYYYMMDD_HHMM.xlsx
```

---

## File structure

```
event-radar/
├── app.py                  ← Flask server, API routes, SSE streaming
├── event_fetcher.py        ← Claude API + web_search, batches venues, parses JSON
├── excel_exporter.py       ← Generates formatted .xlsx with summary sheet
├── sharepoint_uploader.py  ← Microsoft Graph API upload
├── templates/
│   └── index.html          ← Full single-page UI (dark theme, filterable table)
├── requirements.txt
├── render.yaml             ← One-click Render.com deploy
└── .env.example
```

---

## Customising venues

Edit the `DEFAULT_VENUES` list at the top of `app.py`, or simply edit the
textarea in the UI before each run — it does not need to match the defaults.

---

## Changing the AI model

In `event_fetcher.py`, line:
```python
MODEL = "claude-opus-4-5"
```
Options:
- `claude-opus-4-5` — most powerful, best web research (recommended)
- `claude-sonnet-4-6` — faster, cheaper, still very good
- `claude-haiku-4-5-20251001` — fastest / cheapest

---

## API cost estimate

Each run fetches ~18 venues in batches of 4 = **5 API calls**.
With web search + ~8k output tokens per call:
- **Opus**: ~$0.15–0.30 per full run
- **Sonnet**: ~$0.05–0.10 per full run

Monthly cost for weekly runs: **under $5** on Sonnet.
