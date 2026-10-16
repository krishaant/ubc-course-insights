"""Schedule-builder helpers: day/time parsing, conflict detection, and the
weekly grid renderer. Session-only (no accounts exist in this app) -- these
are pure functions over the entries dict kept in st.session_state; nothing
here touches the database.
"""

import ast

from dashboard import style

DAY_ORDER = ["m", "t", "w", "th", "f", "s", "su"]
DAY_LABEL = {"m": "Mon", "t": "Tue", "w": "Wed", "th": "Thu", "f": "Fri", "s": "Sat", "su": "Sun"}

_PALETTE = [style.BLUE, style.GREEN, "#B7791F", style.NAVY_SOFT, "#7C3AED", "#0E7490"]


def color_for(key: str) -> str:
    return _PALETTE[hash(key) % len(_PALETTE)]


def parse_days(raw) -> list[str]:
    if not isinstance(raw, str) or not raw.strip():
        return []
    try:
        days = ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return []
    return [d for d in days if d in DAY_LABEL]


def format_time(seconds) -> str:
    if seconds is None or seconds != seconds:
        return "—"
    h, m = divmod(int(seconds), 3600)
    period = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{m // 60:02d} {period}"


def find_conflicts(entries: list[dict]) -> list[tuple[dict, dict, list[str]]]:
    """Pairwise time-overlap check across entries that share at least one day."""
    conflicts = []
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            a, b = entries[i], entries[j]
            shared_days = sorted(set(a["days"]) & set(b["days"]), key=DAY_ORDER.index)
            if not shared_days:
                continue
            if a["start"] < b["end"] and b["start"] < a["end"]:
                conflicts.append((a, b, shared_days))
    return conflicts


def _layout_day(day_entries: list[dict]) -> dict:
    """Greedy overlap clustering for one day's entries -> {key: (col_index,
    col_count)}, so overlapping classes sit side by side within their
    cluster's width instead of stacking on top of each other."""
    ordered = sorted(day_entries, key=lambda e: e["start"])
    positions = {}
    clusters, cluster, cluster_end = [], [], None
    for e in ordered:
        if cluster and e["start"] < cluster_end:
            cluster.append(e)
            cluster_end = max(cluster_end, e["end"])
        else:
            if cluster:
                clusters.append(cluster)
            cluster, cluster_end = [e], e["end"]
    if cluster:
        clusters.append(cluster)
    for c in clusters:
        n = len(c)
        for i, e in enumerate(c):
            positions[e["key"]] = (i, n)
    return positions


def render_grid(entries: list[dict]) -> str:
    """Render an actual weekly-calendar timetable: one continuous colored
    block per section positioned by its real start/end time, with same-day
    overlaps placed side by side -- not a table with a repeated label per
    half-hour row. Entries with no fixed days are skipped (nothing to place)."""
    row_px = style.SCHED_ROW_PX
    timed = [e for e in entries if e["days"]]
    active_days = sorted({d for e in timed for d in e["days"]}, key=DAY_ORDER.index) or ["m", "t", "w", "th", "f"]

    if not timed:
        start_slot, end_slot = 8 * 3600, 18 * 3600
    else:
        raw_start = min(e["start"] for e in timed)
        raw_end = max(e["end"] for e in timed)
        start_slot = min(int(raw_start // 1800) * 1800, 8 * 3600)
        end_slot = max(int(-(-raw_end // 1800)) * 1800, 18 * 3600)

    total_height = int((end_slot - start_slot) / 1800) * row_px

    labels = []
    t = start_slot if start_slot % 3600 == 0 else start_slot + (3600 - start_slot % 3600)
    while t <= end_slot:
        top = (t - start_slot) / 1800 * row_px
        labels.append(f"<div class='sched-hour-label' style='top:{top}px;'>{format_time(t)}</div>")
        t += 3600
    time_col = f"<div class='sched-time-col' style='height:{total_height}px;'>{''.join(labels)}</div>"

    day_cols = []
    for day in active_days:
        day_entries = [e for e in timed if day in e["days"]]
        positions = _layout_day(day_entries)
        blocks = []
        for e in day_entries:
            col_i, col_n = positions[e["key"]]
            top = (e["start"] - start_slot) / 1800 * row_px
            height = max((e["end"] - e["start"]) / 1800 * row_px, row_px * 0.5)
            width_pct = 100 / col_n
            left_pct = col_i * width_pct
            conflict = col_n > 1
            color = style.RED if conflict else color_for(e["key"])
            bg = style.RED_BG if conflict else f"{color}1F"
            sub_lines = [f"{format_time(e['start'])}–{format_time(e['end'])}"]
            if e["instructor"]:
                sub_lines.append(e["instructor"])
            subs = "".join(f"<div class='sched-event-sub'>{s}</div>" for s in sub_lines)
            blocks.append(
                f"<div class='sched-event{' sched-event-conflict' if conflict else ''}' "
                f"style='top:{top}px; height:{height}px; left:{left_pct}%; "
                f"width:calc({width_pct}% - 4px); background:{bg}; border-left:3px solid {color};'>"
                f"<div class='sched-event-title'>{e['course_key']} {e['section']}</div>{subs}</div>"
            )
        day_cols.append(f"<div class='sched-day-col' style='height:{total_height}px;'>{''.join(blocks)}</div>")

    header_cells = "".join(f"<div class='sched-day-head'>{DAY_LABEL[d]}</div>" for d in active_days)
    grid_style = f"grid-template-columns: 56px repeat({len(active_days)}, 1fr);"
    return (
        "<div class='sched-cal'>"
        f"<div class='sched-cal-grid' style='{grid_style}'>"
        f"<div class='sched-corner'></div>{header_cells}"
        f"{time_col}{''.join(day_cols)}"
        "</div></div>"
    )
