# SUV Off-Road Starter-Body Analysis (1990–2015)

A deliberately small **"data at rest"** project: no database, no servers, no
third-party libraries. The dataset is a single flat CSV
([`data/suvs.csv`](data/suvs.csv)) and all sorting, scoring, and relationship
analysis is done by one stdlib-only Python script
([`analyze.py`](analyze.py)).

The goal is to compare the *physical properties* of used SUVs from 1990–2015
and rank them as candidate **starter bodies for an off-road project car**.

---

## Quick start

```bash
cd suv-analysis

python3 analyze.py                 # ranked recommendation (default weights)
python3 analyze.py --top 10        # top 10 only
python3 analyze.py --correlations  # how the properties relate to each other
python3 analyze.py --show-detail "Jeep Wrangler TJ"   # scoring breakdown
python3 analyze.py --list-weights  # see the active scoring weights
```

Requires only **Python 3** (tested with the standard library — `csv`, `json`,
`math`, `argparse`). Nothing to install.

---

## Optional: query it with Turso (Rust SQLite)

The CSV stays the at-rest source of truth, but you can also load it into
**[Turso](https://github.com/tursodatabase/turso)** — the from-scratch Rust
rewrite of SQLite — and query it with SQL. The Turso shell binary is
`tursodb`.

```bash
./build_db.sh                       # rebuilds suvs.db from data/suvs.csv
tursodb suvs.db "SELECT model, score FROM suv_scores ORDER BY score DESC LIMIT 10"
tursodb suvs.db < queries.sql       # run the example analyses
```

`build_db.sh` is idempotent: it stages the CSV in an all-TEXT table, imports
it (`.import --csv --skip 1`), casts the numeric columns into a typed `suvs`
table, and creates a **`suv_scores` view** that computes the exact same
weighted off-road score as `analyze.py` — the two implementations agree to
the decimal (Wrangler TJ = 74.0 in both). See [`score_view.sql`](score_view.sql)
for the scoring SQL and [`queries.sql`](queries.sql) for worked examples.

> **Gotcha worth knowing:** Turso's `.import` is a *shell meta-command*, not
> SQL, so it is ignored when a `.sql` file is piped in via `<`. It must be fed
> on stdin — which is why the import lives in `build_db.sh` rather than a pure
> `.sql` file. The pure-SQL files (`score_view.sql`, `queries.sql`) run fine
> via redirection.

The generated `suvs.db` is git-ignored (it's regenerable from the CSV).

**Installing tursodb** (if not already present): grab the prebuilt binary for
your platform from the [releases page](https://github.com/tursodatabase/turso/releases)
(this project was built against `v0.6.1`), or build from source with
`cargo install` per the upstream README.

---

## The properties tracked

You asked to track nine physical properties. Here is how each maps to a
column in the dataset (all dimensions in **mm**, mass in **kg**):

| Your property               | Column                       | Meaning                                                            |
|-----------------------------|------------------------------|--------------------------------------------------------------------|
| weight                      | `weight_kg`                  | Kerb (curb) weight, representative trim                            |
| wheel width                 | `wheel_track_mm`             | **Track width** — centre-to-centre between left/right wheels       |
| wheelbase                   | `wheelbase_mm`               | Front-to-rear axle distance                                       |
| length / body length        | `length_mm`                  | Overall bumper-to-bumper length (see note below)                  |
| body width                  | `width_mm`                   | Overall body width, excluding mirrors                             |
| body height                 | `height_mm`                  | Overall height (roof), unladen                                    |
| clearance                   | `ground_clearance_mm`        | Minimum ground clearance, stock                                   |
| rating of torsional rigidity| `torsional_rigidity_rating`  | **1–5 engineering rating** (see the honesty note below)           |

> **"length" vs "body length".** You listed both. For a monocoque or a
> body-on-frame SUV these are the same measurement — the overall length —
> so the dataset represents it once as `length_mm` rather than inventing a
> spurious second figure. If you have a specific distinction in mind (e.g.
> cargo-bay length), say so and I'll add a dedicated column.

Extra context columns: `model`, `year_start`, `year_end`, `generation`,
`construction`, `notes`.

---

## ⚠️ Honesty note on data provenance

This matters for a project where you'll spend real money, so read it.

- **Dimensions, wheelbase, track, clearance, weight** are nominal
  manufacturer figures for a *representative trim and market*. Real numbers
  drift by trim, model year, market, and especially **tyre/suspension
  changes** — a lift and bigger tyres will change clearance and height
  immediately. Treat these as comparison-grade, not gospel. **Verify the
  exact variant before buying.**

- **Torsional rigidity is a 1–5 rating, not a measured Nm/deg figure.**
  Carmakers very rarely publish torsional-rigidity numbers for consumer
  SUVs, so a column of "real" Nm/deg values would be mostly fabricated. To
  avoid misleading you, this is instead an engineering judgement based on
  **construction type and known reputation**:

  | Rating | Meaning                                                        |
  |:------:|----------------------------------------------------------------|
  | 5      | Very stiff structure                                           |
  | 4      | Stiff unibody or monocoque-with-integrated-ladder             |
  | 3      | Typical robust body-on-frame ladder                           |
  | 2      | Deliberately flexible ladder frame (e.g. Wrangler, Samurai)   |
  | 1      | Very flexible / minimal structure                             |

  If you can source a measured figure for a specific chassis, drop it into a
  new numeric column and weight it — the script handles arbitrary numeric
  columns.

If you'd rather I replace any field with figures you've verified yourself,
the CSV is plain text — edit it directly, or hand me your numbers.

---

## How the recommendation score works

Each vehicle gets a composite **0–100 off-road suitability score**. Every
property is first turned into a 0–1 sub-score, then combined using tunable
weights (auto-normalised to sum to 1.0).

Three scoring "directions":

- **`higher`** — more is better. *Ground clearance, track width.*
- **`lower`** — less is better. *Weight, body width, height, length* (lighter
  recovers easier; narrower/shorter clears tight trails and improves
  approach/break-over/departure; lower drops the centre of gravity).
- **`band`** — a **sweet spot** is best. *Wheelbase*: too short is twitchy and
  tippy at speed, too long kills break-over angle and trail agility. The
  default sweet spot is **2350–2750 mm**; values inside score 1.0 and fall off
  proportionally outside.

### Default weights

| Property                     | Weight | Direction | Why                                              |
|------------------------------|:------:|-----------|--------------------------------------------------|
| `ground_clearance_mm`        | 28%    | higher    | The single biggest off-road determinant          |
| `wheelbase_mm`               | 18%    | band      | Break-over vs. high-speed stability trade-off     |
| `weight_kg`                  | 14%    | lower     | Recovery, economy, "less to get stuck"            |
| `wheel_track_mm`             | 10%    | higher    | Lateral stability on side-slopes                  |
| `width_mm`                   | 10%    | lower     | Squeezing through trails / between trees          |
| `torsional_rigidity_rating`  | 10%    | higher    | Good base for cages/armour (**see caveat**)       |
| `height_mm`                  | 6%     | lower     | Lower centre of gravity                           |
| `length_mm`                  | 4%     | lower     | Approach/departure angles, maneuverability        |

> **The rigidity direction is a genuine judgement call.** A *stiffer* body is a
> better foundation for a caged, armoured, high-speed build. A *flexier* frame
> articulates more and keeps tyres planted on technical terrain. The default
> assumes "stiffer is better" at a modest 10% — flip it to `lower` (or zero it)
> if you favour articulation. See the worked example below.

### Tuning the weights

Pass your own JSON file. Anything you omit falls back to the default. An
example articulation-first profile ships as
[`weights.articulation.json`](weights.articulation.json):

```bash
python3 analyze.py --weights weights.articulation.json --top 8
```

A weights file entry looks like:

```json
{
  "ground_clearance_mm": {"weight": 0.35, "direction": "higher"},
  "wheelbase_mm":        {"weight": 0.20, "direction": "band", "band": [2300, 2650]},
  "torsional_rigidity_rating": {"weight": 0.10, "direction": "lower"}
}
```

(Keys beginning with `_`, e.g. `_comment`, are ignored — handy for notes.)

---

## Relationship analysis

`--correlations` prints a Pearson correlation matrix between the physical
properties, so you can see which ones move together:

```bash
python3 analyze.py --correlations
```

In this dataset the strong stories are unsurprising but useful to quantify:
**weight, track, body width, and wheelbase all rise together** (bigger trucks
are bigger in every dimension at once), while **ground clearance is nearly
independent** of all of them — meaning clearance is something you select for
deliberately, not something you get "for free" by buying a bigger vehicle.

---

## Visualise it — PPM images, zero dependencies

You can render the analysis as images **without any plotting library**. The
charts are written as **PPM** (Netpbm portable pixmap) — the image-world
equivalent of our CSV: just a header plus raw RGB bytes, written by hand from
the standard library. PPM is the right primitive for a "no heavy tooling"
project (matplotlib would be a large dependency for one chart).

```bash
python3 analyze.py --ppm-heatmap correlation.ppm     # property correlation heatmap
python3 analyze.py --ppm-bars score_bars.ppm --top 12  # off-road score bar chart
```

- **Heatmap** — the correlation matrix as a diverging colormap (red = +1, blue
  = −1, pale = ~0), with a colour-scale bar. An index→property legend prints to
  stdout. The size-correlated cluster (wheelbase/mass/track/width) lights up
  red; ground clearance stays pale, exactly as the numbers say.
- **Bar chart** — each SUV's composite score as a bar, longest first, coloured
  green (high) → red (low), with rank numbers drawn on the image and a
  rank→model legend printed to stdout.

> **Viewing `.ppm`:** most modern viewers won't open PPM directly. Convert it
> for sharing — e.g. `pnmtopng score_bars.ppm > score_bars.png`, ImageMagick
> `convert score_bars.ppm score_bars.png`, or any online PPM viewer. PPM is a
> great *internal/zero-dep* format, a poor *delivery* format. (Generated
> `*.ppm`/`*.png` are git-ignored.)

---

## Full option list

```
--data PATH           use a different CSV (default: data/suvs.csv)
--top N               show only the top N
--min-year / --max-year   restrict the production window (default 1990–2015)
--sort COLUMN         sort by any column (default: composite score)
--desc / --asc        force sort direction
--weights FILE.json   override scoring weights/directions
--correlations        print the property correlation matrix and exit
--show-detail MODEL   print a per-property scoring breakdown for one vehicle
--list-weights        print the active weights and exit
--csv-out FILE.csv    write the ranked table out as CSV
--ppm-heatmap PATH    render the correlation heatmap as a PPM image
--ppm-bars PATH       render the score bar chart as a PPM image (respects --top)
```

---

## Files

```
suv-analysis/
├── README.md                     # this file
├── analyze.py                    # the stdlib-only analysis tool
├── weights.articulation.json     # example alternate scoring profile
├── build_db.sh                   # build the Turso DB from the CSV (idempotent)
├── score_view.sql                # weighted off-road score as a SQL view
├── queries.sql                   # example SQL analyses
├── .gitignore                    # ignores generated *.db / *.ppm / *.png
└── data/
    └── suvs.csv                  # the dataset "at rest" (source of truth)
```

## Extending the dataset

Add a row to `data/suvs.csv` — it's plain CSV with a header. Blank numeric
cells are allowed and score as neutral (0.5) so a single missing field won't
unfairly sink a vehicle. Add new numeric properties by adding a column and
listing it in `NUMERIC_COLS` in `analyze.py`, then weight it in a weights file.
