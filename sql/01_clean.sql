-- =====================================================================
-- 01_clean.sql  —  Open Medic gzip CSV files  ->  clean tables
-- build_db.py first converts every file to UTF-8 (the ATC4 files of 2019-2024
-- use the Windows-1252 code page, the 2025 one UTF-8) into data/interim/.
-- Files are ';'-separated, with French number formats:
-- "1.171,74" means 1171.74 (dot = thousands separator, comma = decimals).
-- The macro eur() converts such text to a DOUBLE.
-- {INTERIM} is replaced by the Python loader with the data/interim folder.
-- =====================================================================

CREATE OR REPLACE MACRO eur(x) AS
    TRY_CAST(replace(replace(trim(x), '.', ''), ',', '.') AS DOUBLE);

-- One row per year x molecule (ATC5) x age group x sex x region
--   patients    = number of people who received the molecule at least once (nbc)
--   reimbursed  = amount paid by health insurance, EUR (REM)
--   base        = reimbursement base, EUR (BSE) ~ list price of what was dispensed
--   boxes       = number of boxes dispensed (BOITES)
CREATE OR REPLACE TABLE atc5 AS
SELECT
    CAST(regexp_extract(filename, 'NB_(\d{4})_', 1) AS INTEGER) AS year,
    upper(trim(ATC5))            AS atc5,
    trim(l_atc5)                 AS label,
    CAST(age AS INTEGER)         AS age_group,   -- 0 = 0-19, 20 = 20-59, 60 = 60+, 99 = unknown
    CAST(sexe AS INTEGER)        AS sex,         -- 1 male, 2 female, 9 unknown
    CAST(BEN_REG AS INTEGER)     AS region,      -- INSEE region code of the patient (see below)
    eur(nbc)                     AS patients,
    eur(REM)                     AS reimbursed,
    eur(BSE)                     AS base,
    eur(BOITES)                  AS boxes
FROM read_csv('{INTERIM}/NB_*_atc5_age_sexe_reg.csv', delim=';', header=true, all_varchar=true,
              filename=true, union_by_name=true);

-- Same structure at ATC level 4 and 2. Patient counts are only additive
-- inside one file: a person taking two molecules of the same class counts
-- twice in atc5 but once in atc4. So class-level patient numbers must come
-- from these files, never from summing atc5.
CREATE OR REPLACE TABLE atc4 AS
SELECT CAST(regexp_extract(filename, 'NB_(\d{4})_', 1) AS INTEGER) AS year,
       upper(trim(ATC4)) AS atc4, trim(l_atc4) AS label,
       CAST(age AS INTEGER) AS age_group, CAST(sexe AS INTEGER) AS sex, CAST(BEN_REG AS INTEGER) AS region,
       eur(nbc) AS patients, eur(REM) AS reimbursed, eur(BSE) AS base, eur(BOITES) AS boxes
FROM read_csv('{INTERIM}/NB_*_atc4_age_sexe_reg.csv', delim=';', header=true, all_varchar=true,
              filename=true, union_by_name=true);

CREATE OR REPLACE TABLE atc2 AS
SELECT CAST(regexp_extract(filename, 'NB_(\d{4})_', 1) AS INTEGER) AS year,
       upper(trim(ATC2)) AS atc2, trim(l_atc2) AS label,
       CAST(age AS INTEGER) AS age_group, CAST(sexe AS INTEGER) AS sex, CAST(BEN_REG AS INTEGER) AS region,
       eur(nbc) AS patients, eur(REM) AS reimbursed, eur(BSE) AS base, eur(BOITES) AS boxes
FROM read_csv('{INTERIM}/NB_*_atc2_age_sexe_reg.csv', delim=';', header=true, all_varchar=true,
              filename=true, union_by_name=true);

-- Labels of the ATC hierarchy. Level 1 comes from its own summary file;
-- levels 2, 4 and 5 are taken from the detailed tables above. (The 2024
-- summary files for levels 3 and 4 use a DOS code page and are not needed.)
CREATE OR REPLACE TABLE atc_labels AS
SELECT 1 AS level, upper(trim(ATC1)) AS code, trim(L_ATC1) AS label
  FROM read_csv('{INTERIM}/NB_2024_atc1.csv', delim=';', header=true, all_varchar=true)
UNION ALL SELECT DISTINCT ON (atc2) 2, atc2, label FROM atc2
UNION ALL SELECT DISTINCT ON (atc4) 4, atc4, label FROM atc4
UNION ALL SELECT DISTINCT ON (atc5) 5, atc5, label FROM atc5;
