"""Build the DuckDB database from the raw files.

    python src/build_db.py

Creates data/medicines.duckdb with:
  atc5, atc4, atc2, atc_labels   (sql/01_clean.sql)
  population                     (INSEE, one row per year x region x age group x sex)
  regions                        (code -> name, metropolitan regions only)
  analysis views                 (sql/02_views.sql)
"""
from __future__ import annotations

import gzip
import re
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
DB = ROOT / "data" / "medicines.duckdb"

# INSEE region names (as written in the population file) -> official region code.
# Open Medic uses these codes for the patient's region of residence.
REGIONS = {
    "Île-de-France": 11, "Centre-Val-de-Loire": 24, "Bourgogne-Franche-Comté": 27, "Normandie": 28,
    "Hauts-de-France": 32, "Grand Est": 44, "Pays de la Loire": 52, "Bretagne": 53,
    "Nouvelle-Aquitaine": 75, "Occitanie": 76, "Auvergne-Rhône-Alpes": 84,
    "Provence-Alpes-Côte d'Azur": 93, "Corse": 94,
}
# Open Medic age groups: 0 = 0-19, 20 = 20-59, 60 = 60 and over
AGE_GROUP = lambda lo: 0 if lo < 20 else 20 if lo < 60 else 60  # noqa: E731


def normalise_encodings() -> None:
    """Decompress every Open Medic file and rewrite it as UTF-8 text.
    The files do not all use the same encoding (Windows-1252 for the ATC4
    files of 2019-2024, UTF-8 for 2025, plain ASCII elsewhere): we try UTF-8
    first and fall back to Windows-1252."""
    INTERIM.mkdir(parents=True, exist_ok=True)
    for gz in sorted(RAW.glob("NB_*.CSV.gz")):
        data = gzip.decompress(gz.read_bytes())
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("cp1252")
        (INTERIM / gz.name.replace(".CSV.gz", ".csv")).write_text(text, encoding="utf-8")


def run_sql_file(con, name: str) -> None:
    sql = (ROOT / "sql" / name).read_text(encoding="utf-8")
    con.execute(sql.replace("{INTERIM}", INTERIM.as_posix()))


def load_population(con) -> None:
    """Population on 1 January of each year 2019-2023, by region, sex and the
    three Open Medic age groups. 2024 and 2025 reuse 2023 (latest available)."""
    rows = []
    for year in range(2019, 2024):
        raw = pd.read_excel(RAW / "insee_pop_reg.xls", sheet_name=str(year), header=None)
        hdr = raw.index[raw.iloc[:, 1].astype(str).str.contains("0 à 4", na=False)][0]
        ages, blocks = raw.iloc[hdr].tolist(), raw.iloc[hdr - 1].ffill().tolist()
        for _, line in raw.iloc[hdr + 1:].iterrows():
            name = str(line.iloc[0]).strip()
            if name not in REGIONS:
                continue
            for col, (block, age) in enumerate(zip(blocks, ages)):
                if isinstance(age, str) and "ans" in age and block in ("Hommes", "Femmes"):
                    rows.append((year, REGIONS[name], 1 if block == "Hommes" else 2,
                                 AGE_GROUP(int(age.split()[0])), float(line.iloc[col])))
    pop = pd.DataFrame(rows, columns=["year", "region", "sex", "age_group", "population"])
    pop = pop.groupby(["year", "region", "sex", "age_group"], as_index=False)["population"].sum()
    latest = pop[pop.year == 2023]
    pop = pd.concat([pop] + [latest.assign(year=y) for y in (2024, 2025)], ignore_index=True)
    con.execute("CREATE OR REPLACE TABLE population AS SELECT * FROM pop")
    reg = pd.DataFrame([(c, n) for n, c in REGIONS.items()], columns=["region", "region_name"])
    con.execute("CREATE OR REPLACE TABLE regions AS SELECT * FROM reg")


GENERIC_LABELS = {"ASSOCIATIONS", "DIVERS", "AUTRES", "AUTRES PREPARATIONS"}


def norm_label(label: str) -> str:
    """'VALSARTAN ET SACUBITRIL' and 'SACUBITRIL + VALSARTAN' -> 'SACUBITRIL + VALSARTAN'."""
    s = re.sub(r"\s+", " ", label.upper().replace(" ET ", " + ").replace(", ", " + ")).strip()
    return " + ".join(sorted(p.strip() for p in s.split("+")))


def build_molecule_map(con) -> None:
    """One molecule can appear under several ATC5 codes (the WHO reclassified
    GLP-1 analogues in 2020 and many cancer drugs in 2021) and under several
    spellings ('DAPAGLIFOZINE' / 'DAPAGLIFLOZINE'). We link two (code, label)
    pairs when they share the code OR the normalised label, and take the
    connected groups as molecules (union-find). The molecule name is the
    label used in the most recent year."""
    pairs = con.execute("SELECT atc5, label, max(year) AS last_year FROM atc5 GROUP BY ALL").df()
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    pairs["label"] = pairs["label"].fillna(pairs["atc5"])      # a few rows have no label
    for code, label in zip(pairs.atc5, pairs.label):
        if norm_label(label) in GENERIC_LABELS:           # catch-all labels must not link codes
            find("C:" + code); continue
        a, b = find("C:" + code), find("L:" + norm_label(label))
        if a != b:
            parent[a] = b
    pairs["group"] = [find("C:" + c) for c in pairs.atc5]
    latest = pairs.sort_values("last_year").groupby("group")["label"].last()
    pairs["molecule"] = pairs["group"].map(latest)
    generic = pairs["label"].map(norm_label).isin(GENERIC_LABELS)
    pairs.loc[generic, "molecule"] = pairs["label"] + " (" + pairs["atc5"] + ")"
    mm = pairs[["atc5", "label", "molecule"]]
    con.execute("CREATE OR REPLACE TABLE molecule_map AS SELECT * FROM mm")


def main() -> None:
    DB.unlink(missing_ok=True)
    normalise_encodings()
    con = duckdb.connect(DB.as_posix())
    run_sql_file(con, "01_clean.sql")
    load_population(con)
    build_molecule_map(con)
    run_sql_file(con, "02_views.sql")
    for t in ("atc5", "atc4", "atc2", "atc_labels", "population"):
        print(f"{t:<11} {con.execute(f'SELECT count(*) FROM {t}').fetchone()[0]:>9,} rows")
    con.close()


if __name__ == "__main__":
    main()
