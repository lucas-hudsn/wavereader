# ROADMAP — wavereader

**Goal:** Agentic surf forecaster for Australian breaks. Demo video by **Mon Sep 7, 2026** for NVIDIA GTC Golden Ticket contest (#NVIDIAGTC).

**Stack:** Python 3.12, uv, FastAPI, smolagents CodeAgent, Gradio, daggr, Open-Meteo Marine, HF Inference + NVIDIA NIM.

---

## ✅ Done (through Thu Sep 3)

- [x] Repo restructure per `AGENTS.md`; Python 3.12; deps added; `langchain-community` dropped
- [x] NVIDIA NIM API key + HF token verified
- [x] Open-Meteo Marine spike: Snapper Rocks hourly fields look sane
- [x] `data/break_details.json` validation pass (coords, ranges, spot-check 10)
- [x] `spots.py`: search by name/city/region/skill
- [x] `forecasts.py`: Open-Meteo Marine + wind, hourly 7-day, disk cache
- [x] `scoring.py`: deterministic 0–10 score/hour, component breakdown, unit tests
- [x] Scoring sanity checks: Bells (SW swell + NW wind), Kirra (long-period E)
- [x] `agent.py`: smolagents CodeAgent, streaming, trace capture, HF⇄NIM switch
- [x] `tools.py`: 5 tools wired (get_forecast, score_week, find_spots, get_spot_knowledge, rank_spots_this_week)
- [x] System prompt: numbers from tools, model explains
- [x] End-to-end flows: near-me weekly ranking with skill filter, best-hours-today, spot Q&A
- [ ] User profile (skill, home region) carried through conversation (skill filter works via chat; no persistent profile yet)
- [ ] `evals/golden_questions.json` written; spot-checked manually (ranking+skill, best-hours, spot Q&A) — automated runner still TODO

---

### User Data & Personalization

- [ ] **User profile model** — `User` class with:
  - `skill_level`: beginner / intermediate / advanced / pro → feeds `scoring.py`
  - `home_region`: state/region for default "near me"
  - `preferences`:
    - `wave_direction`: left / right / both
    - `state`: filter by Australian state
    - `location`: lat/lon + radius for "near me"
    - `other_preferences`: tags (reef, beach, point, crowd_tolerance, etc.)
- [ ] **Skill level → scoring engine**
  - Adjust ideal swell size per skill (beginner: 0.5–1.5m, pro: 2–4m+)
  - Weight wind/period components differently per skill
  - Return skill-adjusted score in `/score`
- [ ] **Preferences → pre-filter breaks** (before scoring)
  - Filter by `wave_direction` match
  - Filter by `state` match
  - Filter by `location` radius (haversine)
  - Filter by `other_preferences` tags
  - Score only filtered subset
- [ ] **Custom local break (max 1/user)**
  - Fields: name, lat, lon, region, optimal_swell_direction, optimal_swell_size_range, optimal_wind_direction, skill_level_suitability, notes
  - Validate coords against Open-Meteo grid
  - Merge into user's break list for ranking; persist in profile
  - UI: Gradio form (modal/sidebar) with "Add my local break"

### Infrastructure & Polish

- [ ] Persist user profiles (SQLite or HF dataset) — survive restarts
- [ ] Auth (email/token or HF OAuth) for multi-user Space
- [ ] Migrate `data/break_details.json` → proper DB for concurrent writes
- [ ] Add tide data source (stretch: WillyWeather integration)

### API + UI

- [x] `api.py`: FastAPI endpoints (`/spots`, `/forecast`, `/score`, `/ask`)
- [x] `app.py`: Gradio UI — Australia map home page, chat, interactive seaborn-styled charts, agent trace panel, HF/NIM toggle
- [ ] 📹 Capture: polished Demo Q1 + OpenAPI docs screen

### daggr + Deploy

- [x] `daggr_pipeline.py`: "Morning Surf Report" DAG (find_spots → fetch forecasts → score → rank → InferenceNode narrates); embeds in the UI via iframe
- [ ] Deploy to HF Space (secrets: `HF_TOKEN`, `NVIDIA_API_KEY`); test public URL end-to-end
- [ ] Publish `data/break_details.json` as HF dataset; README architecture diagram; license
- [ ] 📹 Capture: daggr canvas walkthrough; Space on phone
- [ ] Stretch: live surf-cam snapshots tool for famous breaks

### Rehearse + Record

- [ ] Run evals against live Space; fix breaks
- [ ] Full rehearsal → record main video
- [ ] Draft LinkedIn post

### Launch

- [ ] Edit + publish video; post to LinkedIn (contest + Berlin announcement); submit entry
- [ ] Sep 8–10 buffer for retakes / judge replies

---

## Video Script (~2 min)

1. **Hook (0:00–0:10)** — "I moved to Berlin — 16,000 km from surf. Built an agent to find waves back home."
2. **Problem (0:10–0:25)** — Local knowledge: which winds suit which break. Show `break_details.json` + raw forecast.
3. **Demo Q1 (0:25–0:55)** — "Where should I surf near Byron Bay this weekend? Intermediate longboarder." → ranked cards + trace panel.
4. **Demo Q2 (0:55–1:15)** — "What time should I surf Snapper Rocks tomorrow?" → interactive hourly chart + best-window reasoning.
5. **Reasoning canvas (1:15–1:35)** — daggr Morning Surf Report: click through node outputs live.
6. **Under the hood (1:35–1:50)** — FastAPI OpenAPI docs; HF ↔ NIM toggle; break knowledge base as HF dataset.
7. **CTA (1:50–2:10)** — Open models (Qwen via HF + NVIDIA NIM). Free GTC Berlin ticket 🤞 #NVIDIAGTC. New in Berlin — DMs open for ML work.

---

## Risks & Fallbacks

| Risk                                             | Mitigation                                                                                           |
| ------------------------------------------------ | ---------------------------------------------------------------------------------------------------- |
| Daggr beta misbehaves (no conditional branching) | Agent trace panel = reasoning demo; swap canvas shot for trace walkthrough                           |
| Open-Meteo grid points sit offshore              | Fetch slightly seaward coords; validate against known break behavior                                 |
| Demo-day API flakiness / rate limits             | Disk-cached forecasts; daily milestone clips = no rebuild needed for retakes                         |
| Tool-loop unreliability                          | Small tool set, strict structured outputs, `golden_questions.json` gates recording                   |
| Model availability on either router              | Provider-agnostic client; same model on HF + NIM; fallback must support tool calling + `json_schema` |
