"""Shared visual identity: palette, CSS injection, header banner, badges.

Not an official UBC product -- colors are drawn from UBC's own public web
palette (ubc.ca) purely for a consistent, "built for this campus" feel.
No crest/wordmark/logo is used anywhere, intentionally.
"""

import streamlit as st

NAVY = "#002145"
NAVY_SOFT = "#5C7A9F"
BLUE = "#0055B7"
GOLD = "#FFC72C"
PALE = "#EFF3F8"

GREEN = "#1B7A43"
GREEN_BG = "#E3F3E9"
GREY = "#5B6472"
GREY_BG = "#E9ECEF"
AMBER = "#8A6100"
AMBER_BG = "#FFF1CC"

MATCH_LABEL_KIND = {
    "exact": "success",
    "no_rmp": "neutral",
    "unverified": "warning",
    "ambiguous_within_rmp": "warning",
}
MATCH_LABEL_TEXT = {
    "exact": "Matched to RMP",
    "no_rmp": "No RMP page",
    "unverified": "Unverified match",
    "ambiguous_within_rmp": "Ambiguous match",
}

_BADGE_COLORS = {
    "success": (GREEN, GREEN_BG),
    "neutral": (GREY, GREY_BG),
    "warning": (AMBER, AMBER_BG),
}


def badge(text: str, kind: str = "neutral") -> str:
    fg, bg = _BADGE_COLORS.get(kind, _BADGE_COLORS["neutral"])
    return (
        f"<span style='display:inline-block; background:{bg}; color:{fg}; "
        f"font-size:0.78rem; font-weight:600; padding:2px 10px; "
        f"border-radius:999px; white-space:nowrap;'>{text}</span>"
    )


def match_label_badge(match_label: str) -> str:
    kind = MATCH_LABEL_KIND.get(match_label, "neutral")
    text = MATCH_LABEL_TEXT.get(match_label, match_label or "Unknown")
    return badge(text, kind)


def inject_css() -> None:
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

        html, body, [class*="css"] {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }}

        h1, h2, h3, h4 {{
            font-family: 'Inter', sans-serif;
            letter-spacing: -0.01em;
            color: {NAVY};
        }}

        [data-testid="stSidebarNav"] {{
            background: {NAVY};
            padding-top: 1rem;
            border-radius: 0 10px 10px 0;
        }}
        [data-testid="stSidebarNav"] a, [data-testid="stSidebarNav"] a span {{
            color: #CBDCF2 !important;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            font-size: 0.82rem;
        }}
        [data-testid="stSidebarNav"] a:hover, [data-testid="stSidebarNav"] a:hover span {{
            color: {GOLD} !important;
        }}
        [data-testid="stSidebarNav"] li div[aria-current="page"] a,
        [data-testid="stSidebarNav"] li div[aria-current="page"] a span {{
            color: {GOLD} !important;
        }}

        [data-testid="stMetric"] {{
            background: {PALE};
            border: 1px solid #DCE4EE;
            border-radius: 10px;
            padding: 0.9rem 1rem 0.6rem;
        }}
        [data-testid="stMetricValue"] {{
            color: {NAVY};
        }}
        [data-testid="stMetricLabel"] {{
            color: {NAVY_SOFT};
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.72rem;
            letter-spacing: 0.04em;
        }}

        [data-testid="stDataFrame"] {{
            border: 1px solid #DCE4EE;
            border-radius: 10px;
            overflow: hidden;
        }}

        .stTabs [data-baseweb="tab-list"] {{
            gap: 0.5rem;
        }}
        .stTabs [data-baseweb="tab"] {{
            color: {NAVY_SOFT};
            font-weight: 600;
        }}
        .stTabs [aria-selected="true"] {{
            color: {NAVY} !important;
        }}
        .stTabs [data-baseweb="tab-highlight"] {{
            background-color: {GOLD} !important;
            height: 3px;
        }}

        .stButton button, .stLinkButton a {{
            background: {BLUE};
            color: white;
            border: none;
            border-radius: 8px;
            font-weight: 600;
        }}
        .stButton button:hover, .stLinkButton a:hover {{
            background: {NAVY};
            color: white;
        }}

        div[data-testid="stTextInput"] input {{
            border-radius: 8px;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header(title: str, subtitle: str | None = None) -> None:
    subtitle_html = f"<div style='color:#BFD3EC; font-size:0.95rem; margin-top:.4rem;'>{subtitle}</div>" if subtitle else ""
    st.markdown(
        f"""
        <div style='background:{NAVY}; border-radius:12px; padding:1.75rem 2rem 1.4rem;
                    border-bottom:4px solid {GOLD}; margin-bottom:1.5rem;'>
            <div style='color:white; font-size:2.1rem; font-weight:800; letter-spacing:-0.02em;'>{title}</div>
            {subtitle_html}
            <div style='color:#8FB3DA; font-size:0.76rem; margin-top:.65rem; font-style:italic;'>
                Unofficial student project — not affiliated with or endorsed by UBC.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
