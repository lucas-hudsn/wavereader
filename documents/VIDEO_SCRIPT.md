# wave~reader — GTC Berlin Golden Ticket entry video script

Target: **90 seconds**, screen recording + voiceover (or captions).
Record AFTER `uv run python scripts/warm_caches.py` so every spin-up on
screen is warm (charts land in <100 ms). Browser at ~1440×900, zoom ~110%.

Tag line to open on: **"wave~reader — a surf forecasting world model,
powered by NVIDIA Nemotron 3.5 Lightning on Hugging Face Inference
Providers."**

---

## Shot list

### 0:00–0:08 — cold open (hero)
- Show the landing view: `wave~reader` hero + the **engines strip**
  (🌍 world model · 📡 feeds · 🌡 climate · ⚙ scorer · 🧠 LLM · 🔌 MCP).
- VO: "wave~reader makes its machinery visible: a GEBCO world model, open
  weather feeds, a deterministic scoring engine — and one open model,
  Nemotron 3.5 Lightning, that is only ever allowed to narrate their numbers."

### 0:08–0:25 — break book
- Filter Victoria → Surf Coast, pick **Bells Beach**.
- Show the field guide + the 5-year **ERA5 climate rose** and audit chips
  ("dataset ideals agree with the observed climate").
- VO: "238 Australian breaks, each grounded against five years of ERA5
  reanalysis — the data corrects the model where they disagree."

### 0:25–0:48 — swell check: the world model works while you watch
- Clicking the break, the swell check populates in stages — read the
  status line aloud: feed timing, scorer timing, then **"🌍 world model:
  GEBCO 2020 — resolved in 1.2 s"**.
- Score bars + swell + wind strips with weekend shading; the hero
  "p75 daily consistency" list.
- Click the **Seafloor** tab: smoothed 3D bathymetry. Press **▶ swell** —
  the animated swell layer rides the reef at the forecast's dominant
  period. Slowly drag-rotate the scene.
- VO: "Every score is computed, never generated: 168 hourly 0–10 scores
  from Open-Meteo marine data. And the world model — real GEBCO
  bathymetry — renders the reef in 3D, with the forecast's own swell
  riding it."

### 0:48–1:10 — surf agent: tool calling, on the clock
- Switch to **surf agent**, click the chip *"When are the best morning
  windows at Bells Beach this week?"*.
- Let the tool cards stream: `🔧 score_week(...)` → `📦 → 84 scored hours ·
  ⚡ 312 ms`, charts appearing mid-answer, then the token meter
  (🪙 prompt/completion tokens, single turn).
- VO: "The agent is a native tool-calling loop on Nemotron 3.5 Lightning.
  Watch the clock: every tool call is milliseconds, because the numbers
  come from deterministic Python — the model only interprets. Hard budget:
  six steps, 700 tokens per turn."

### 1:10–1:25 — MCP: the app is the tool
- Cut to a terminal: `curl localhost:7860/gradio_api/mcp/schema | jq` —
  show the three tools; then call `score_week` for Bells Beach from an
  MCP client (opencode) and show the same deterministic payload.
- VO: "The app ships as an MCP server — the same three deterministic
  tools the agent uses, exposed to any client. One door, no hallucinated
  numbers anywhere."

### 1:25–1:30 — close
- Return to the 3D seafloor with the swell animating.
- VO: "Open weights, open data, deterministic core. wave~reader."
- End card: repo URL + `#NVIDIAGTC`.

---

## Recording checklist
- [ ] `uv run python scripts/warm_caches.py` (featured breaks hot)
- [ ] `uv run python app.py` running locally (MCP badge visible)
- [ ] No cold spinners on screen — every fetch warm
- [ ] ▶ swell clicked at least once before camera rolls (verify animation smooth)
- [ ] Token meter shows real numbers (agent tab costs a few cents total)
- [ ] Terminal MCP shot: schema + one call
- [ ] 90 s hard cap; captions if no voiceover
