# WaveReader UI & Demo Guide

Comprehensive visual and interaction guide for the WaveReader Gradio interface (`wavereader/app.py`).

Launch command:
```bash
uv run python -m wavereader.app
```
Access in browser: `http://localhost:7860`

---

## 1. Interface Overview

```
┌───────────────────────────────────────────────────────────────────────────┐
│ 🏄 WaveReader  ·  Agentic Surf Forecaster  ·  Model: Qwen 80B / Llama 90B  │
├─────────────┬─────────────┬─────────────────┬─────────────────┬───────────┤
│ 🗺️ Explore   │ 🤖 Agent    │ 📊 Charts       │ 🏆 Rankings     │ 📋 Report │
└─────────────┴─────────────┴─────────────────┴─────────────────┴───────────┘
```

The app is divided into five dedicated views, optimized for demo clarity:

1. **🗺️ Explore (Home):** Interactive map of Australia displaying all 100 surf breaks color-coded by surfer skill level.
2. **🤖 Surf Agent:** Natural-language chat interface featuring live code-stream visualization, provider toggle, trace inspection, and dynamic forecast charts.
3. **📊 Forecast Charts:** Standalone deep dive with hourly wave height, period, wind speed/direction, and deterministic score breakdowns.
4. **🏆 Weekly Rankings:** 7-day regional leaderboards with skill filtering.
5. **📋 Morning Surf Report:** Embedded daggr pipeline canvas visualising deterministic multi-step batch execution.

---

## 2. Tab Walkthroughs

### 2.1 🗺️ Explore (Australia Map)

- **Interactive Map:** Built with Plotly `Scattergeo`.
  - Color-coded pins: Green (Beginner), Cyan (Intermediate), Purple (Advanced), Red (Expert).
  - Hover tooltip displays spot name, state, ideal swell window, and offshore wind tolerances.
  - Interactive selection: clicking a spot on the map automatically selects it in the break search dropdown and displays its full profile card.
- **Skill Filter:** Dropdown above the map filters pins live across all states.
- **Spot Profile Card:** Markdown card rendering key metadata:
  - Latitude / Longitude coordinates
  - Ideal swell size range and directions
  - Ideal wind speed limit and directions
  - Qualitative tide recommendations from local knowledge
  - Hazards and crowd density ratings
- **Quick-Jump Button:** "Show forecast charts for this spot" immediately routes to detailed 7-day graphs.

---

### 2.2 🤖 Surf Agent (Chat & Reasoning)

- **Provider Hosting Radio:**
  - `Hugging Face 🤗 (Qwen 80B)`: `Qwen/Qwen3-Next-80B-A3B-Instruct` via the Hugging Face Router.
  - `NVIDIA NIM ⚡ (Llama 3.2 90B)`: `meta/llama-3.2-90b-vision-instruct` via NVIDIA NIM.
- **Streaming Code Reasoning:**
  - Smolagents `CodeAgent` execution stream displays live code synthesis in a syntax-highlighted python block (`*🧠 thinking…*`) and tool execution indicators (`*🔧 calling get_forecast…*`).
- **Inspectable Trace Panel (`#wr-trace`):**
  - Collapsible event log showing exact tool calls, parameters, raw tool responses, and timestamps.
- **Dynamic Charts:**
  - Whenever the agent analyzes spots in its tool loop, interactive Plotly charts appear immediately beneath the chat window:
    1. **Hourly Surf Score (0–10):** Bold composite score curve with dotted component curves (Swell Size, Direction, Wind, Period).
    2. **Wave & Wind Forecast:** Filled area chart of wave height (m), with secondary axis for wave period (s) and wind speed (km/h) with compass direction annotations.

---

### 2.3 📊 Forecast Charts

- Deep-dive analysis for any selected break:
  - **Top Chart:** 7-day hourly wave height, period, wind speed, and direction.
  - **Bottom Chart:** 7-day hourly deterministic surf score (0 to 10) with individual breakdown of swell size, direction, wind alignment, and period components.

---

### 2.4 🏆 Weekly Rankings

- Pick any Australian region (`NSW`, `QLD`, `VIC`, `WA`, `SA`, `TAS`) and skill level (`beginner`, `intermediate`, `advanced`, `expert`).
- Click **"Rank this week"**:
  - Horizontal bar chart sorting breaks by their single best hourly score across the 7-day forecast.
  - Interactive table displaying spot name, region, best score, and exact time stamp of optimal surf.

---

### 2.5 📋 Morning Surf Report (daggr Pipeline)

- Embeds the standalone daggr canvas running on port 7861 (`wavereader.daggr_pipeline`).
- Visualizes the deterministic pipeline DAG:
  `User Input` ──▶ `Find Spots` ──▶ `Fetch Forecasts` ──▶ `Score Forecasts` ──▶ `Rank Spots` ──▶ `Narrate Report`
- Allows judges to inspect individual node outputs and intermediate states.

---

## 3. Demo Video Recording Checklist (Monday, Sep 7)

For the NVIDIA GTC Golden Ticket submission:
1. **Resolution:** Set browser viewport to 1080p (1920x1080) at 100% zoom.
2. **Tokens Ready:** Ensure both `HF_TOKEN` and `NVIDIA_API_KEY` are exported.
3. **Background Services:** Verify daggr is running (`http://127.0.0.1:7861`).
4. **Follow 7-Beat Script:**
   - Beat 1 (0:00–0:10): Hook & problem (Berlin surfer looking for waves back home in Australia).
   - Beat 2 (0:10–0:25): Explore tab & local knowledge (`break_details.json`).
   - Beat 3 (0:25–0:55): Demo Q1 ("Where should I surf near Byron Bay this weekend? Intermediate longboarder"). Point to trace panel & ranking cards.
   - Beat 4 (0:55–1:15): Demo Q2 ("What time should I surf Snapper Rocks tomorrow?"). Point to interactive hourly score chart.
   - Beat 5 (1:15–1:35): Switch to daggr Morning Surf Report canvas.
   - Beat 6 (1:35–1:50): Toggle HF ↔ NVIDIA NIM hosting & show FastAPI `/docs`.
   - Beat 7 (1:50–2:10): Call to Action (#NVIDIAGTC).
