# WaveReader: System Audit, Current State & Next Steps

**Contest Target:** NVIDIA GTC Berlin Golden Ticket contest (#NVIDIAGTC)  
**Submission Deadline:** September 10, 2026  
**Hard Video Recording Deadline:** Monday, September 7, 2026 (~3 days remaining)  
**Audit Date:** Friday, September 4, 2026  

---

## 1. Executive Summary

WaveReader has established a solid architectural foundation adhering to the core principle: **"The LLM orchestrates; deterministic code owns the numbers."** 

All 134 automated unit tests currently pass, the 100-break knowledge base is validated, the Open-Meteo marine forecast client caches reliably with coastal seaward snapping, the deterministic surf-scoring engine behaves smoothly across skill levels, and both FastAPI (`api.py`) and Gradio (`app.py`) scaffolds are operational alongside the daggr Morning Surf Report canvas.

However, an active live-system audit with real credentials and live inference endpoints uncovered **two critical runtime blockers** that were masked by offline unit test mocks:
1. **Smolagents prompt template override in `agent.py`:** Overwriting `system_prompt` completely removed the `smolagents.CodeAgent` execution instructions (code block tags `<code>...</code>` and `final_answer()` tool), causing the agent to loop 10 times in failure and consume ~27,000 tokens before hitting max steps.
2. **NVIDIA NIM model unavailability:** `Qwen/Qwen3-Next-80B-A3B-Instruct` is hardcoded as `DEFAULT_MODEL`, but that model ID does not exist on NVIDIA NIM (`https://integrate.api.nvidia.com/v1`). Because `_detect_provider()` prioritizes NIM whenever `NVIDIA_API_KEY` is present, the agent failed instantly with HTTP 404.

Both issues have been diagnosed and verified with live tests (appending `SYSTEM_PROMPT` restores 1-2 step execution, and `meta/llama-3.2-90b-vision-instruct` on NIM completes queries in ~6s).

This document details the completed components, audit findings, and a prioritized action plan to take the project from its current state to a polished, recorded demo video by Monday, Sep 7.

---

## 2. Review of What Has Been Done

### 2.1 Knowledge Base (`data/` & `wavereader/spots.py`)
- **Dataset:** 100 Australian surf breaks across NSW, QLD, VIC, WA, SA, and TAS compiled in `data/breaks.json` and enriched with structured, web-grounded attributes in `data/break_details.json`.
- **Validation:** Pydantic validation pass in `spots.py` enforcing geographic bounding boxes per state, strictly positive wind strength, valid swell ranges, and allowed skill levels.
- **Search:** Case-insensitive search by name, region, and skill level with limit caps.

### 2.2 Marine & Weather Forecast Client (`wavereader/forecasts.py`)
- **Dual API Merging:** Fetches wave parameters (`wave_height`, `wave_period`, `wave_direction`, `swell_wave_height`, `wind_wave_height`) from Open-Meteo Marine and wind parameters (`wind_speed_10m`, `wind_direction_10m`) from Open-Meteo Weather, merged on hourly timestamps.
- **Seaward Offset:** Automatic coastal snapping (~0.13° / ~14 km seaward) based on coastline orientation (east coast shifts east, west coast shifts west, south coast/Tasmania shifts south).
- **Disk Cache & Demo Survivability:** Atomic 6-hour JSON disk caching in `.cache/forecasts/`. Network failures fall back to stale cache entries to guarantee demo stability.

### 2.3 Deterministic Surf Scoring Engine (`wavereader/scoring.py`)
- **Continuous Scoring Curves:** Gaussian decay models for swell height and direction, cosine decay for wind alignment, and groundswell period ramps.
- **Skill Profiles:** Specific thresholds for `beginner`, `intermediate`, `advanced`, and `expert` regulating comfort swell size, maximum safe size, wind tolerances, and maximum period.
- **Dynamic Weight Redistribution:** Automatically redistributes weights when optional fields (such as wave direction) are missing, avoiding false penalties or substitutions.
- **Batch Evaluation:** `score_week` and `rank_spots_this_week` evaluate 7-day horizons and rank spots by their best hourly score.

### 2.4 Agent Scaffold (`wavereader/agent.py`) & Tools (`wavereader/tools.py`)
- **Framework:** `smolagents.CodeAgent` with `OpenAIServerModel` supporting both Hugging Face Router and NVIDIA NIM.
- **Strict Separation:** The LLM does not generate numbers; it writes Python code to query deterministic tools:
  - `get_forecast(spot_name, region)`
  - `score_week(spot_name, region)`
  - `find_spots(query, region, skill, limit)`
  - `get_spot_knowledge(spot_name, region)`
  - `rank_spots_this_week(region, skill)`
- **Trace Capture:** Custom `AgentTrace` capturing `tool_call`, `tool_result`, `llm_chunk`, and `final_answer` events for UI visualization.

### 2.5 API Backend (`wavereader/api.py`)
- FastAPI endpoints for `/spots`, `/spots/{spot_name}`, `/forecast`, `/score`, and `/ask`.
- Standard OpenAPI schema at `/docs`.

### 2.6 Gradio Demo UI (`wavereader/app.py`)
- **Explore Tab:** Interactive Plotly `Scattergeo` map of Australia with color-coded skill buckets and spot profiles.
- **Agent Chat Tab:** Streaming LLM reasoning, live tool call badges, inspectable trace panel, and dynamic Plotly forecast/score charts.
- **Forecast Charts & Rankings Tabs:** Standalone 7-day wave/wind and hourly score breakdowns, plus regional weekly leaderboards.
- **Morning Surf Report Tab:** Embedded iframe pointing to the daggr canvas.

### 2.7 Daggr Visual Pipeline (`wavereader/daggr_pipeline.py`)
- Standalone DAG on port 7861 visualising the fixed deterministic Morning Surf Report flow: `User Input` → `Find Spots` → `Fetch Forecasts` → `Score Forecasts` → `Rank Spots` → `Format Report` + `Narrate Report`.

---

## 3. Deep System Audit & Critical Findings

While `uv run pytest` reports 134 passing tests, our deep manual inspection and live API execution uncovered the following issues:

### 🚨 Finding 1 (Critical): `agent.py` System Prompt Erases CodeAgent Prompt
- **Root Cause:** In `wavereader/agent.py` lines 253–260:
  ```python
  default_templates = yaml.safe_load(default_templates_yaml)
  default_templates["system_prompt"] = SYSTEM_PROMPT
  prompt_templates = PromptTemplates(**default_templates)
  ```
  `smolagents.prompts.code_agent.yaml` contains critical instructions teaching the model how to output code blocks (`<code>...</code>`), how to plan, and how to terminate via `final_answer(answer)`. Replacing `default_templates["system_prompt"]` directly wiped out all formatting instructions.
- **Impact:** The LLM produces raw text instead of code blocks. `CodeAgent` fails regex parsing (`regex pattern <code>(.*?)</code> was not found`), forces 10 consecutive retry steps, burns ~27k tokens, and hits max steps without an answer.
- **Resolution:** Append `SYSTEM_PROMPT` to the default template (e.g., `default_templates["system_prompt"] += "\n\n" + SYSTEM_PROMPT`), preserving the `CodeAgent` contract. Verified in live test: query resolved in 2 steps (~4s).

### 🚨 Finding 2 (Critical): NVIDIA NIM Provider Fails with 404
- **Root Cause:** `DEFAULT_MODEL = "Qwen/Qwen3-Next-80B-A3B-Instruct"` is hardcoded for both HF and NIM. Querying NVIDIA NIM (`https://integrate.api.nvidia.com/v1/models`) revealed that Qwen 80B is **not** hosted on NIM. Furthermore, because `_detect_provider()` defaults to NIM when `NVIDIA_API_KEY` exists in `.env`, the agent default was broken out-of-the-box on NIM.
- **Impact:** Anyone launching the app with an NVIDIA key experiences immediate HTTP 404 failures when asking questions.
- **Resolution:** Use provider-specific model mapping:
  - Hugging Face: `Qwen/Qwen3-Next-80B-A3B-Instruct`
  - NVIDIA NIM: `meta/llama-3.2-90b-vision-instruct` (or `meta/llama-3.2-11b-vision-instruct`)
  Verified live: `meta/llama-3.2-90b-vision-instruct` on NIM executes tool calls and returns final answers cleanly in 1 step (~6s).

### ⚠️ Finding 3: Skill Parameter Forwarding Disconnect
- **Issue:** In `wavereader/tools.py`, `rank_spots_this_week(region, skill)` accepts `skill` and filters the list of spots via `spots.find_spots`, but **does not** pass `skill_level=skill` to `scoring.rank_spots_this_week(forecasts_map, spots_list)`.
- **Impact:** Even when a user requests "beginner" breaks, the scores computed for those breaks use "intermediate" tolerances instead of the beginner profile (e.g. wave comfort size, max safe size).
- **Resolution:** Normalize skill level using the 4 canonical tiers (`beginner`, `intermediate`, `advanced`, `expert`) and pass `skill_level` to `scoring.rank_spots_this_week`, `tools.score_week`, and the `/score` FastAPI endpoint.

### ⚠️ Finding 4: Dead & Broken Matplotlib Functions in `tools.py`
- **Issue:** `plot_daily_surf_overview` and `plot_hourly_surf_drilldown` in `wavereader/tools.py` attempt to plot `df["swell_height"]` and `df["wind_speed"]`, which do not exist in the output dictionary of `scoring.score_week`. Furthermore, these functions are not included in `TOOLS` in `agent.py` because the architecture shifted to UI-side Plotly charts.
- **Resolution:** Remove or deprecate these unused functions to prevent confusion and maintain codebase cleanliness.

### ⚠️ Finding 5: Evals Discrepancy & Missing Automated Runner
- **Issue:** In `evals/golden_questions.json`, question `gq-04` asks: *"Tell me about Margaret Bay — what swell and wind does it like?"* However, no "Margaret Bay" exists in `break_details.json` (the valid WA spots are `Margaret River - Main Break` and `Margaret River - The Box`).
- **Issue:** There is currently no automated runner for `golden_questions.json` (it was tracked as TODO in `ROADMAP.md`).
- **Resolution:** Fix the break name in `gq-04` and build a standalone test script `evals/run_evals.py` that iterates through all 10 questions and validates tool calls and outputs.

### ℹ️ Finding 6: Missing Documentation Files & Minor Warnings
- `docs/ARCHITECTURE.md` links to `API.md` and `UI_GUIDE.md`, which do not exist in the repository.
- Gradio emits a UserWarning on `gr.Blocks(theme=..., css=...)` regarding parameter relocation in Gradio 6.0 (non-breaking, but clean to address).
- Clicking markers on the Australia Plotly map does not currently select the spot in the dropdown (it requires manually searching or picking from the dropdown).

---

## 4. Prioritized Action Plan (Roadmap to Demo Video)

With **Monday, September 7, 2026** as the hard recording deadline, we must focus strictly on what makes the demo video and contest entry stand out.

```
[Now: Fri Sep 4] ──▶ Phase 1: Core Fixes (Hours 0-4)
                  ──▶ Phase 2: Eval Runner & Docs (Hours 4-8)
[Sat Sep 5]      ──▶ Phase 3: UI Polish & Map Click Interaction
[Sun Sep 6]      ──▶ Phase 4: Space Deployment & End-to-End Dry Run
[Mon Sep 7]      ──▶ Phase 5: Video Recording (7 beats) & Submission
```

### Phase 1: Immediate Core Fixes (Hours 0–4)
1. **Fix `agent.py` Prompt Construction:**
   - Update prompt configuration so `SYSTEM_PROMPT` is appended to smolagents' base prompt rather than replacing it.
2. **Implement Dual-Provider Model Selection:**
   - In `agent.py`, support provider-specific default models:
     - `HF_DEFAULT_MODEL = "Qwen/Qwen3-Next-80B-A3B-Instruct"`
     - `NIM_DEFAULT_MODEL = "meta/llama-3.2-90b-vision-instruct"`
   - Ensure the UI radio toggle cleanly swaps between both endpoints.
3. **Wire Skill Through Scoring Tools & API:**
   - In `tools.py`, forward normalized `skill_level` to `scoring.rank_spots_this_week` and `scoring.score_week`.
   - Update `/score` endpoint in `api.py` to accept an optional `skill` query param.
4. **Clean up `tools.py`:**
   - Remove unused Matplotlib helper functions that have incompatible column lookups.
5. **Fix `gq-04` in `evals/golden_questions.json`:**
   - Change "Margaret Bay" to "Margaret River - Main Break".

### Phase 2: Automated Evaluation Gate (Hours 4–8)
1. **Build `evals/run_evals.py`:**
   - CLI script running the 10 golden questions through `SurfAgent`.
   - Checks assertions:
     - Did it call the required tools (`find_spots`, `rank_spots_this_week`, `get_spot_knowledge`, `score_week`)?
     - Are the numerical values consistent with the tools (no hallucinated wave sizes or scores)?
     - Did it complete without reaching max steps?
   - Outputs a clean terminal markdown scorecard.
2. **Add Missing Documentation:**
   - Create `docs/API.md` (documenting the 5 endpoints and schemas).
   - Create `docs/UI_GUIDE.md` (documenting layout, map navigation, and chat interactions).

### Phase 3: UI Polish & Contest Demo Features (Saturday, Sep 5)
1. **Map Click-to-Select:**
   - Wire `map_plot.select` / `clickData` event in `app.py` so clicking any surf spot on the Australia map immediately populates the spot card and loads its charts.
2. **User Personalization Quick-Pick:**
   - Add a lightweight "Surfer Profile" selector in the sidebar/chat (Skill: Beginner/Intermediate/Advanced/Pro, Home State: NSW/QLD/VIC/WA/SA/TAS) that auto-contextualizes agent queries.

### Phase 4: Space Deployment & Verification (Sunday, Sep 6)
1. **Hugging Face Space Deployment:**
   - Verify `uv.lock` and Python 3.12 compatibility on Spaces.
   - Configure secrets: `HF_TOKEN` and `NVIDIA_API_KEY`.
   - Run `evals/run_evals.py` against the public URL.
2. **Publish Knowledge Base:**
   - Upload `data/break_details.json` as an open dataset on the Hugging Face Hub (`lucas-hudsn/australian-surf-breaks`).

### Phase 5: Rehearsal & Recording (Monday, Sep 7)
Follow the pre-planned 2-minute video script from `ROADMAP.md`:
1. **0:00–0:10 | The Hook:** "I moved to Berlin — 16,000 km from surf. Built an agent to find waves back home."
2. **0:10–0:25 | The Problem:** Local knowledge (wind/swell alignment) & show `break_details.json` alongside raw Open-Meteo data.
3. **0:25–0:55 | Demo Q1:** *"Where should I surf near Byron Bay this weekend? Intermediate longboarder."* Show ranking cards, skill filtering, and live trace panel.
4. **0:55–1:15 | Demo Q2:** *"What time should I surf Snapper Rocks tomorrow?"* Show interactive hourly score chart with component breakdown.
5. **1:15–1:35 | Reasoning Canvas:** Switch to daggr Morning Surf Report canvas; inspect nodes live.
6. **1:35–1:50 | Under the Hood:** FastAPI Swagger UI (`/docs`), HF ↔ NIM toggle demonstration, open dataset on HF Hub.
7. **1:50–2:10 | Call to Action:** Open models on open infrastructure. NVIDIA GTC Golden Ticket submission (#NVIDIAGTC).

---

## 5. Summary Checklist

| Task | Priority | Status | Target Completion |
|---|---|---|---|
| Fix `agent.py` system prompt concatenation | **P0** | Ready to implement | Fri Sep 4 (Immediate) |
| Fix NIM provider default model (`llama-3.2-90b`) | **P0** | Verified live | Fri Sep 4 (Immediate) |
| Pass `skill` through `tools.py` into `scoring.py` | **P0** | Ready to implement | Fri Sep 4 |
| Clean up broken plot functions in `tools.py` | **P0** | Ready to implement | Fri Sep 4 |
| Fix `gq-04` spot name in `golden_questions.json` | **P0** | Ready to implement | Fri Sep 4 |
| Create automated eval runner `evals/run_evals.py` | **P1** | Scoped | Fri Sep 4 |
| Create `docs/API.md` and `docs/UI_GUIDE.md` | **P1** | Scoped | Fri Sep 4 |
| Wire Australia map marker click in Gradio | **P2** | Scoped | Sat Sep 5 |
| User profile preferences in UI | **P2** | Scoped | Sat Sep 5 |
| HF Space deploy & secrets verification | **P3** | Scoped | Sun Sep 6 |
| Publish `break_details.json` on HF Hub | **P3** | Scoped | Sun Sep 6 |
| Video recording & LinkedIn submission | **P4** | Scoped | Mon Sep 7 |
