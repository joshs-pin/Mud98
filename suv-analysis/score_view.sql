-- score_view.sql — the weighted off-road suitability score, in pure SQL.
-- Mirrors the default weights/directions in analyze.py so the Turso database
-- and the Python tool agree. Pure SQL (no dot-commands): safe to run via
--   tursodb suvs.db < score_view.sql
DROP VIEW IF EXISTS suv_scores;

CREATE VIEW suv_scores AS
WITH stats AS (
    SELECT
        MIN(ground_clearance_mm)       AS clr_lo, MAX(ground_clearance_mm)       AS clr_hi,
        MIN(wheelbase_mm)              AS wb_lo,  MAX(wheelbase_mm)              AS wb_hi,
        MIN(weight_kg)                 AS wt_lo,  MAX(weight_kg)                 AS wt_hi,
        MIN(wheel_track_mm)            AS tr_lo,  MAX(wheel_track_mm)            AS tr_hi,
        MIN(width_mm)                  AS wd_lo,  MAX(width_mm)                  AS wd_hi,
        MIN(torsional_rigidity_rating) AS rg_lo,  MAX(torsional_rigidity_rating) AS rg_hi,
        MIN(height_mm)                 AS ht_lo,  MAX(height_mm)                 AS ht_hi,
        MIN(length_mm)                 AS ln_lo,  MAX(length_mm)                 AS ln_hi
    FROM suvs
),
sub AS (
    SELECT s.*,
        -- higher-is-better: (v - lo) / (hi - lo)
        1.0 * (s.ground_clearance_mm - x.clr_lo) / (x.clr_hi - x.clr_lo)        AS sub_clr,
        1.0 * (s.wheel_track_mm     - x.tr_lo)  / (x.tr_hi - x.tr_lo)           AS sub_tr,
        1.0 * (s.torsional_rigidity_rating - x.rg_lo) / (x.rg_hi - x.rg_lo)     AS sub_rg,
        -- lower-is-better: 1 - (v - lo)/(hi - lo)
        1.0 - 1.0 * (s.weight_kg - x.wt_lo) / (x.wt_hi - x.wt_lo)               AS sub_wt,
        1.0 - 1.0 * (s.width_mm  - x.wd_lo) / (x.wd_hi - x.wd_lo)               AS sub_wd,
        1.0 - 1.0 * (s.height_mm - x.ht_lo) / (x.ht_hi - x.ht_lo)              AS sub_ht,
        1.0 - 1.0 * (s.length_mm - x.ln_lo) / (x.ln_hi - x.ln_lo)              AS sub_ln,
        -- band (sweet spot 2350..2750mm): 1.0 inside, linear falloff outside,
        -- scaled by the dataset spread, floored at 0.
        CASE
            WHEN s.wheelbase_mm BETWEEN 2350 AND 2750 THEN 1.0
            WHEN s.wheelbase_mm < 2350
                THEN MAX(0.0, 1.0 - (2350 - s.wheelbase_mm) * 1.0 / (x.wb_hi - x.wb_lo))
            ELSE     MAX(0.0, 1.0 - (s.wheelbase_mm - 2750) * 1.0 / (x.wb_hi - x.wb_lo))
        END AS sub_wb
    FROM suvs s CROSS JOIN stats x
)
SELECT
    model, year_start, year_end, construction,
    weight_kg, wheel_track_mm, wheelbase_mm, length_mm, width_mm, height_mm,
    ground_clearance_mm, torsional_rigidity_rating,
    ROUND(100.0 * (
        0.28 * sub_clr +
        0.18 * sub_wb  +
        0.14 * sub_wt  +
        0.10 * sub_tr  +
        0.10 * sub_wd  +
        0.10 * sub_rg  +
        0.06 * sub_ht  +
        0.04 * sub_ln
    ), 1) AS score
FROM sub;
