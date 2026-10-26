-- =====================================================================
-- 02_views.sql  —  analysis-ready views
-- =====================================================================

-- Metropolitan regions present in Open Medic. Codes 0, 5 and 99 are not
-- metropolitan regions (unknown / other / overseas grouping) and Corsica
-- (94) is not published separately, so regional comparisons use these 12.
CREATE OR REPLACE TABLE metro_regions AS
SELECT * FROM regions WHERE region IN (11, 24, 27, 28, 32, 44, 52, 53, 75, 76, 84, 93);

-- Every ATC5 row with its molecule (stable across code changes) and its
-- main therapeutic group (ATC level 1 = first letter of the code).
CREATE OR REPLACE VIEW atc5_mol AS
SELECT a.*, m.molecule, left(a.atc5, 1) AS atc1, l.label AS atc1_label
FROM atc5 a
JOIN molecule_map m ON m.atc5 = a.atc5 AND m.label = COALESCE(a.label, a.atc5)
LEFT JOIN atc_labels l ON l.level = 1 AND l.code = left(a.atc5, 1);

-- National totals per year
CREATE OR REPLACE VIEW yearly AS
SELECT year,
       sum(reimbursed)              AS reimbursed,
       sum(base)                    AS base,
       sum(boxes)                   AS boxes,
       sum(base) / sum(boxes)       AS base_per_box
FROM atc5 GROUP BY year;

-- Spending per molecule and year, with year-on-year growth (window function LAG)
CREATE OR REPLACE VIEW molecule_year AS
SELECT molecule, year, sum(reimbursed) AS reimbursed, sum(boxes) AS boxes,
       sum(reimbursed) - lag(sum(reimbursed)) OVER (PARTITION BY molecule ORDER BY year) AS change_vs_prev_year
FROM atc5_mol GROUP BY molecule, year;

-- Region x year x age group: spending and population (metropolitan regions)
CREATE OR REPLACE VIEW region_age AS
WITH spend AS (
    SELECT year, region, age_group, sum(reimbursed) AS reimbursed
    FROM atc5 WHERE age_group IN (0, 20, 60) GROUP BY ALL
), pop AS (
    SELECT year, region, age_group, sum(population) AS population FROM population GROUP BY ALL
)
SELECT s.year, s.region, r.region_name, s.age_group, s.reimbursed, p.population
FROM spend s
JOIN metro_regions r USING (region)
JOIN pop p USING (year, region, age_group);
