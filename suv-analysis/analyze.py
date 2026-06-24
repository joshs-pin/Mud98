#!/usr/bin/env python3
"""
SUV off-road suitability analysis -- "data at rest" edition.

No database, no third-party libraries. The dataset lives in a flat CSV
(data/suvs.csv) and this script performs the sorting, scoring, and
relationship analysis using only the Python standard library.

Goal: help identify the most appropriate starter body for an off-road
project car, drawn from used SUVs of 1990-2015.

Usage examples
--------------
    python3 analyze.py                       # ranked recommendation, default weights
    python3 analyze.py --top 10              # show only the top 10
    python3 analyze.py --min-year 1995 --max-year 2010
    python3 analyze.py --sort ground_clearance_mm --desc
    python3 analyze.py --correlations        # Pearson correlations between properties
    python3 analyze.py --weights weights.json
    python3 analyze.py --show-detail "Toyota 4Runner 4th gen"
    python3 analyze.py --csv-out ranking.csv # write the ranked table to CSV

Run `python3 analyze.py --help` for the full option list.
"""

import argparse
import csv
import json
import math
import os
import sys

DATA_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "data", "suvs.csv")

# ---------------------------------------------------------------------------
# Scoring configuration
# ---------------------------------------------------------------------------
# Each property contributes to a composite 0-100 off-road suitability score.
# "direction" controls how a raw value maps to a 0-1 sub-score:
#
#   "higher"  -> more is better (e.g. ground clearance)
#   "lower"   -> less is better (e.g. weight, body width on tight trails)
#   "band"    -> a sweet-spot range is best; values inside the band score 1.0
#                and fall off linearly outside it (e.g. wheelbase)
#
# Weights are relative; they are normalised to sum to 1.0 at runtime, so you
# can use any scale you like in a custom weights.json.
#
# NOTE on torsional rigidity: the rating is a 1-5 engineering judgement
# (see README), not a measured Nm/deg figure. The default treats "stiffer is
# better" (good base for cage/armour builds) but at a low weight. If you value
# axle articulation over stiffness, set its direction to "lower" or drop its
# weight to 0 in a custom weights file.
DEFAULT_CONFIG = {
    "ground_clearance_mm":       {"weight": 0.28, "direction": "higher"},
    "wheelbase_mm":              {"weight": 0.18, "direction": "band",
                                  "band": [2350, 2750]},
    "weight_kg":                 {"weight": 0.14, "direction": "lower"},
    "wheel_track_mm":            {"weight": 0.10, "direction": "higher"},
    "width_mm":                  {"weight": 0.10, "direction": "lower"},
    "torsional_rigidity_rating": {"weight": 0.10, "direction": "higher"},
    "height_mm":                 {"weight": 0.06, "direction": "lower"},
    "length_mm":                 {"weight": 0.04, "direction": "lower"},
}

# Columns that are numeric (everything else is treated as text/metadata).
NUMERIC_COLS = [
    "weight_kg", "wheel_track_mm", "wheelbase_mm", "length_mm", "width_mm",
    "height_mm", "ground_clearance_mm", "torsional_rigidity_rating",
    "year_start", "year_end",
]

# Physical properties compared in the correlation matrix / heatmap, with short
# display labels. Shared by print_correlations() and the PPM heatmap.
CORR_COLS = [
    ("ground_clearance_mm", "clear"),
    ("wheelbase_mm", "wbase"),
    ("weight_kg", "mass"),
    ("wheel_track_mm", "track"),
    ("width_mm", "width"),
    ("height_mm", "hght"),
    ("torsional_rigidity_rating", "rigid"),
]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_data(path):
    """Load the CSV into a list of dicts, coercing numeric columns."""
    if not os.path.exists(path):
        sys.exit("error: data file not found: %s" % path)
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for lineno, raw in enumerate(reader, start=2):
            row = dict(raw)
            for col in NUMERIC_COLS:
                if col not in row:
                    continue
                val = (row[col] or "").strip()
                if val == "":
                    row[col] = None
                    continue
                try:
                    row[col] = float(val)
                except ValueError:
                    sys.exit("error: %s line %d: column '%s' is not numeric: %r"
                             % (path, lineno, col, val))
            rows.append(row)
    if not rows:
        sys.exit("error: no data rows found in %s" % path)
    return rows


def filter_years(rows, min_year, max_year):
    """Keep vehicles whose production span overlaps the requested window."""
    out = []
    for r in rows:
        ys, ye = r.get("year_start"), r.get("year_end")
        if ys is None or ye is None:
            out.append(r)
            continue
        if ye >= min_year and ys <= max_year:
            out.append(r)
    return out


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def _normalise(values, direction, band=None):
    """Map a list of raw values to 0-1 sub-scores per the given direction.

    Missing values (None) map to a neutral 0.5 so a single blank field does
    not unfairly sink or inflate a vehicle's overall score.
    """
    present = [v for v in values if v is not None]
    if not present:
        return [0.5] * len(values)
    lo, hi = min(present), max(present)
    span = hi - lo

    out = []
    for v in values:
        if v is None:
            out.append(0.5)
            continue
        if direction == "band":
            blo, bhi = band
            if blo <= v <= bhi:
                out.append(1.0)
            else:
                # Distance outside the band, scaled by the dataset spread so
                # the penalty is proportionate rather than arbitrary.
                dist = (blo - v) if v < blo else (v - bhi)
                ref = span if span else 1.0
                out.append(max(0.0, 1.0 - dist / ref))
            continue
        if span == 0:
            out.append(1.0)
            continue
        frac = (v - lo) / span
        out.append(frac if direction == "higher" else (1.0 - frac))
    return out


def score(rows, config):
    """Attach a composite 'score' (0-100) and per-property sub-scores to rows.

    Returns the same list, each row gaining:
        row["score"]      -> float 0-100
        row["_sub"][col]  -> float 0-1 contribution before weighting
    """
    # Normalise the weights so they always sum to 1.0.
    total_w = sum(c["weight"] for c in config.values())
    if total_w <= 0:
        sys.exit("error: configured weights sum to zero")

    sub_scores = {}
    for col, cfg in config.items():
        values = [r.get(col) for r in rows]
        sub_scores[col] = _normalise(values, cfg["direction"], cfg.get("band"))

    for i, r in enumerate(rows):
        r["_sub"] = {}
        composite = 0.0
        for col, cfg in config.items():
            s = sub_scores[col][i]
            r["_sub"][col] = s
            composite += (cfg["weight"] / total_w) * s
        r["score"] = round(composite * 100, 1)
    return rows


# ---------------------------------------------------------------------------
# Relationship analysis
# ---------------------------------------------------------------------------
def pearson(xs, ys):
    """Pearson correlation coefficient for paired values (ignoring blanks)."""
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(pairs)
    if n < 3:
        return None
    mx = sum(p[0] for p in pairs) / n
    my = sum(p[1] for p in pairs) / n
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pairs)
    sxx = sum((p[0] - mx) ** 2 for p in pairs)
    syy = sum((p[1] - my) ** 2 for p in pairs)
    if sxx == 0 or syy == 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def correlation_matrix(rows, cols):
    matrix = {}
    for a in cols:
        matrix[a] = {}
        for b in cols:
            matrix[a][b] = pearson([r.get(a) for r in rows],
                                   [r.get(b) for r in rows])
    return matrix


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
def print_ranking(rows, top=None, score_shown=True):
    cols = [
        ("model", "Model", 26, "l"),
        ("year_start", "From", 5, "r"),
        ("ground_clearance_mm", "Clr", 5, "r"),
        ("wheelbase_mm", "WB", 5, "r"),
        ("weight_kg", "Mass", 5, "r"),
        ("width_mm", "Width", 6, "r"),
        ("height_mm", "Hght", 5, "r"),
        ("torsional_rigidity_rating", "Rig", 4, "r"),
    ]
    if score_shown:
        cols.append(("score", "SCORE", 6, "r"))

    def fmt(val, width, align):
        if val is None:
            text = "-"
        elif isinstance(val, float):
            text = ("%g" % val)
        else:
            text = str(val)
        if len(text) > width:
            text = text[:width]
        return text.ljust(width) if align == "l" else text.rjust(width)

    header = "  ".join(fmt(h, w, "l" if a == "l" else "r")
                       for _, h, w, a in cols)
    print(header)
    print("-" * len(header))
    display = rows if top is None else rows[:top]
    for r in display:
        line = "  ".join(fmt(r.get(key), w, a) for key, _, w, a in cols)
        print(line)
    print("\n(Clr=ground clearance mm, WB=wheelbase mm, Mass=kerb kg, "
          "Rig=torsional rigidity rating 1-5)")


def print_detail(rows, model, config):
    match = [r for r in rows if r["model"].lower() == model.lower()]
    if not match:
        partial = [r for r in rows if model.lower() in r["model"].lower()]
        if len(partial) == 1:
            match = partial
        elif len(partial) > 1:
            print("Multiple matches for %r:" % model)
            for r in partial:
                print("  - %s" % r["model"])
            return
        else:
            print("No vehicle matching %r" % model)
            return
    r = match[0]
    total_w = sum(c["weight"] for c in config.values())
    print("=" * 60)
    print(r["model"], "(%s)" % r.get("generation", ""))
    print("=" * 60)
    print("Years:        %g-%g" % (r["year_start"], r["year_end"]))
    print("Construction: %s" % r.get("construction", "-"))
    print("Notes:        %s" % r.get("notes", "-"))
    print("-" * 60)
    print("Composite off-road score: %.1f / 100" % r["score"])
    print("-" * 60)
    print("%-28s %8s %8s %10s" % ("property", "value", "sub", "weighted"))
    for col, cfg in sorted(config.items(),
                           key=lambda kv: -kv[1]["weight"]):
        sub = r["_sub"].get(col, 0.0)
        wpct = cfg["weight"] / total_w
        print("%-28s %8s %8.2f %9.1f%%"
              % (col, _g(r.get(col)), sub, sub * wpct * 100))


def _g(v):
    if v is None:
        return "-"
    if isinstance(v, float):
        return "%g" % v
    return str(v)


def print_correlations(rows):
    cols = [c for c, _ in CORR_COLS]
    short = {
        "ground_clearance_mm": "clear",
        "wheelbase_mm": "wbase",
        "weight_kg": "mass",
        "wheel_track_mm": "track",
        "width_mm": "width",
        "height_mm": "hght",
        "torsional_rigidity_rating": "rigid",
    }
    matrix = correlation_matrix(rows, cols)
    print("Pearson correlation between physical properties")
    print("(+1 = move together, -1 = move oppositely, ~0 = unrelated)\n")
    head = "        " + "".join("%7s" % short[c] for c in cols)
    print(head)
    for a in cols:
        line = "%-8s" % short[a]
        for b in cols:
            v = matrix[a][b]
            line += "%7s" % ("  -  " if v is None else "%+.2f" % v)
        print(line)
    print("\nNotable relationships:")
    seen = set()
    flat = []
    for a in cols:
        for b in cols:
            if a >= b:
                continue
            v = matrix[a][b]
            if v is not None:
                flat.append((abs(v), v, a, b))
    flat.sort(reverse=True)
    for _, v, a, b in flat[:5]:
        kind = "strong" if abs(v) > 0.7 else "moderate" if abs(v) > 0.4 else "weak"
        sign = "positive" if v > 0 else "negative"
        print("  %-26s vs %-22s r=%+.2f (%s %s)"
              % (a, b, v, kind, sign))


def write_csv(rows, path, config):
    cols = ["rank", "model", "year_start", "year_end", "construction",
            "weight_kg", "wheel_track_mm", "wheelbase_mm", "length_mm",
            "width_mm", "height_mm", "ground_clearance_mm",
            "torsional_rigidity_rating", "score"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for i, r in enumerate(rows, start=1):
            w.writerow([i] + [_g(r.get(c)) if c != "rank" else i
                              for c in cols[1:]])
    print("wrote ranked table -> %s" % path)


# ---------------------------------------------------------------------------
# PPM visualisation (stdlib only -- no image libraries)
# ---------------------------------------------------------------------------
# PPM (Netpbm portable pixmap) is the image-world equivalent of our CSV: just
# files, no library required. We render charts by writing a binary (P6) header
# and raw RGB bytes by hand. View a .ppm with any image tool, or convert with
# e.g. `pnmtopng score_bars.ppm > score_bars.png`.

# Compact 3x5 bitmap font, just the glyphs we need for axis/rank labels.
_FONT = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "010", "010", "010"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
    "+": ("000", "010", "111", "010", "000"),
    "-": ("000", "000", "111", "000", "000"),
    ".": ("000", "000", "000", "000", "010"),
}


class _Image:
    """Minimal RGB framebuffer that writes a binary (P6) PPM. No dependencies."""

    def __init__(self, w, h, bg=(255, 255, 255)):
        self.w, self.h = w, h
        self.px = bytearray(bg * (w * h))

    def rect(self, x, y, w, h, c):
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.w, x + w), min(self.h, y + h)
        for yy in range(y0, y1):
            base = (yy * self.w + x0) * 3
            for xx in range(x1 - x0):
                i = base + xx * 3
                self.px[i], self.px[i + 1], self.px[i + 2] = c

    def write_ppm(self, path):
        with open(path, "wb") as fh:
            fh.write(b"P6\n%d %d\n255\n" % (self.w, self.h))
            fh.write(bytes(self.px))


def _glyph(img, ch, x, y, scale, color):
    rows = _FONT.get(ch)
    if not rows:
        return
    for ry, row in enumerate(rows):
        for cx, bit in enumerate(row):
            if bit == "1":
                img.rect(x + cx * scale, y + ry * scale, scale, scale, color)


def _text(img, s, x, y, scale, color):
    cur = x
    for ch in str(s):
        _glyph(img, ch, cur, y, scale, color)
        cur += 4 * scale  # 3px glyph + 1px gap, scaled
    return cur - x


def _lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _corr_color(r):
    """Diverging colormap: red=+1, pale=0, blue=-1; grey for missing."""
    if r is None:
        return (180, 180, 180)
    t = min(1.0, abs(r))
    return _lerp((245, 245, 245), (200, 40, 40) if r >= 0 else (40, 70, 200), t)


def _score_color(s, lo, hi):
    """Sequential red->yellow->green by score within the shown range."""
    u = 0.0 if hi == lo else (s - lo) / (hi - lo)
    red, yellow, green = (200, 60, 50), (225, 200, 60), (50, 165, 75)
    return _lerp(red, yellow, u / 0.5) if u < 0.5 \
        else _lerp(yellow, green, (u - 0.5) / 0.5)


def build_heatmap_ppm(rows, path):
    """Correlation heatmap of the physical properties -> PPM image."""
    cols = [c for c, _ in CORR_COLS]
    n = len(cols)
    matrix = correlation_matrix(rows, cols)
    cell, pad_l, pad_t = 54, 34, 34
    bar_gap, bar_w, pad_r = 16, 22, 60
    grid = n * cell
    W = pad_l + grid + bar_gap + bar_w + pad_r
    H = pad_t + grid + 12
    img = _Image(W, H)

    # axis index labels (1..n) along top and left
    for i in range(n):
        _text(img, i + 1, pad_l + i * cell + cell // 2 - 4, pad_t - 16, 3, (40, 40, 40))
        _text(img, i + 1, pad_l - 18, pad_t + i * cell + cell // 2 - 7, 3, (40, 40, 40))

    # cells
    for ri, a in enumerate(cols):
        for ci, b in enumerate(cols):
            img.rect(pad_l + ci * cell, pad_t + ri * cell, cell, cell,
                     _corr_color(matrix[a][b]))
    # white grid lines
    for k in range(n + 1):
        img.rect(pad_l + k * cell, pad_t, 1, grid + 1, (255, 255, 255))
        img.rect(pad_l, pad_t + k * cell, grid + 1, 1, (255, 255, 255))

    # vertical colour-scale bar (+1 top .. -1 bottom)
    bx = pad_l + grid + bar_gap
    for j in range(grid):
        img.rect(bx, pad_t + j, bar_w, 1, _corr_color(1.0 - 2.0 * (j / (grid - 1))))
    _text(img, "+1", bx + bar_w + 4, pad_t - 2, 3, (40, 40, 40))
    _text(img, "0", bx + bar_w + 4, pad_t + grid // 2 - 7, 3, (40, 40, 40))
    _text(img, "-1", bx + bar_w + 4, pad_t + grid - 14, 3, (40, 40, 40))

    img.write_ppm(path)
    print("wrote correlation heatmap -> %s  (%dx%d PPM)" % (path, W, H))
    print("  axis index legend:")
    for i, (c, lbl) in enumerate(CORR_COLS):
        print("    %d = %-26s (%s)" % (i + 1, c, lbl))
    print("  colour: red=+1 (move together), blue=-1 (opposite), pale=~0")


def build_barchart_ppm(rows, path, top=None):
    """Horizontal bar chart of the off-road score (0..100) -> PPM image."""
    ranked = sorted(rows, key=lambda r: r["score"], reverse=True)
    if top:
        ranked = ranked[:top]
    n = len(ranked)
    pitch, barh = 18, 13
    pad_l, pad_t, pad_b, plot_w, pad_r = 30, 14, 10, 300, 26
    W = pad_l + plot_w + pad_r
    H = pad_t + n * pitch + pad_b
    img = _Image(W, H)
    scores = [r["score"] for r in ranked]
    lo, hi = min(scores), max(scores)

    # faint vertical gridlines at 0/25/50/75/100 points of score
    for g in (0, 25, 50, 75, 100):
        img.rect(pad_l + int(g / 100 * plot_w), pad_t, 1, n * pitch, (224, 224, 224))
    # bars + rank numbers
    for i, r in enumerate(ranked):
        y = pad_t + i * pitch
        blen = max(1, int(r["score"] / 100 * plot_w))
        img.rect(pad_l, y, blen, barh, _score_color(r["score"], lo, hi))
        _text(img, i + 1, 4, y + 3, 3, (60, 60, 60))
    img.rect(pad_l, pad_t, 1, n * pitch, (120, 120, 120))  # baseline

    img.write_ppm(path)
    print("wrote score bar chart -> %s  (%dx%d PPM)" % (path, W, H))
    print("  rank legend (bar length = score 0-100, green=high red=low):")
    for i, r in enumerate(ranked):
        print("    %2d. %-26s %5.1f" % (i + 1, r["model"], r["score"]))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def load_weights(path):
    with open(path, encoding="utf-8") as fh:
        user = json.load(fh)
    config = {k: dict(v) for k, v in DEFAULT_CONFIG.items()}
    for col, cfg in user.items():
        if col.startswith("_"):
            continue  # allow "_comment"-style annotation keys
        if col not in config:
            # allow brand-new properties only if they are numeric columns
            if col not in NUMERIC_COLS:
                sys.exit("error: weights file references unknown column %r" % col)
            config[col] = {"weight": 0.0, "direction": "higher"}
        config[col].update(cfg)
    return config


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Off-road SUV suitability analysis over a flat CSV "
                    "(no database required).")
    p.add_argument("--data", default=DATA_DEFAULT,
                   help="path to the SUV CSV (default: data/suvs.csv)")
    p.add_argument("--top", type=int, default=None,
                   help="show only the top N vehicles")
    p.add_argument("--min-year", type=int, default=1990)
    p.add_argument("--max-year", type=int, default=2015)
    p.add_argument("--sort", default="score",
                   help="column to sort by (default: composite score)")
    p.add_argument("--desc", action="store_true",
                   help="sort descending (score/clearance already default to "
                        "best-first)")
    p.add_argument("--asc", action="store_true", help="force ascending sort")
    p.add_argument("--weights", default=None,
                   help="JSON file overriding scoring weights/directions")
    p.add_argument("--correlations", action="store_true",
                   help="print the property correlation matrix and exit")
    p.add_argument("--show-detail", metavar="MODEL", default=None,
                   help="print a scoring breakdown for one vehicle")
    p.add_argument("--csv-out", default=None,
                   help="write the ranked table to a CSV file")
    p.add_argument("--ppm-heatmap", metavar="PATH", default=None,
                   help="write the property-correlation heatmap as a PPM image")
    p.add_argument("--ppm-bars", metavar="PATH", default=None,
                   help="write the off-road score bar chart as a PPM image "
                        "(respects --top)")
    p.add_argument("--list-weights", action="store_true",
                   help="print the active scoring weights and exit")
    args = p.parse_args(argv)

    config = load_weights(args.weights) if args.weights else \
        {k: dict(v) for k, v in DEFAULT_CONFIG.items()}

    if args.list_weights:
        total = sum(c["weight"] for c in config.values())
        print("Active scoring weights (normalised):")
        for col, cfg in sorted(config.items(), key=lambda kv: -kv[1]["weight"]):
            print("  %-28s %5.1f%%  (%s)"
                  % (col, cfg["weight"] / total * 100, cfg["direction"]))
        return 0

    rows = load_data(args.data)
    rows = filter_years(rows, args.min_year, args.max_year)
    rows = score(rows, config)

    if args.correlations:
        print_correlations(rows)
        return 0

    if args.show_detail:
        print_detail(rows, args.show_detail, config)
        return 0

    if args.ppm_heatmap or args.ppm_bars:
        if args.ppm_heatmap:
            build_heatmap_ppm(rows, args.ppm_heatmap)
        if args.ppm_bars:
            build_barchart_ppm(rows, args.ppm_bars, top=args.top)
        return 0

    # Sorting. Score and clearance default to best-first (descending) unless
    # the user forces a direction.
    sort_key = args.sort
    if sort_key not in rows[0] and sort_key != "score":
        sys.exit("error: unknown sort column %r" % sort_key)
    default_desc = sort_key in ("score", "ground_clearance_mm",
                                "wheel_track_mm", "torsional_rigidity_rating")
    descending = default_desc
    if args.asc:
        descending = False
    if args.desc:
        descending = True

    rows.sort(key=lambda r: (r.get(sort_key) is None, r.get(sort_key)),
              reverse=descending)

    print("Off-road starter-body ranking  |  %d vehicles, %d-%d"
          % (len(rows), args.min_year, args.max_year))
    print("Sorted by: %s (%s)\n"
          % (sort_key, "high to low" if descending else "low to high"))
    print_ranking(rows, top=args.top)

    if args.csv_out:
        print()
        write_csv(rows, args.csv_out, config)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        # Downstream pipe (e.g. `| head`) closed early; exit quietly.
        try:
            sys.stdout.close()
        finally:
            os._exit(0)
