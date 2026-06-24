-- queries.sql — example analyses against the Turso database.
-- Run a single query interactively, e.g.:
--   tursodb suvs.db "SELECT model, score FROM suv_scores ORDER BY score DESC LIMIT 10"
-- or run this whole file:
--   tursodb suvs.db < queries.sql

-- 1) Top 10 off-road starter bodies by composite score.
SELECT model, year_start, ground_clearance_mm, wheelbase_mm, weight_kg, score
FROM suv_scores
ORDER BY score DESC
LIMIT 10;

-- 2) Best body-on-frame candidates only (ladder frames), 1990-2015.
SELECT model, construction, ground_clearance_mm, score
FROM suv_scores
WHERE construction LIKE '%ladder%'
  AND year_start <= 2015 AND year_end >= 1990
ORDER BY score DESC
LIMIT 10;

-- 3) Highest ground clearance, lightest first as a tie-breaker.
SELECT model, ground_clearance_mm, weight_kg
FROM suvs
ORDER BY ground_clearance_mm DESC, weight_kg ASC
LIMIT 8;

-- 4) "Lightweight + capable" sweet spot: under 1.7 t with >=220mm clearance.
SELECT model, weight_kg, ground_clearance_mm, wheelbase_mm
FROM suvs
WHERE weight_kg < 1700 AND ground_clearance_mm >= 220
ORDER BY ground_clearance_mm DESC;

-- 5) Average clearance and mass grouped by construction type.
SELECT construction,
       COUNT(*)                       AS n,
       ROUND(AVG(ground_clearance_mm)) AS avg_clearance_mm,
       ROUND(AVG(weight_kg))           AS avg_weight_kg
FROM suvs
GROUP BY construction
ORDER BY avg_clearance_mm DESC;

-- 6) The classic relationship check: does a longer wheelbase mean more mass?
--    (Covariance sign / simple Pearson numerator vs denominators.)
SELECT
    COUNT(*)                                                       AS n,
    ROUND(AVG(wheelbase_mm))                                       AS avg_wb,
    ROUND(AVG(weight_kg))                                          AS avg_kg,
    ROUND(
        (AVG(wheelbase_mm * weight_kg) - AVG(wheelbase_mm) * AVG(weight_kg)) /
        ( ((AVG(wheelbase_mm*wheelbase_mm) - AVG(wheelbase_mm)*AVG(wheelbase_mm))
           * (AVG(weight_kg*weight_kg)     - AVG(weight_kg)*AVG(weight_kg))
          ) ), 4)                                                  AS r_squared_proxy
FROM suvs;
