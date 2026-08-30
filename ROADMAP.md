# ROADMAP — GTC Golden Ticket sprint

One-week sprint: **Sun Aug 30 → video published Mon Sep 7, 2026.**
Contest submissions close **Sep 10** (3-day buffer). Deliverables: public HF
Space, polished repo, ~2-minute video posted on LinkedIn with #NVIDIAGTC
tagging Merve Noyan — doubling as an announcement of the Berlin move and
openness to ML work/research in Berlin.

Decisions locked: 8-day build to Mon Sep 7 · HF Inference + NVIDIA NIM behind
one client · surf cams are stretch-only · demo lives on a HF Space ·
FastAPI + hand-rolled agent loop + Gradio + daggr (no LangChain, no htmx).

---

## Day-by-day

### Sun Aug 30 (tonight, ~2h)
- Restructure repo to the layout in `AGENTS.md`; pin Python 3.12; add deps
  (`gradio`, `daggr`, `openai`, `httpx`, `pydantic`, `pytest`); drop
  `langchain-community`.
- Grab a free NVIDIA NIM API key (build.nvidia.com); verify HF token works.
- 30-min spike: hit Open-Meteo Marine API for Snapper Rocks, confirm hourly
  wave fields look sane.

### Mon Aug 31 — Data layer
- Validation pass over `data/break_details.json`: coords plausible for region,
  ranges sane; spot-check ~10 breaks against local knowledge.
- `spots.py` (search by name/city/region/skill) + `forecasts.py`
  (Open-Meteo Marine + wind, hourly, 7-day, disk cache).
- 📹 **Capture:** terminal printing a 7-day forecast table for 3 spots.

### Tue Sep 1 — Scoring engine
- `scoring.py`: deterministic 0–10 score per hour with per-component
  breakdown (swell size vs ideal range, swell direction match, wind speed +
  offshore alignment, wave period). Unit tests.
- Sanity-check rankings: Bells Beach should score on SW swell + light NW
  wind; Kirra on long-period E.
- Outputs: "best hours today" and day-by-week profile per spot.
- 📹 **Capture:** score table / heatmap clip.

### Wed Sep 2 — Agent core
- `agent.py`: hand-rolled tool loop, streaming, trace capture; HF⇄NIM switch
  via env vars. `tools.py`: 5 tools wired (get_forecast, score_week,
  find_spots, get_spot_knowledge, rank_spots_this_week).
- System prompt contract: numbers come from tools; the model explains.
- 📹 **Capture:** the first complete agent answer, raw and candid — great b-roll.

### Thu Sep 3 — Flows + evals
- End-to-end flows: near-me weekly ranking with skill filter; today-at-X time
  recommendation; spot Q&A using the knowledge tool.
- User profile (skill level, home region) carried through conversation.
- Write + run `evals/golden_questions.json`; fix prompt/tool gaps.

### Fri Sep 4 — API + UI
- `api.py`: FastAPI endpoints (`/spots` `/forecast` `/score` `/ask`).
- `app.py`: Gradio UI — **Australia map home page (select your break)**,
  chat, **interactive seaborn-styled forecast charts** whenever the agent
  surfaces wind/sea data, agent trace panel, HF/NIM model toggle.
- 📹 **Capture:** polished Demo Q1 + OpenAPI docs screen.

### Sat Sep 5 — daggr + ship
- `daggr_pipeline.py`: fixed "Morning Surf Report" DAG (geocode → find_spots
  → score_week → top-3 rank → InferenceNode narrates). Verify node outputs
  look good on the canvas.
- Deploy to HF Space (secrets: `HF_TOKEN`, `NVIDIA_API_KEY`); test the public
  URL end-to-end.
- Publish `data/break_details.json` as a HF dataset; README architecture
  diagram; license.
- Stretch (only if everything else lands): live surf-cam snapshots → "is it
  clean/right now" tool for a handful of famous breaks.
- 📹 **Capture:** daggr canvas walkthrough; Space opened on a phone.

### Sun Sep 6 — Rehearse + record
- Run evals against the live Space; fix anything that breaks.
- Full rehearsal, then record the main video (script below).
- Draft the LinkedIn post.

### Mon Sep 7 — Launch
- Edit and publish the video; post to LinkedIn (contest entry + Berlin
  announcement); submit the contest entry.
- Sep 8–10: buffer for retakes / judge replies.

---

## Video script (~2 min, landscape screen captures + webcam bubble)

Record each shot's milestone clip during the week as insurance; the final
video is a re-recorded clean pass through the live Space.

1. **Hook (0:00–0:10).** "I moved to Berlin last week — 16,000 km from the
   nearest surf break. So I built an agent that finds waves back home."
   *(B-roll: coastline → app loading.)*
2. **Problem (0:10–0:25).** "Surf forecasting runs on local knowledge — which
   winds suit which break, what size it can handle." *(Show
   `break_details.json` snippet + raw forecast table.)*
3. **Demo Q1 (0:25–0:55).** In the app: *"Where should I surf near Byron Bay
   this weekend? Intermediate longboarder."* → ranked spot cards with scores
   and the why. *(Show the agent trace panel streaming tool calls.)*
4. **Demo Q2 (0:55–1:15).** *"What time should I surf Snapper Rocks
   tomorrow?"* → interactive hourly chart, best-window recommendation with
   wind/swell reasoning.
5. **Reasoning canvas (1:15–1:35).** daggr Morning Surf Report — click
   through node outputs live: rank → forecast → narrated report.
6. **Under the hood (1:35–1:50).** FastAPI OpenAPI docs flash; flip the
   HF ↔ NIM toggle; show the break knowledge base as a HF dataset.
7. **CTA (1:50–2:10).** "Everything runs on open models — Qwen via Hugging
   Face and NVIDIA NIM. Free GTC Berlin ticket, please 🤞 #NVIDIAGTC — and
   since I just moved to Berlin: if you're working on LLM agents or applied
   ML, I'd love to talk. DMs open." *(Screen: Space link + repo link.)*

## LinkedIn post skeleton

1. Hook: the move to Berlin.
2. The problem: surf forecasting's inherent knowledge.
3. Two sentences: what the app does + the two flagship questions.
4. Video + Space link.
5. Open-credentials: Qwen via HF Inference + NVIDIA NIM, open dataset on HF,
   daggr canvas.
6. Thanks + tags: judges, #NVIDIAGTC.
7. Berlin close: "New in Berlin, keen on ML research/engineering — say hi."

*(Nice detail: Hugging Face is headquartered in Berlin — the judge will get it.)*

---

## Risks & fallbacks

| Risk | Mitigation |
| --- | --- |
| Daggr beta misbehaves (no conditional branching; pin the version) | The agent trace panel is the reasoning demo; swap video shot 5 for a trace walkthrough. |
| Open-Meteo coastal grid points sit offshore | Fetch slightly seaward coords; validate Tue against known break behavior. |
| Demo-day API flakiness / rate limits | Disk-cached forecasts; daily milestone clips mean a retake never rebuilds the week. |
| Tool-loop unreliability | Small tool set, strict structured outputs, `golden_questions.json` gates recording. |
| Model availability on either router | Client is provider-agnostic; same model on HF and NIM; fallback model must support tool calling + `json_schema` (see `data/GENERATION.md`). |
