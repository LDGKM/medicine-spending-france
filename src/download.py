"""Download the raw data used by the project.

Sources (open data):
  * Open Medic (Assurance Maladie / SNDS): medicines dispensed by retail pharmacies
    and reimbursed by all health-insurance schemes, 2019-2025, "NB" files:
      - NB_<year>_atc5_age_sexe_reg : one row per molecule (ATC level 5) x age group x sex x region
      - NB_<year>_atc4_age_sexe_reg : same at ATC level 4 (therapeutic class, e.g. GLP-1 analogues)
      - NB_<year>_atc2_age_sexe_reg : same at ATC level 2 (e.g. antibiotics)
      - NB_2024_atc1                : labels of the 14 main ATC groups
    https://www.data.gouv.fr/datasets/open-medic-base-complete-sur-les-depenses-de-medicaments-interregimes/
  * INSEE population estimates by region, sex and five-year age group (1975-2023)
  * Simplified region boundaries (gregoiredavid/france-geojson)

The Assurance Maladie download pages hand out a short-lived token in each
link, so we first read the listing page, then download the file it points to.

Run:  python src/download.py      (already-downloaded files are skipped)
"""
from __future__ import annotations

import re
import time
import urllib.request
from pathlib import Path

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
YEARS = range(2019, 2026)
BASE = "https://open-data-assurance-maladie.ameli.fr/medicaments/"
EXTRA = {
    "insee_pop_reg.xls": "https://www.insee.fr/fr/statistiques/fichier/1893198/estim-pop-nreg-sexe-aq-1975-2023.xls",
    "regions.geojson": "https://raw.githubusercontent.com/gregoiredavid/france-geojson/master/regions-version-simplifiee.geojson",
}


def get(url: str, tries: int = 5) -> bytes:
    for attempt in range(1, tries + 1):
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 - network errors: retry
            print(f"  retry {attempt}/{tries}: {e}")
            time.sleep(3 * attempt)
    raise RuntimeError(f"could not download {url}")


def open_medic(folder: str, filename: str) -> None:
    """Download one Open Medic file listed on the page of `folder` (e.g. '2024_ATC5')."""
    dest = RAW / filename
    if dest.exists() and dest.stat().st_size > 500:
        return
    page = get(f"{BASE}download2.php?Dir_Rep={folder}").decode("latin-1")
    m = re.search(r'href="\./(download_file\.php\?token=[^"]*' + re.escape(filename) + ')"', page)
    if not m:
        raise RuntimeError(f"{filename} not listed on {folder}")
    dest.write_bytes(get(BASE + m.group(1)))
    print(f"  ok   {filename}")


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for y in YEARS:
        for lvl in (5, 4, 2):
            open_medic(f"{y}_ATC{lvl}", f"NB_{y}_atc{lvl}_age_sexe_reg.CSV.gz")
    open_medic("2024_ATC1", "NB_2024_atc1.CSV.gz")
    for name, url in EXTRA.items():
        dest = RAW / name
        if not dest.exists():
            dest.write_bytes(get(url)); print(f"  ok   {name}")


if __name__ == "__main__":
    main()
