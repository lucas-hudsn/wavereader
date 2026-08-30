# Write project documentation files for WaveReader

Create three markdown files at the repo root capturing everything agreed in this chat, as the project's source of truth for the week:

## 1. `README.md` — public-facing
- Project pitch: agentic Australian surf forecaster; the "inherent knowledge" problem; the two flagship questions.
- Features: agent answers ("Where should I surf near Byron Bay this weekend?", "What time at Snapper tomorrow?"), **interactive forecast graphs** shown whenever the agent surfaces wind/sea data (seaborn-styled), **Australia break-selector map on the home page**, agent trace panel, daggr "Morning Surf Report" canvas, HF ↔ NVIDIA NIM model toggle, 101-break open knowledge base.
- Architecture diagram + stack: FastAPI, hand-rolled tool loop (no LangChain), Gradio, daggr, Qwen3-Next-80B, Open-Meteo Marine API; note on interactivity for seaborn-style charts.
- Quickstart (uv, env vars HF_TOKEN / NVIDIA_API_KEY), HF Space link (placeholder), license note.

## 2. `AGENTS.md` — for AI coding agents working in this repo
- Project context + contest deadline context (video Mon Sep 7).
- Stack rules: pin Python 3.12; deps to add/remove; no LangChain; provider-agnostic OpenAI-compatible client; deterministic scoring engine owns the numbers, LLM only interprets.
- Repo layout, data file schemas (breaks.json, break_details.json), conventions, evals/golden_questions.json purpose.

## 3. `ROADMAP.md` — the working plan
- Day-by-day tasks Sun Aug 30 → Mon Sep 7 (as agreed, updated to include the map home page + interactive graphs on Fri's UI day).
- Daggr strategy + beta caveat (no conditional loops; fixed Morning Surf Report DAG).
- Shot-by-shot video script (~2 min) with the Berlin move/open-to-work CTA.
- LinkedIn post copy skeleton (contest entry + Berlin announcement).
- Risks & fallbacks section.

No code changes — documentation only.