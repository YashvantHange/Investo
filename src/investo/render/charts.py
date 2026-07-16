"""Inline SVG exhibits, hand-written — no chart library, no JS, no external assets.

Every chart is a pure function returning a :class:`Chart`, so the renderer only *places*
exhibits; it never composes one out of strings. That is what keeps the caption and the source
line attached to the figure they describe instead of depending on somebody remembering to type
them at each call site.

House rules, applied throughout (see the project's dataviz guidance):

- **Colour carries one job.** Identity is a single accent (the subject) against de-emphasised
  ink (its peers) — an emphasis chart, not a categorical palette, so no eight-hue cycling and no
  colourblind hazard. Polarity uses a validated diverging pair with a neutral midpoint. Nominal
  categories get *one* colour: shading score buckets darker-where-bigger would double-encode bar
  length as hue and burn the only free channel on information the bar already shows.
- **Text never wears the data colour.** Marks carry the accent; labels, values and ticks stay in
  text tokens.
- **Label selectively.** A number on every mark goes unread; values live in the adjacent table.
- **Thin marks, hairline grid, no borders around marks.** Separation is a 2px surface gap and a
  2px surface ring, never a stroke.
- Colours resolve to CSS custom properties, so light/dark/print are decided once in ``css.py``
  rather than baked into every path.

Accessibility: each figure is ``role="img"`` with a ``<title>``/``<desc>``, and marks carry a
``<title>`` so a browser shows a native tooltip with no script. Nothing here is ever the *only*
way to read a value — every exhibit sits beside the table it summarises.
"""

from __future__ import annotations

from dataclasses import dataclass

from .fmt import esc

# Geometry, in user units. The viewBox scales; these are ratios, not pixels.
_ROW_H = 24
_BAR_H = 11  # <= 24px cap, and thin enough to read as data rather than decoration
_GAP = 2  # the surface gap that separates touching marks
_RADIUS = 3  # rounded data-end
_W = 720


@dataclass(frozen=True)
class Chart:
    """A figure plus the words that make it honest.

    ``caption`` says what the reader is looking at; ``source`` says where it came from and how
    much to trust it. They travel with the SVG because an exhibit without its provenance is how
    a curated estimate gets read as a measurement.
    """

    title: str
    svg: str
    caption: str = ""
    source: str = ""


# --------------------------------------------------------------------------------------
# Primitives — every chart builds from these, so the specs live in one place
# --------------------------------------------------------------------------------------
def draw_text(x: float, y: float, text: str, *, cls: str = "vt", anchor: str = "start") -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" text-anchor="{anchor}">'
            f'{esc(text)}</text>')


def draw_bar(x: float, y: float, w: float, h: float, *, cls: str = "vbar",
             tip: str = "", radius: float = _RADIUS) -> str:
    """A bar with a rounded data-end. Width is clamped so a zero value still shows a sliver."""
    w = max(0.0, w)
    r = min(radius, w / 2) if w > 0 else 0
    title = f"<title>{esc(tip)}</title>" if tip else ""
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'rx="{r:.1f}" class="{cls}">{title}</rect>')


def draw_track(x: float, y: float, w: float, h: float) -> str:
    """The unfilled remainder behind a bar — a lighter step of the same ramp, not a border."""
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'rx="{h / 2:.1f}" class="vtrack"/>')


def draw_grid(x1: float, y1: float, x2: float, y2: float) -> str:
    """A hairline, solid and recessive. Never dashed — dashing reads as a threshold."""
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" class="vgrid"/>'


def draw_axis(x1: float, y1: float, x2: float, y2: float) -> str:
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" class="vaxis"/>'


def draw_dot(cx: float, cy: float, r: float = 4.5, *, cls: str = "vdot", tip: str = "") -> str:
    """A marker with a surface ring, so it stays legible where marks overlap."""
    title = f"<title>{esc(tip)}</title>" if tip else ""
    return f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" class="{cls}">{title}</circle>'


def _svg(view_w: float, view_h: float, body: str, *, title: str, desc: str) -> str:
    """Wrap marks in an accessible, self-contained, responsive figure."""
    return (
        f'<svg viewBox="0 0 {view_w:.0f} {view_h:.0f}" class="viz" role="img" '
        f'preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">'
        f'<title>{esc(title)}</title><desc>{esc(desc)}</desc>{body}</svg>'
    )


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


# --------------------------------------------------------------------------------------
# Exhibits
# --------------------------------------------------------------------------------------
def hbar_chart(
    rows: list[tuple[str, float, str]],
    *,
    title: str,
    desc: str = "",
    label_w: float = 190,
    value_w: float = 96,
) -> str:
    """Horizontal bars for nominal categories: (label, 0..1 fill, value text).

    One colour for every bar. These categories have no natural order, so a value-ramp would
    restate the bar length as hue and say nothing new.
    """
    if not rows:
        return ""
    h = len(rows) * _ROW_H + 8
    track_x = label_w
    track_w = _W - label_w - value_w
    parts: list[str] = []
    for i, (label, frac, value) in enumerate(rows):
        y = i * _ROW_H + 4
        mid = y + _ROW_H / 2 - 1
        bar_y = y + (_ROW_H - _BAR_H) / 2 - 1
        parts.append(draw_text(0, mid + 3.5, label))
        parts.append(draw_track(track_x, bar_y, track_w, _BAR_H))
        parts.append(draw_bar(track_x, bar_y, track_w * _clamp01(frac), _BAR_H,
                              tip=f"{label}: {value}"))
        parts.append(draw_text(_W, mid + 3.5, value, cls="vt vnum", anchor="end"))
    return _svg(_W, h, "".join(parts), title=title, desc=desc or title)


def diverging_bars(
    rows: list[tuple[str, float, str, str]],
    *,
    title: str,
    desc: str = "",
    label_w: float = 150,
    value_w: float = 150,
) -> str:
    """Bars diverging from a neutral midpoint: (label, 0..1 percentile, value text, tooltip).

    Percentile against a peer median is *polarity*, not magnitude — 0.5 means "the same as the
    industry", and the reader's question is which side of it the company sits on. So the mark
    grows from the midpoint, with a neutral gray rule at the middle and the validated
    blue/red pair on the arms.
    """
    if not rows:
        return ""
    h = len(rows) * _ROW_H + 20
    plot_x = label_w
    plot_w = _W - label_w - value_w
    mid_x = plot_x + plot_w / 2
    parts: list[str] = [draw_grid(mid_x, 0, mid_x, h - 16)]
    for i, (label, pct, value, tip) in enumerate(rows):
        y = i * _ROW_H + 4
        mid = y + _ROW_H / 2 - 1
        bar_y = y + (_ROW_H - _BAR_H) / 2 - 1
        offset = (_clamp01(pct) - 0.5) * plot_w  # signed distance from the median
        parts.append(draw_text(0, mid + 3.5, label))
        if offset >= 0:
            parts.append(draw_bar(mid_x + _GAP / 2, bar_y, offset - _GAP / 2, _BAR_H,
                                  cls="vbar pos", tip=tip))
        else:
            parts.append(draw_bar(mid_x + offset, bar_y, -offset - _GAP / 2, _BAR_H,
                                  cls="vbar neg", tip=tip))
        parts.append(draw_text(_W, mid + 3.5, value, cls="vt vnum", anchor="end"))
    parts.append(draw_text(mid_x, h - 4, "industry median", cls="vt vmuted", anchor="middle"))
    return _svg(_W, h, "".join(parts), title=title, desc=desc or title)


def scatter(
    points: list[tuple[str, float, float, bool]],
    *,
    title: str,
    x_label: str,
    y_label: str,
    desc: str = "",
) -> str:
    """Peers positioned on two measures: (label, x, y, is_subject).

    An emphasis chart, deliberately: the question is where *one* company sits among its cohort,
    so the subject carries the accent and everyone else recedes to muted ink. That also means no
    categorical palette — five hues on five dots would fail colourblind separation to say
    something the position already says. Every dot is direct-labelled, so identity never depends
    on colour.
    """
    real = [p for p in points if p[1] is not None and p[2] is not None]
    if len(real) < 2:
        return ""
    h = 300.0
    pad_l, pad_r, pad_t, pad_b = 54.0, 90.0, 16.0, 40.0
    xs = [p[1] for p in real]
    ys = [p[2] for p in real]
    x_lo, x_hi = min(xs), max(xs)
    y_lo, y_hi = min(ys), max(ys)
    # Pad a degenerate axis so a single-valued set doesn't divide by zero or hug an edge.
    x_pad = (x_hi - x_lo) * 0.18 or (abs(x_hi) * 0.2 or 0.02)
    y_pad = (y_hi - y_lo) * 0.18 or (abs(y_hi) * 0.2 or 0.02)
    x_lo, x_hi = x_lo - x_pad, x_hi + x_pad
    y_lo, y_hi = y_lo - y_pad, y_hi + y_pad

    def px(v: float) -> float:
        return pad_l + (v - x_lo) / (x_hi - x_lo) * (_W - pad_l - pad_r)

    def py(v: float) -> float:
        return h - pad_b - (v - y_lo) / (y_hi - y_lo) * (h - pad_t - pad_b)

    parts: list[str] = []
    # Recessive frame: two hairlines, no box.
    parts.append(draw_axis(pad_l, h - pad_b, _W - pad_r, h - pad_b))
    parts.append(draw_axis(pad_l, pad_t, pad_l, h - pad_b))
    for frac in (0.25, 0.5, 0.75):
        gy = pad_t + (h - pad_t - pad_b) * frac
        parts.append(draw_grid(pad_l, gy, _W - pad_r, gy))
    # Ticks carry the values the dots aren't labelled with.
    for v, anchor in ((x_lo, "start"), (x_hi, "end")):
        parts.append(draw_text(px(v), h - pad_b + 16, f"{v:.0%}", cls="vt vtick", anchor=anchor))
    for v in (y_lo, y_hi):
        parts.append(draw_text(pad_l - 8, py(v) + 3.5, f"{v:.0%}", cls="vt vtick", anchor="end"))
    parts.append(draw_text((_W - pad_r + pad_l) / 2, h - 6, x_label, cls="vt vmuted",
                           anchor="middle"))
    parts.append(f'<text x="14" y="{(h - pad_b + pad_t) / 2:.1f}" class="vt vmuted" '
                 f'text-anchor="middle" transform="rotate(-90 14 '
                 f'{(h - pad_b + pad_t) / 2:.1f})">{esc(y_label)}</text>')

    for label, x, y, is_subject in real:
        cx, cy = px(x), py(y)
        tip = f"{label}: {x:.1%} {x_label.lower()}, {y:.1%} {y_label.lower()}"
        parts.append(draw_dot(cx, cy, 5.5 if is_subject else 4.5,
                              cls="vdot subject" if is_subject else "vdot peer", tip=tip))
        parts.append(draw_text(cx + 9, cy + 3.5,
                               label, cls="vt vlabel" + (" strong" if is_subject else "")))
    return _svg(_W, h, "".join(parts), title=title, desc=desc or title)


def sparkline(values: list[float | None], *, width: float = 120, height: float = 28,
              tip: str = "") -> str:
    """A 2px trend line with an end marker. Inline, unlabelled: the table carries the numbers."""
    real = [(i, v) for i, v in enumerate(values) if v is not None]
    if len(real) < 2:
        return ""
    lo = min(v for _, v in real)
    hi = max(v for _, v in real)
    span = (hi - lo) or (abs(hi) or 1.0)
    pad = 4.0
    n = len(values) - 1 or 1

    def px(i: int) -> float:
        return pad + i / n * (width - 2 * pad)

    def py(v: float) -> float:
        return height - pad - (v - lo) / span * (height - 2 * pad)

    pts = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, v in real)
    last_i, last_v = real[-1]
    title = f"<title>{esc(tip)}</title>" if tip else ""
    body = (f'<polyline points="{pts}" class="vline"/>'
            f'{draw_dot(px(last_i), py(last_v), 3.2, cls="vdot subject")}{title}')
    return (f'<svg viewBox="0 0 {width:.0f} {height:.0f}" class="viz spark" role="img" '
            f'xmlns="http://www.w3.org/2000/svg"><title>{esc(tip or "trend")}</title>'
            f'{body}</svg>')


def value_vs_price(
    intrinsic: float | None,
    price: float | None,
    *,
    currency_fmt,
    title: str = "Intrinsic value vs market price",
) -> str:
    """Two bars on one scale: what the DCF says it's worth, and what it costs.

    One axis, deliberately — the whole point is that these two numbers are comparable, which is
    exactly the claim a second scale would fabricate.
    """
    if intrinsic is None or price is None or intrinsic <= 0 or price <= 0:
        return ""
    h = 2 * _ROW_H + 26
    label_w, value_w = 150.0, 110.0
    track_w = _W - label_w - value_w
    hi = max(intrinsic, price)
    parts: list[str] = []
    for i, (label, val, cls) in enumerate((
        ("DCF intrinsic value", intrinsic, "vbar pos" if intrinsic >= price else "vbar neg"),
        ("Market price", price, "vbar muted"),
    )):
        y = i * _ROW_H + 6
        mid = y + _ROW_H / 2 - 1
        bar_y = y + (_ROW_H - _BAR_H) / 2 - 1
        parts.append(draw_text(0, mid + 3.5, label))
        parts.append(draw_bar(label_w, bar_y, track_w * (val / hi), _BAR_H, cls=cls,
                              tip=f"{label}: {currency_fmt(val)}"))
        parts.append(draw_text(_W, mid + 3.5, currency_fmt(val), cls="vt vnum", anchor="end"))
    gap = (intrinsic - price) / price
    note = f"{gap:+.0%} vs price — {'margin of safety' if gap > 0 else 'premium to value'}"
    parts.append(draw_text(label_w, h - 6, note, cls="vt vmuted"))
    return _svg(_W, h, "".join(parts), title=title, desc=note)
