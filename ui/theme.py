"""Lo-fi wave~reader theme (light blue bg, dark blue Courier).

Ported verbatim from ``app/theme.py`` — the v2 UI keeps the same identity.
"""

from __future__ import annotations


APP_CSS = """
/* wave~reader lo-fi theme: light blue bg (#eef6fd everywhere), dark blue font */
.gradio-container, .gradio-container-4x, main, body {
    background: #eef6fd !important;
    color: #0b2c5c !important;
    font-family: "Courier New", Courier, monospace !important;
}
.gradio-container h1, .gradio-container h2, .gradio-container h3,
.gradio-container p, .gradio-container span, .gradio-container label,
.gradio-container .markdown, .prose {
    color: #0b2c5c !important;
    font-family: "Courier New", Courier, monospace !important;
}
.hero-title {
    font-size: 2.2em !important;
    letter-spacing: 1px;
    text-transform: lowercase;
    margin-bottom: 0 !important;
}
.hero-sub {
    font-size: 0.78em !important;
    margin: 0 !important;
    opacity: 0.75;
}
button, select {
    font-family: "Courier New", Courier, monospace !important;
}
/* primary (orange) buttons -> dark blue */
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
.break-list { max-height: 210px; overflow-y: auto; border: 1px solid #0b2c5c; border-radius: 8px; padding: 4px; background: #eef6fd !important; }
/* selected break dot -> dark blue (radio circle fill + border) */
.break-list input[type="radio"]:checked,
.break-list input[type="checkbox"]:checked {
    background-color: #0b2c5c !important;
    border-color: #0b2c5c !important;
    accent-color: #0b2c5c !important;
}
.break-list label.selected {
    background: #d6e9f8 !important;
    color: #0b2c5c !important;
}
/* blocks match the page bg (#eef6fd) — padding + dark borders define them */
.gradio-container {
    --background-fill-primary: #eef6fd !important;
    --background-fill-secondary: #eef6fd !important;
    --block-background-fill: #eef6fd !important;
    --block-border-color: #0b2c5c !important;
    --block-label-background-fill: #eef6fd !important;
    --block-label-text-color: #0b2c5c !important;
    --input-background-fill: #ffffff !important;
    --input-border-color: #0b2c5c !important;
    --input-placeholder-color: #4a6fa5 !important;
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
    --block-title-text-size: 15px !important;
    --checkbox-background-color-selected: #0b2c5c !important;
    --checkbox-border-color-selected: #0b2c5c !important;
    --checkbox-border-color-focus: #0b2c5c !important;
    --checkbox-border-color-hover: #0b2c5c !important;
    --checkbox-label-background-fill-selected: #d6e9f8 !important;
    --checkbox-label-text-color-selected: #0b2c5c !important;
}
.gradio-container .gr-box, .gradio-container .gr-panel,
.gradio-container .block, .gradio-container .form,
.gradio-container .gr-group, .gradio-container .gr-block,
.gradio-container .tabitem, .gradio-container .tabs {
    background: #eef6fd !important;
    border-color: #0b2c5c !important;
    border-width: 2px !important;
    border-radius: 12px !important;
    padding: 11px !important;
    gap: 8px !important;
}
.gradio-container input, .gradio-container textarea,
.gradio-container select, .gradio-container .gr-textbox,
.gradio-container .gr-dropdown, .gradio-container .gr-radio,
.gradio-container .gr-checkbox, .gradio-container .gr-dataframe {
    background: #ffffff !important;
    border-color: #0b2c5c !important;
    color: #0b2c5c !important;
}
.gradio-container table, .gradio-container thead,
.gradio-container tbody, .gradio-container th,
.gradio-container td, .gradio-container .table-wrap {
    background: #eef6fd !important;
    color: #0b2c5c !important;
}
.gradio-container tbody tr:nth-child(even) {
    background: #eef6fd !important;
}
.gradio-container .message, .gradio-container .bubble,
.gradio-container .message-wrap {
    background: #ffffff !important;
    border-color: #0b2c5c !important;
    color: #0b2c5c !important;
}
/* browse tabs stand out: big lowercase pill tabs, same courier + dark blue */
.gradio-container .tab-nav {
    gap: 14px !important;
    padding: 6px 2px 12px 2px !important;
    border-bottom: 2px solid #0b2c5c !important;
    background: transparent !important;
}
.gradio-container .tab-nav button {
    background: #eef6fd !important;
    color: #0b2c5c !important;
    border: 2px solid #0b2c5c !important;
    border-radius: 999px !important;
    font-size: 1.15em !important;
    font-weight: bold !important;
    text-transform: lowercase !important;
    letter-spacing: 1px !important;
    padding: 10px 28px !important;
}
.gradio-container .tab-nav button:hover {
    background: #d6e9f8 !important;
}
.gradio-container .tab-nav button.selected {
    background: #0b2c5c !important;
    color: #ffffff !important;
    border-color: #0b2c5c !important;
}
/* agentic-mode sliding toggle: style the checkbox as an on/off switch */
.mode-switch input[type="checkbox"] {
    appearance: none !important;
    -webkit-appearance: none !important;
    width: 52px !important;
    height: 28px !important;
    border-radius: 999px !important;
    background: #8fb8dd !important;
    border: 2px solid #0b2c5c !important;
    position: relative !important;
    cursor: pointer !important;
    outline: none !important;
    flex-shrink: 0 !important;
}
.mode-switch input[type="checkbox"]::after {
    content: "" !important;
    position: absolute !important;
    top: 1px !important;
    left: 2px !important;
    width: 20px !important;
    height: 20px !important;
    border-radius: 50% !important;
    background: #ffffff !important;
    border: 2px solid #0b2c5c !important;
    transition: left 0.15s ease-in-out !important;
}
.mode-switch input[type="checkbox"]:checked {
    background: #0b2c5c !important;
}
.mode-switch input[type="checkbox"]:checked::after {
    left: 24px !important;
}
/* header row: title left, compact toggle pinned top-right */
.header-row { align-items: flex-start !important; flex-wrap: nowrap !important; overflow: visible !important; }
/* messenger-style chat: input row pinned under the chat log */
.chat-input-row { align-items: flex-end !important; }
.mode-switch-wrap { max-width: 320px !important; min-width: 230px !important; margin-left: auto !important; flex-grow: 0 !important; flex-shrink: 0 !important; overflow: visible !important; padding-right: 8px !important; }
.mode-switch { max-width: 320px !important; overflow: visible !important; }
.mode-switch-wrap label { font-size: 0.85em !important; white-space: nowrap !important; overflow: visible !important; text-overflow: clip !important; max-width: none !important; padding-right: 8px !important; }
.mode-switch span, .mode-switch .gr-checkbox-label { overflow: visible !important; text-overflow: clip !important; white-space: nowrap !important; max-width: none !important; }
"""
