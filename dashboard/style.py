"""Shared visual identity: palette, CSS injection, header banner, badges,
review cards, and schedule-grid rendering.

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
RED = "#B23B3B"
RED_BG = "#FCE4E4"
STAR = "#F2A900"

# Pixels per 30-minute slot in the schedule-builder's weekly calendar grid.
SCHED_ROW_PX = 48

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
    "danger": (RED, RED_BG),
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


def stars_html(value, max_stars: int = 5) -> str:
    """Render a 1-5 rating as filled/empty stars. NaN-safe."""
    if value is None or value != value:
        return "<span style='color:#999; font-size:0.85rem;'>No rating</span>"
    n = max(0, min(max_stars, round(value)))
    filled = "★" * n
    empty = "☆" * (max_stars - n)
    return (
        f"<span style='letter-spacing:1px;'>"
        f"<span style='color:{STAR};'>{filled}</span>"
        f"<span style='color:#D8DEE6;'>{empty}</span></span>"
    )


def rating_chip(label: str, value, invert: bool = False) -> str:
    """Small colored pill for a 1-5 review sub-rating.

    invert=True means a *higher* raw value should read as worse (used for
    difficulty, where 5 = very hard), so the color scale flips.
    """
    if value is None or value != value:
        return badge(f"{label}: —", "neutral")
    v = (6 - value) if invert else value
    kind = "success" if v >= 4 else "warning" if v >= 3 else "danger"
    return badge(f"{label}: {value:g}", kind)


def render_review_card(r, show_course: bool = True) -> str:
    """One review as a styled card. `r` is a pandas Series/row with the
    reviews table's columns (raw_class, date, comment, clarity_rating,
    difficulty_rating, helpful_rating, is_online, is_for_credit)."""
    date_str = str(r["date"]).split(" ")[0] if r.get("date") else ""
    course_html = (
        f"<span class='review-course'>{r['raw_class'] or 'Course not specified'}</span>"
        if show_course else ""
    )
    comment = r.get("comment")
    comment_html = comment if comment else "<span class='review-empty'>(no comment text)</span>"

    chips = (
        rating_chip("Clarity", r.get("clarity_rating"))
        + " " + rating_chip("Difficulty", r.get("difficulty_rating"), invert=True)
        + " " + rating_chip("Helpful", r.get("helpful_rating"))
    )
    tags = ""
    if r.get("is_online"):
        tags += badge("Online", "neutral") + " "
    if r.get("is_for_credit"):
        tags += badge("For credit", "neutral") + " "

    return f"""
    <div class='review-card'>
        <div class='review-card-head'>
            <div>{course_html}</div>
            <div>{stars_html(r.get('clarity_rating'))}</div>
        </div>
        <div class='review-card-body'>{comment_html}</div>
        <div class='review-card-foot'>
            <div>{chips} {tags}</div>
            <div class='review-date'>{date_str}</div>
        </div>
    </div>
    """


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
            box-shadow: 0 1px 3px rgba(0,33,69,0.06);
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

        /* Bordered st.container(border=True) cards -- professor rows,
           review cards' outer wrapper, etc. */
        [data-testid="stVerticalBlockBorderWrapper"] {{
            border-radius: 12px !important;
            border-color: #DCE4EE !important;
            transition: box-shadow 0.15s ease, border-color 0.15s ease;
        }}
        [data-testid="stVerticalBlockBorderWrapper"]:hover {{
            box-shadow: 0 2px 10px rgba(0,33,69,0.08);
            border-color: {NAVY_SOFT} !important;
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

        /* Primary buttons / link-buttons: solid filled CTA. */
        .stButton button[data-testid="baseButton-primary"],
        .stLinkButton a {{
            background: {BLUE};
            color: white;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            box-shadow: 0 1px 2px rgba(0,33,69,0.15);
        }}
        .stButton button[data-testid="baseButton-primary"]:hover,
        .stLinkButton a:hover {{
            background: {NAVY};
            color: white;
        }}

        /* Secondary buttons: minimal, link-like -- used for in-line
           navigation (e.g. a professor's name) and lower-emphasis actions. */
        .stButton button[data-testid="baseButton-secondary"] {{
            background: transparent;
            color: {BLUE};
            border: 1px solid transparent;
            border-radius: 6px;
            font-weight: 600;
            box-shadow: none;
            padding-left: 0.3rem;
        }}
        .stButton button[data-testid="baseButton-secondary"]:hover {{
            color: {NAVY};
            background: {PALE};
            text-decoration: underline;
        }}
        .stButton button[data-testid="baseButton-secondary"]:disabled {{
            color: {GREEN};
            opacity: 0.8;
        }}

        div[data-testid="stTextInput"] input {{
            border-radius: 8px;
        }}

        /* Review cards */
        .review-card {{
            border: 1px solid #DCE4EE;
            border-radius: 12px;
            padding: 0.9rem 1.1rem;
            margin-bottom: 0.7rem;
            background: white;
            transition: box-shadow 0.15s ease;
        }}
        .review-card:hover {{
            box-shadow: 0 2px 10px rgba(0,33,69,0.08);
        }}
        .review-card-head {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 0.45rem;
        }}
        .review-course {{
            font-weight: 700;
            color: {NAVY};
            background: {PALE};
            padding: 2px 10px;
            border-radius: 6px;
            font-size: 0.85rem;
        }}
        .review-card-body {{
            color: #2A2E34;
            line-height: 1.45;
            font-size: 0.93rem;
            margin-bottom: 0.6rem;
        }}
        .review-empty {{
            color: #888;
            font-style: italic;
        }}
        .review-card-foot {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 0.4rem;
        }}
        .review-date {{
            color: {NAVY_SOFT};
            font-size: 0.78rem;
        }}

        /* Schedule weekly calendar grid */
        .sched-cal {{
            margin-top: 0.5rem;
            border: 1px solid #DCE4EE;
            border-radius: 12px;
            overflow: hidden;
            background: white;
        }}
        .sched-cal-grid {{
            display: grid;
            align-items: stretch;
        }}
        .sched-corner {{
            background: {NAVY};
        }}
        .sched-day-head {{
            background: {NAVY};
            color: white;
            font-weight: 700;
            font-size: 0.82rem;
            text-align: center;
            padding: 0.55rem 0.25rem;
            border-left: 1px solid rgba(255,255,255,0.15);
        }}
        .sched-time-col {{
            position: relative;
            border-right: 1px solid #EEF1F6;
        }}
        .sched-hour-label {{
            position: absolute;
            left: 0;
            right: 6px;
            transform: translateY(-50%);
            text-align: right;
            font-size: 0.72rem;
            color: {NAVY_SOFT};
            font-weight: 600;
        }}
        .sched-day-col {{
            position: relative;
            border-left: 1px solid #EEF1F6;
            background-image: repeating-linear-gradient(
                to bottom, #EEF1F6 0, #EEF1F6 1px,
                transparent 1px, transparent {SCHED_ROW_PX * 2}px
            );
        }}
        .sched-event {{
            position: absolute;
            border-radius: 6px;
            padding: 4px 7px;
            overflow: hidden;
            font-size: 0.74rem;
            line-height: 1.3;
            box-shadow: 0 1px 2px rgba(0,33,69,0.12);
        }}
        .sched-event-conflict {{
            z-index: 2;
        }}
        .sched-event-title {{
            font-weight: 700;
            color: {NAVY};
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .sched-event-sub {{
            color: {NAVY_SOFT};
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header(title: str, subtitle: str | None = None) -> None:
    # Built as one unbroken line, not a multi-line template -- a blank line
    # left by an empty subtitle (e.g. the About page, which passes none)
    # terminates CommonMark's raw-HTML-block passthrough early and leaks the
    # rest of this markup as literal text instead of rendering it.
    subtitle_html = f"<div style='color:#BFD3EC; font-size:0.95rem; margin-top:.4rem;'>{subtitle}</div>" if subtitle else ""
    st.markdown(
        f"<div style='background:{NAVY}; border-radius:12px; padding:1.75rem 2rem 1.4rem; "
        f"border-bottom:4px solid {GOLD}; margin-bottom:1.5rem;'>"
        f"<div style='color:white; font-size:2.1rem; font-weight:800; letter-spacing:-0.02em;'>{title}</div>"
        f"{subtitle_html}"
        f"<div style='color:#8FB3DA; font-size:0.76rem; margin-top:.65rem; font-style:italic;'>"
        f"Unofficial student project — not affiliated with or endorsed by UBC."
        f"</div></div>",
        unsafe_allow_html=True,
    )
