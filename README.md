# Prisma (WIP)

Chrome extension for capturing, organizing, and analyzing web content. The current release focuses on the **browser extension**. The **analytics pipeline** and **server** are under active development.

> ⚠️ Work in Progress: You can install and use the extension today. Analytics dashboards and the backend APIs are being built and will ship in upcoming versions.

---

## Quick Start

### Option A — Install from Chrome Web Store

1. Open the Chrome Web Store listing: **[Link – Prisma Extension]** *(placeholder; replace with the real URL)*
2. Click **Add to Chrome**.
3. Pin the extension (optional): click the puzzle icon → pin **Prisma**.

### Option B — Developer Install (Unpacked)

1. Clone this repo:

   ```bash
   git clone https://github.com/your-org/prisma-extension.git
   cd prisma-extension
   ```
2. Install dependencies & build:

   ```bash
   npm install
   npm run build
   ```
3. Load in Chrome:

   * Visit `chrome://extensions`
   * Toggle **Developer mode** (top right)
   * Click **Load unpacked** and select the `dist/` (or `build/`) folder

---

## What You Can Do Today (v0.x)

* **Capture content** from the current tab (text selection, page metadata, and URL)
* **Save via context menu** (right-click → "Save to Prisma")
* **Quick notes** in the popup (autosaved locally via `chrome.storage`)
* **Export** captured items to JSON for offline analysis

### Coming Soon (Roadmap)

* **Analytics**: per-domain/page insights (counts, tags, topics, sentiment)
* **Server**: authenticated sync, Teams/Projects, and search
* **Dashboards**: time-series views, top entities, engagement metrics
* **Share**: generate read-only links for collections

---

## Analytics & Server (WIP)

**Planned stack (subject to change):**

* **API**: Node.js (Express/Fastify) or Python (FastAPI) with JWT auth
* **DB**: Postgres (primary), Redis (caching/queues)
* **Workers**: queue-based ETL; optional LLM classification pipeline
* **Telemetry**: event ingestion endpoint (`/v1/events`) with batch writes

**Key endpoints (draft):**

* `POST /v1/items` — ingest captured items (title/url/snippet/tags)
* `GET /v1/items?query=...` — search & filter
* `POST /v1/events` — analytics events (capture, tag, view)
* `GET /v1/metrics` — rollups for dashboards

**Sync strategy:** optimistic local writes → background sync → conflict resolution (last-write-wins + mergeable fields like tags/notes)

---

## Configuration

Create a `.env` (or `.env.local`) at the repo root for local builds:

```
# Extension build
VITE_APP_NAME=Prisma
VITE_ENV=development

# Backend (optional; safe defaults for now)
VITE_API_BASE_URL=http://localhost:8080
VITE_TELEMETRY_WRITE_KEY=
```

> The extension works locally without a server. When the server is available, set `VITE_API_BASE_URL`.

---

## Development

### Prerequisites

* Node.js 18+
* npm or pnpm
* Google Chrome 120+

### Common Scripts

```bash
# Install deps
npm install

# Dev build with watch
npm run dev

# Production build
npm run build

# Lint & type-check (if configured)
npm run lint
npm run typecheck
```

### Hot Reload Tips

* Some MV3 changes require a full **Service Worker reload** (chrome://extensions → Prisma → **Reload**)
* Content script changes often require a page refresh

---

## Usage

1. Open a page you want to capture
2. Click the **Prisma** toolbar icon → **Capture**
3. (Optional) Right-click selected text → **Save to Prisma**
4. Open the popup to view items, add tags/notes, and export JSON

---

## Troubleshooting

* **Extension won’t load**: Ensure you selected the correct `dist/` folder. Run `npm run build` again.
* **Context menu missing**: Toggle the extension off/on in `chrome://extensions`.
* **No data appears**: Check `chrome://extensions` → Prisma → **Service Worker** logs.
* **CSP/Permissions**: If capture fails on specific sites, the page may block injection; try the activeTab capture from the popup.

---

## Security & Privacy

* Local-first: data is stored in your browser via `chrome.storage.local`.
* No external network calls occur unless you configure `VITE_API_BASE_URL`.
* When analytics ship, a clear consent toggle will be provided in **Options**.
