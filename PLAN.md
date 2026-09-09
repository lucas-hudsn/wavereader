wave~reader v2 — 6-hour rebuild plan
What I found (why a redo is justified)
Keep (genuinely good): the "LLM never owns numbers" split; scoring.py skill-calibrated Gaussian curves; forecasts.py versioned/atomic/stale-fallback cache + seaward grid-snap; seafloor.py GEBCO grid → shelf class → 2D/3D/transect figs; the lo-fi Courier identity; the <think>/marker-stripping streaming pattern.
Broken / weak (confirmed with file refs):

- Three different model ids are hardcoded across the code, none matching the README/AGENTS.md: Nemotron-3-Ultra-550B on deepinfra (app/agent.py:163, app/generate_surf_report.py:35, app/generate_surf_break.py:57) and Qwen2.5-7B on hf-inference (app/generate_seafloor_report.py:22). Ultra is $1/$5 per Mtok — on a $0.10 free tier that's a handful of agent turns.
- Agent = CodeAgent + ~300 lines of monkey-patching private smolagents internals (\_step_stream, per-instance forward, agent.py:656-763, 843-852) purely to recover tool traces the framework hides inside python_interpreter. Fragile, and 12k-token system prompt per step.
- Scoring ignores swell*wave*\* (fetched but unused, forecasts.py:39-46), tide, idealWind.type, uses a flat 15 kt wind cap for every break (adapters.py:32), a 10→0 wind cliff, cyclic-mean of ideal directions instead of a window, scores night hours, ranks by single best hour.
- Dataset is low-variance LLM guesswork: 233/238 breaks "mid/high" tide, 238/238 "autumn", coords rounded to arc-minutes.
- ui.py 710-line monolith, 9 gr.States, two-way filter↔prefs mirroring; no tests at all; <data> injection guard trivially escapable (prompt_guard.py:70-78).
- Uncommitted WIP across 20 files.
  Target architecture
  wavereader/ # pure core: typed, tested, no Gradio imports
  breaks.py # load + jsonschema-validate data/, resolve names
  openmeteo.py # marine + weather + _archive_ client, cache (ported)
  climate.py # NEW: 5-yr ERA5 wave climatology per break
  scoring.py # v2 engine (ported + upgraded)
  seafloor.py # ported, slope math fixed
  tools.py # THE 9 typed tool functions (single source for agent + MCP)
  agent.py # smolagents ToolCallingAgent factory + event stream
  narrate.py # streamed Nemotron write-up (numbers-in, prose-out)
  llm.py # one InferenceClient factory: model/provider/token from env
  ui/ # Gradio 6, lo-fi theme kept
  app.py panels/{book,swell,agent}.py charts/\*.py theme.py
  scripts/build_climate.py scripts/eval_agent.py
  tests/ # pytest, offline fixtures
  app.py # HF Space entry: demo.launch(mcp_server=True)
  One model, one door: nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16 via HF Inference Providers (fireworks-ai; provider table confirms tools + structured output supported). WR_MODEL / WR_PROVIDER / WR_BASE_URL env overrides so a local Ollama/NIM endpoint works but Nemotron stays the story. Delete Ultra/Qwen references entirely.
  The five upgrades that make it "cutting edge"

1. Climatology grounding (the headline). scripts/build_climate.py pulls Open-Meteo marine archive (ERA5, free, no key) daily swell_wave_height_max / swell_wave_direction_dominant / swell_wave_period_max for 5 years × 238 breaks (~238 calls, ~10 min, cached to data/climate/\*.json). From it compute per break: swell-direction rose, monthly height/period medians, "best season" by count of days in the break's ideal size window. Then audit the LLM-generated fields: flag where idealSwell.direction/bestSeason disagree with observed climate, and let the score use the observed window. Story: "open reanalysis data corrects an open model's guesses — and the agent tells you when it did."
2. Scoring v2: swell components from swell*wave*\*; direction score = distance to the arc of ideal directions; wind cap from idealWind.type + break type; smooth logistic wind roll-off; daylight-only hours (sunrise/sunset already fetched); daily score = p75 of daylight hours (consistency), rank by surfable-hours + best. Property tests pin monotonicity.
3. Agent rebuilt on native tool calling: smolagents ToolCallingAgent with @tool-decorated functions from wavereader/tools.py, stream=True yields real ToolCall/ToolOutput — delete all monkey-patching and agent_trace.py coercion hacks. Hard budget: max_steps=6, ≤2 score_week per turn, max_tokens=700, reasoning_effort off. Compact system prompt (<1.5k tokens). Charts render straight from typed tool payloads. Add a token meter in the UI (prompt/completion tokens per turn) — makes the budget discipline visible.
4. MCP server for free: demo.launch(mcp_server=True) with the tool functions exposed via @gr.api() — the Space gets the MCP badge, and any agent (opencode included) can call score_week / rank_region_week / explain_score deterministically. Demo: opencode using the Space as a tool.
5. Tests + eval: offline pytest over recorded Open-Meteo fixtures (scoring, adapters, climate, tools); scripts/eval_agent.py with 8 golden questions asserting which tools were called (1 live run ≈ 8 × ~5k tokens — pennies on Lightning). Results table goes in README.
   Cut: custom-break generation (inference spend, weak value), seafloor LLM explainer (wrong model, adds nothing over deterministic markdown), surf cams overlay, filter↔prefs mirroring. Keep seafloor deterministic charts.
   BYO token: UI accepts an HF_TOKEN textbox (session-only) and the Space secret is the fallback, so visitors don't drain your $0.10.
   Timeline (6h, 4 GLM-5.3-Flash workers + you as orchestrator)
   Workers are manual opencode sessions; each brief below is paste-ready. Give every worker the same standing rules: never read .env; run uv run pytest -q + uv run python -c "import wavereader, ui.app" before declaring done; don't touch files outside your package; no new deps without listing them; Nemotron-only; commit to your branch every 30 min.
   H0:00–0:20 — Orchestrator (you)

- git add -A && git commit -m "wip: pre-rebuild snapshot" && git tag pre-rebuild
- git checkout -b v2; create empty wavereader/ ui/ tests/ scripts/; add deps: pydantic, jsonschema, pytest, gradio[mcp], smolagents[toolkit]; drop pandas if unused. Add .env.example vars HF_TOKEN, WR_MODEL, WR_PROVIDER, WR_BASE_URL.
- Verify budget once: a single 50-token Nemotron Lightning call via InferenceClient(provider="fireworks-ai") and check the cost line in HF billing.
- Spin up workers A–D on branches v2-core, v2-climate, v2-agent, v2-ui.
  H0:20–2:30 — parallel
  Worker A — core port + scoring v2 (v2-core)
  Port app/forecasts.py→wavereader/openmeteo.py (add swell_wave_direction, swell_wave_period hourly vars, bump CACHE_VERSION), app/adapters.py+app/scoring.py→wavereader/scoring.py, app/seafloor.py→wavereader/seafloor.py (fix lon step in slope, skip None cells), app/breaks_data.py→wavereader/breaks.py with jsonschema validation against data/surf-break-schema.json. Implement scoring v2: swell fields, ideal-direction arc distance, wind cap from idealWind.type (offshore 18 kt, cross 12, onshore 8, light/variable 10) with logistic roll-off, daylight filtering using daily.sunrise/sunset, daily_summary() = p75 of daylight scores, rank() by (surfable_hours ≥6, best). Write tests/fixtures/openmeteo_bells.json by recording one real call, then tests for every component incl. monotonicity properties. Exports: get_forecast, score_week, score_hour, rank_spots, resolve_break, load_breaks, get_seafloor.
  Worker B — climatology (v2-climate)
  wavereader/climate.py + scripts/build_climate.py: Open-Meteo marine archive (/v1/archive, daily swell_wave_height_max,swell_wave_direction_dominant,swell_wave_period_max, last 5 full years, seaward offset reused from openmeteo.py), 1 req/s, resumable, writes data/climate/<id-slug>.json (16-bin direction rose in %, monthly median height/period, days-in-ideal-window per month) and one data/climate/index.json. audit_break(break, climate) -> list[Finding] comparing idealSwell.direction vs rose top-3 and bestSeason vs top months. Plotly climate_rose_fig(). Run the full build once. Tests over one fixture file.
  Worker C — agent + narrator (v2-agent)
  wavereader/llm.py (InferenceClient factory from env, Nemotron Lightning/fireworks default, WR_BASE_URL → OpenAI-compatible path). wavereader/tools.py: 9 @tool functions with docstrings + typed returns (get_spot_knowledge, get_climate_profile, score_week, rank_region_week, explain_score, find_best_windows, find_spots, find_similar_spots, list_regions) wrapping Worker A/B exports (stub imports until merge; agree on signatures in the first 15 min). wavereader/agent.py: ToolCallingAgent, compact system prompt (≤1.5k tokens, output contract: verdict → picks → why → hazards), run_stream() yielding typed events {kind: token|tool_call|tool_result|final|usage}, per-turn budget guard. wavereader/narrate.py: port generate_surf_report.py (daily summaries in, streamed markdown out, marker/think stripping kept). scripts/eval_agent.py: 8 questions × expected tool names, dry-run mode with a fake model for tests.
  Worker D — Gradio 6 UI (v2-ui)
  ui/theme.py (port APP_CSS verbatim), ui/charts/{score,swell,wind,map,seafloor}.py (port Plotly builders), ui/panels/book.py (map + filters + details + climate rose + audit findings), ui/panels/swell.py (score/swell/wind/seafloor tabs, daily summary hero, narrate button), ui/panels/agent.py (chat with tool cards, token meter, charts from tool payloads, BYO token box), ui/app.py::build(), root app.py with launch(mcp_server=True) and @gr.api() tool exposure. ≤3 gr.State. Build against Worker A/C stubs; wire real modules after merge.
  H2:30–3:30 — Orchestrator: integrate
  Merge order v2-core → v2-climate → v2-agent → v2-ui. Run uv run pytest -q, uv run python app.py, click through all three panels, run scripts/eval_agent.py live once (record token cost), test MCP: curl localhost:7860/gradio_api/mcp/schema, then add to opencode as an MCP server and ask it to score a break.
  H3:30–4:30 — polish (2 workers)
- Worker A: fix eval failures; tighten prompt; scoring edge cases from real data (nulls, TAS offsets).
- Worker D: visual pass — loading states, empty states, mobile width, audit-finding chips, MCP badge copy.
  H4:30–5:15 — deploy
  Create HF Space (Gradio SDK, CPU basic), requirements.txt exported from uv, secret HF_TOKEN, push v2. Confirm /gradio_api/mcp/ responds publicly. Delete app/, main.py; git rm old docs.
  H5:15–6:00 — docs + demo
  Rewrite README.md (architecture, climatology audit story, eval table with token costs, MCP usage snippet), AGENTS.md for the new layout, refresh documents/\*.md or delete stale ones. Record a 90-second walkthrough: ask the agent "best intermediate wave in the Surf Coast this weekend", show the tool cards, the climate audit correcting the dataset, then call the same tool from opencode over MCP.
  Risks and the fallback for each
  Risk Fallback
  Nemotron Lightning tool-calling unreliable via fireworks Keep a CodeAgent switch in agent.py (WR_AGENT=code); test in H0:20 before Worker C commits
  Open-Meteo archive rate limit during climate build Script is resumable; ship partial coverage + note
  Gradio 6 @gr.api MCP exposure quirks Minimum: mcp_server=True on the swell-check panel functions (they have typed inputs)
  Merge conflicts Strict package ownership per worker; interface signatures agreed in first 15 min and pinned in wavereader/tools.py stubs
  Budget All live LLM calls gated behind one factory; eval run is the only mandatory spend (~$0.01)
