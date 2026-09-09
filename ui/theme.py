"""Lo-fi wave~reader theme (page-blue bg, ink-blue IBM Plex Mono).

One CSS string for the single-page app: instrument-panel blocks on the
#eef6fd page, pill chips (engines / days / badges / skills), left-set
type everywhere. Identity note: the mono face changed from Courier New
to IBM Plex Mono (self-hosted font via Google Fonts, Courier fallback
when offline) — same ink, more designed.
"""

from __future__ import annotations


APP_CSS = """
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:ital,wght@0,400;0,500;0,600;0,700;1,400&display=swap');

/* wave~reader lo-fi theme: page blue everywhere, ink-blue mono type */
.gradio-container, .gradio-container-4x, main, body {
    background: #eef6fd !important;
    color: #0b2c5c !important;
    font-family: 'IBM Plex Mono', 'Courier New', Courier, monospace !important;
}
.gradio-container h1, .gradio-container h2, .gradio-container h3,
.gradio-container p, .gradio-container span, .gradio-container label,
.gradio-container .markdown, .gradio-container .prose {
    color: #0b2c5c !important;
    font-family: 'IBM Plex Mono', 'Courier New', Courier, monospace !important;
    text-align: left !important;
}
/* markdown blocks: never justify, no oversized empty boxes */
.gradio-container .markdown { text-align: left !important; min-height: 0 !important; }
.gradio-container p { margin: 2px 0 !important; }
/* Gradio paints em/strong/li/code near-white by default — always inherit the ink */
.gradio-container em, .gradio-container i,
.gradio-container strong, .gradio-container b,
.gradio-container li, .gradio-container ul, .gradio-container ol,
.gradio-container code {
    color: inherit !important;
}

.hero-title {
    font-size: 2.1em !important;
    font-weight: 700 !important;
    letter-spacing: 1px;
    text-transform: lowercase;
    margin-bottom: 0 !important;
}
.hero-sub { font-size: 0.78em !important; margin: 0 !important; opacity: 0.75; }
/* hero band: title + toggle on one line, engine strip below, rule under */
.hero-band { padding: 2px 0 6px !important; border-bottom: 2px solid #c9dff2; margin-bottom: 8px; }
.hero-row { align-items: center !important; flex-wrap: nowrap !important; overflow: visible !important; }
.hero-right { display: flex !important; justify-content: flex-end; align-items: center; }

button, select, input, textarea {
    font-family: 'IBM Plex Mono', 'Courier New', Courier, monospace !important;
}
/* primary (orange) buttons -> ink blue */
.gradio-container {
    --button-primary-background-fill: #0b2c5c !important;
    --button-primary-background-fill-hover: #13407e !important;
    --button-primary-text-color: #ffffff !important;
    --button-primary-border-color: #0b2c5c !important;
}
.gradio-container button.primary,
.gradio-container .gr-button-primary,
button.primary, button.lg.primary {
    background: #0b2c5c !important;
    border-color: #0b2c5c !important;
    color: #ffffff !important;
}
.gradio-container button.primary:hover,
.gradio-container .gr-button-primary:hover,
button.primary:hover, button.lg.primary:hover {
    background: #13407e !important;
    border-color: #13407e !important;
    color: #ffffff !important;
}

/* blocks match the page bg — padding + ink borders define them */
.gradio-container {
    --body-text-color: #0b2c5c !important;
    --background-fill-primary: #eef6fd !important;
    --background-fill-secondary: #eef6fd !important;
    --block-background-fill: #eef6fd !important;
    --block-border-color: #0b2c5c !important;
    --block-label-background-fill: #eef6fd !important;
    --block-label-text-color: #0b2c5c !important;
    --input-background-fill: #ffffff !important;
    --input-border-color: #0b2c5c !important;
    --input-placeholder-color: #4a6fa5 !important;
    --code-background-fill: #d6e9f8 !important;
    --table-background-fill: #eef6fd !important;
    --table-border-color: #0b2c5c !important;
    --table-odd-background-fill: #eef6fd !important;
    --table-even-background-fill: #eef6fd !important;
    --chatbot-code-background-fill: #eef6fd !important;
    --button-secondary-background-fill: #eef6fd !important;
    --button-secondary-background-fill-hover: #d6e9f8 !important;
    --button-secondary-text-color: #0b2c5c !important;
    --button-secondary-border-color: #0b2c5c !important;
    --button-cancel-background-fill: #eef6fd !important;
    --button-cancel-text-color: #0b2c5c !important;
    --button-cancel-border-color: #0b2c5c !important;
    --block-border-width: 2px !important;
    --block-shadow: none !important;
    --block-title-text-size: 14px !important;
    --checkbox-background-color-selected: #0b2c5c !important;
    --checkbox-border-color-selected: #0b2c5c !important;
    --checkbox-label-background-fill: #ffffff !important;
    --checkbox-label-background-fill-selected: #0b2c5c !important;
    --checkbox-label-border-color: #0b2c5c !important;
    --checkbox-label-border-color-selected: #0b2c5c !important;
    --checkbox-label-text-color: #0b2c5c !important;
    --checkbox-label-text-color-selected: #ffffff !important;
}
.gradio-container .gr-box, .gradio-container .gr-panel,
.gradio-container .block, .gradio-container .form,
.gradio-container .gr-group, .gradio-container .gr-block {
    background: #eef6fd !important;
    border-color: #0b2c5c !important;
    border-width: 2px !important;
    border-radius: 12px !important;
    padding: 10px !important;
    gap: 6px !important;
}
.gradio-container input, .gradio-container textarea,
.gradio-container select, .gradio-container .gr-textbox,
.gradio-container .gr-dropdown, .gradio-container .gr-radio,
.gradio-container .gr-checkbox, .gradio-container .gr-dataframe {
    background: #ffffff !important;
    border-color: #0b2c5c !important;
    color: #0b2c5c !important;
}
/* dropdown value + its open option list: compact type — the Gradio defaults
   (14px field, 16px inherited list) read oversized next to the 12px labels */
.gradio-container .secondary-wrap input,
ul.options .item {
    font-size: 13px !important;
}
.gradio-container table, .gradio-container thead,
.gradio-container tbody, .gradio-container th,
.gradio-container td, .gradio-container .table-wrap {
    background: #eef6fd !important;
    color: #0b2c5c !important;
}
.gradio-container tbody tr:nth-child(even) { background: #eef6fd !important; }
.gradio-container .message, .gradio-container .bubble,
.gradio-container .message-wrap {
    background: #ffffff !important;
    border-color: #0b2c5c !important;
    color: #0b2c5c !important;
}
/* radio pill row (mode toggle, agent depth): tight inline options */
.gradio-container .gr-radio { gap: 6px !important; }
.gradio-container .gr-radio label {
    border: 2px solid #0b2c5c !important;
    border-radius: 999px !important;
    background: #ffffff !important;
    color: #0b2c5c !important;
    padding: 3px 10px !important;
    font-size: 0.82em !important;
}
.gradio-container .gr-radio label.selected,
.gradio-container label:has(input[type="radio"]:checked),
.gradio-container label:has(input[type="checkbox"]:checked) {
    background: #0b2c5c !important;
    color: #ffffff !important;
}
.gradio-container .gr-radio label.selected span,
.gradio-container label:has(input:checked) span { color: #ffffff !important; }
/* accordions read as sections of one instrument */
.gradio-container details, .gradio-container .accordion-wrap, .gradio-container summary {
    border-color: #0b2c5c !important;
    color: #0b2c5c !important;
}
.gradio-container summary, .gradio-container .label-wrap span {
    font-family: 'IBM Plex Mono', 'Courier New', Courier, monospace !important;
    font-weight: 700 !important;
    text-transform: lowercase !important;
    letter-spacing: 0.5px !important;
    color: #0b2c5c !important;
}

/* engine strip: lo-fi chips naming every engine, faint trailing note */
.engine-md { margin: 0 !important; }
.engine-strip { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 2px 0; }
.engine-note { font-size: 0.68em; opacity: 0.65; margin-left: 4px; }
.engine-chip {
    display: inline-block; border: 2px solid #0b2c5c; border-radius: 999px;
    padding: 2px 10px; font-size: 0.72em; background: #ffffff; color: #0b2c5c;
    white-space: nowrap;
}

/* spot badges: identity + hazards + surf cam */
.badge-row { display: flex; flex-wrap: wrap; gap: 6px; margin: 4px 0; }
.badge-chip {
    display: inline-block; border: 2px solid #0b2c5c; border-radius: 999px;
    padding: 3px 10px; font-size: 0.78em; background: #ffffff; color: #0b2c5c;
}
.badge-warn { background: #fef7e0 !important; }
.badge-link { background: #d6e9f8 !important; text-decoration: none; font-weight: 600; }
.badge-link:hover { background: #0b2c5c !important; color: #ffffff !important; }

/* week hero: day chips with score-coloured left borders */
.day-chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0; }
.day-chip {
    display: inline-flex; flex-direction: column; gap: 0;
    border: 1px solid #c9dff2; border-left: 5px solid #91cf60;
    border-radius: 8px; padding: 4px 10px; background: #ffffff; color: #0b2c5c;
    font-size: 0.8em; line-height: 1.5; min-width: 86px;
}
.day-chip b { font-size: 1.05em; }
.day-chip i { font-style: normal; opacity: 0.8; }
.hero-cap { font-size: 0.85em; font-weight: 700; margin-top: 4px; }

/* map skill legend chips */
.skill-legend { display: flex; flex-wrap: wrap; gap: 10px; margin: 2px 4px; }
.skill-chip { display: inline-flex; align-items: center; gap: 5px; font-size: 0.75em; color: #0b2c5c; }
.skill-chip i { display: inline-block; width: 10px; height: 10px; border-radius: 50%; border: 1px solid #0b2c5c; }

/* strip caption: how to read the instrument */
.strip-caption { font-size: 0.72em; opacity: 0.75; margin: 0 4px; }

/* lens column sticks while the story scrolls past */
.lens-col { position: sticky !important; top: 8px; align-self: flex-start !important; }

/* agent bar: full-width sidekick under the main row */
.agent-col { margin-top: 4px; }

/* messenger-style chat: input row pinned under the chat log */
.chat-input-row { align-items: flex-end !important; }

/* agent controls row: depth radio + region focus on one tight line */
.agent-controls { align-items: flex-end !important; gap: 8px !important; }
.agent-controls .gr-radio { flex-wrap: nowrap !important; }
.ctx-line { font-size: 0.78em; opacity: 0.8; margin: 0 2px 4px !important; }

/* agent trace: live tool cards with ms timing bars + payload previews */
.trace { display: flex; flex-direction: column; gap: 6px; }
.trace-ask { font-size: 0.78em; opacity: 0.7; margin-bottom: 2px; }
.trace-card {
  border: 2px solid #0b2c5c; border-radius: 10px; background: #ffffff;
  padding: 6px 10px; font-size: 0.78em; color: #0b2c5c;
}
.trace-card.pending { border-style: dashed; opacity: 0.75; }
.trace-head { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.trace-head code { font-size: 0.95em; word-break: break-all; }
.trace-ms { margin-left: auto; opacity: 0.8; white-space: nowrap; font-weight: 600; }
.trace-bar {
  height: 6px; background: #eef6fd; border: 1px solid #c9dff2;
  border-radius: 999px; margin: 4px 0 2px; overflow: hidden;
}
.trace-bar i { display: block; height: 100%; background: #0b2c5c; }
.trace-summary { opacity: 0.85; margin-top: 2px; }
.trace-card details { margin-top: 3px; }
.trace-card pre {
  background: #eef6fd; border: 1px solid #c9dff2; border-radius: 6px;
  padding: 6px; font-size: 0.9em; overflow-x: auto;
  white-space: pre-wrap; word-break: break-word; margin: 3px 0 0;
}
.trace-empty, .rank-empty { font-size: 0.8em; opacity: 0.6; }

/* verdict banner: the answer's contract line, front and centre */
.verdict-slot { border: none !important; padding: 0 !important; background: transparent !important; box-shadow: none !important; }
.verdict-banner {
  border: 2px solid #0b2c5c; border-radius: 12px; background: #ffffff;
  padding: 8px 14px; font-size: 1.02em; margin: 2px 0 6px;
}
.verdict-banner:empty { display: none; }

/* ranked leaderboard cards */
.rank-list { display: flex; flex-direction: column; gap: 6px; }
.rank-card {
  display: flex; align-items: center; gap: 10px;
  border: 2px solid #0b2c5c; border-radius: 10px; background: #ffffff;
  padding: 6px 10px; font-size: 0.8em; color: #0b2c5c;
}
.rank-card .rank-num { font-weight: 700; min-width: 30px; }
.rank-card .rank-name { min-width: 0; }
.rank-card .rank-name i { opacity: 0.75; }
.rank-card .rank-score { margin-left: auto; font-weight: 700; white-space: nowrap; }
.rank-card .rank-time { opacity: 0.8; white-space: nowrap; }

/* chip buttons wrap instead of stretching one per row */
.chip-btn { white-space: normal !important; height: auto !important; min-height: 0 !important; }

/* mode toggle: sliding pill switch in the header — forecast vs agentic */
.mode-toggle {
  display: inline-flex; align-items: center; gap: 0;
  background: #ffffff; border: 1px solid #c9dff2; border-radius: 999px;
  padding: 3px; width: fit-content; margin: 0 0 0 auto;
}
.mode-toggle .wrap { display: inline-flex !important; gap: 0 !important; }
.mode-toggle input[type="radio"],
.mode-toggle input[type="radio"] + * .circle,
.mode-toggle span.circle { display: none !important; }
.mode-toggle label {
  border-radius: 999px !important; padding: 4px 14px !important;
  font-size: 0.78em; font-weight: 600; color: #0b2c5c; cursor: pointer;
  border: none !important; box-shadow: none !important; background: transparent !important;
  transition: background 0.18s ease, color 0.18s ease;
}
.mode-toggle label.selected {
  background: #0b2c5c !important; color: #ffffff !important;
}

/* mobile: stack columns, shrink map */
@media (max-width: 700px) {
  .gradio-container .gr-row { flex-wrap: wrap !important; }
  .gradio-container .gr-column { min-width: 100% !important; }
  .lens-col { position: static !important; }
  .hero-title { font-size: 1.6em !important; }
}
"""
