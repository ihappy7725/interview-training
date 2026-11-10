"""레퍼런스(화상회의 대시보드) 톤의 모던·클린 테마 CSS와 HTML 조각."""
from __future__ import annotations

import html

PRIMARY = "#1570C9"
PRIMARY_SOFT = "#EAF3FC"
DANGER = "#E5372B"
GOOD = "#22A06B"
WARN = "#F08C00"
TEXT = "#1D2939"
MUTED = "#667085"

CSS = f"""
<style>
@import url("https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css");
html, body, .stApp, [class*="css"], button, input, textarea {{
  font-family: "Pretendard", -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif !important;
}}
.stApp {{ background: #F3F5F8; }}
header[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 3.6rem; padding-bottom: 3rem; max-width: 1380px; }}
h1, h2, h3, h4 {{ color: {TEXT}; letter-spacing: -0.02em; }}

/* ── Sidebar ─────────────────────────────── */
section[data-testid="stSidebar"] {{ background: #FFFFFF; border-right: 1px solid #ECEEF2; }}
section[data-testid="stSidebar"] div[role="radiogroup"] {{ gap: 4px; }}
section[data-testid="stSidebar"] div[role="radiogroup"] label {{
  padding: 10px 14px; border-radius: 12px; width: 100%; margin: 0;
  border-left: 4px solid transparent; transition: background .15s;
}}
section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {{ background: #F5F8FC; }}
section[data-testid="stSidebar"] div[role="radiogroup"] label > div > div:first-child:not([data-testid]) {{ display: none; }}
section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {{
  background: {PRIMARY_SOFT}; border-left: 4px solid {PRIMARY};
}}
section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) p {{ color: {PRIMARY}; font-weight: 700; }}

/* ── Cards (st.container(key="card_…")) ─── */
[class*="st-key-card"] {{
  background: #FFFFFF; border-radius: 18px; padding: 20px 22px;
  box-shadow: 0 1px 2px rgba(16,24,40,.04), 0 6px 24px rgba(16,24,40,.06);
  border: 1px solid #EEF0F4;
}}
[class*="st-key-panel"] {{
  background: {PRIMARY_SOFT}; border-radius: 14px; padding: 12px 16px;
}}

/* ── Buttons ─────────────────────────────── */
.stButton > button, .stDownloadButton > button {{
  border-radius: 12px; font-weight: 600; padding: 0.55rem 1rem; border: 1px solid #E4E7EC;
}}
.stButton > button[kind="primary"] {{ background: {PRIMARY}; border-color: {PRIMARY}; }}
[class*="st-key-btn_danger"] button {{ background: {DANGER} !important; color: #fff !important; border-color: {DANGER} !important; }}
[class*="st-key-btn_cta"] button {{
  background: {PRIMARY} !important; color: #fff !important; border: none !important;
  padding: 0.85rem 1rem; font-size: 1rem; box-shadow: 0 6px 16px rgba(21,112,201,.25);
}}

/* ── Inputs ──────────────────────────────── */
.stTextInput input, .stTextArea textarea {{ border-radius: 12px !important; background: #FAFBFC; }}
[data-testid="stAudioInput"] {{ border-radius: 14px; }}

/* ── Custom HTML ─────────────────────────── */
.hdr-sub {{ color: {MUTED}; font-size: .85rem; display:flex; align-items:center; gap:8px; }}
.badge {{ display:inline-block; padding: 2px 10px; border-radius: 999px; font-size: .75rem; font-weight: 600;
          background: {PRIMARY_SOFT}; color: {PRIMARY}; }}
.badge.gray {{ background:#F2F4F7; color:{MUTED}; }}
.badge.good {{ background:#E7F6EE; color:{GOOD}; }}
.badge.warn {{ background:#FFF4E5; color:{WARN}; }}
.badge.bad {{ background:#FDECEB; color:{DANGER}; }}
.hdr-title {{ font-size: 1.6rem; font-weight: 800; color:{TEXT}; margin: 2px 0 0 0; letter-spacing:-0.03em; }}
.sec-title {{ font-weight: 700; color: {PRIMARY}; font-size: 1.02rem; margin: 0; }}
.q-card {{ background: linear-gradient(135deg, #1570C9 0%, #2B8AE0 100%); color:#fff; border-radius: 16px;
           padding: 18px 20px; margin-bottom: 10px; }}
.q-card .q-meta {{ font-size:.8rem; opacity:.85; margin-bottom:6px; }}
.q-card .q-text {{ font-size:1.18rem; font-weight:700; line-height:1.5; }}
.q-card .q-tip {{ font-size:.82rem; opacity:.9; margin-top:8px; }}
.live-row {{ display:flex; justify-content:space-between; align-items:center; padding: 9px 2px;
             border-bottom: 1px solid #F0F2F5; font-size:.92rem; color:{TEXT}; }}
.live-row:last-child {{ border-bottom: none; }}
.live-row b {{ font-weight:700; }}
.coach-msg {{ border-radius: 12px; padding: 10px 14px; font-weight:600; font-size:.92rem; margin-bottom:6px; }}
.coach-msg.good {{ background:#E7F6EE; color:{GOOD}; }}
.coach-msg.warn {{ background:#FFF4E5; color:{WARN}; }}
.coach-msg.bad  {{ background:#FDECEB; color:{DANGER}; }}
.bubble {{ background:#F2F4F7; border-radius: 14px 14px 14px 4px; padding: 12px 14px; color:{TEXT};
           font-size:.93rem; line-height:1.6; margin: 6px 0; }}
.bubble.me {{ background:#E9F7EC; border-radius: 14px 14px 4px 14px; }}
.bubble-name {{ font-size:.78rem; color:{MUTED}; font-weight:600; }}
.kpi {{ background:#fff; border-radius:16px; padding:16px 18px; border:1px solid #EEF0F4;
        box-shadow: 0 6px 24px rgba(16,24,40,.05); }}
.kpi .k-label {{ color:{MUTED}; font-size:.82rem; font-weight:600; }}
.kpi .k-value {{ color:{TEXT}; font-size:1.9rem; font-weight:800; letter-spacing:-0.03em; }}
.kpi .k-sub {{ color:{MUTED}; font-size:.78rem; }}
.chip {{ display:inline-block; background:#F2F4F7; border-radius:999px; padding:4px 11px; margin:3px 4px 3px 0;
         font-size:.8rem; color:{TEXT}; }}
.chip b {{ color:{PRIMARY}; }}
.brand {{ display:flex; align-items:center; gap:10px; font-weight:800; font-size:1.15rem; color:{TEXT}; margin-bottom: 8px; }}
.brand-logo {{ width:34px; height:34px; border-radius:10px; background: linear-gradient(135deg,#1570C9,#59A8F0);
               display:flex; align-items:center; justify-content:center; color:#fff; font-size:1rem; }}
.muted {{ color:{MUTED}; font-size:.85rem; }}
</style>
"""


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def kpi(label: str, value, sub: str = "") -> str:
    return f'<div class="kpi"><div class="k-label">{esc(label)}</div><div class="k-value">{esc(value)}</div><div class="k-sub">{esc(sub)}</div></div>'


def chip(label: str, value) -> str:
    return f'<span class="chip">{esc(label)} <b>{esc(value)}</b></span>'


def live_row(label: str, value: str, level: str = "gray") -> str:
    return f'<div class="live-row"><span>{esc(label)}</span><span class="badge {level}">{esc(value)}</span></div>'
