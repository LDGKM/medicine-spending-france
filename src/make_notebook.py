"""Build and execute notebooks/medicine_spending.ipynb (guided tour of the analysis)."""
from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell

cells = [
    md("# What France reimburses: medicines dispensed in pharmacies, 2019–2025\n"
       "Data: Open Medic (Assurance Maladie, extracted from the national health data system SNDS) — every box of "
       "medicine dispensed by a retail pharmacy and reimbursed, by molecule, age group, sex and region. "
       "Population: INSEE. Tables come from SQL queries on `data/medicines.duckdb` (see `sql/`), charts from `src/analysis.py`."),
    code("import sys; sys.path.insert(0, '../src')\nfrom IPython.display import Image\n"
         "import pandas as pd; pd.set_option('display.precision', 3); pd.set_option('display.width', 160)\n"
         "from analysis import *"),
    md("## 0. Checks\nThe files exist at three levels of detail (molecule, class, group). Summing spending at each level "
       "must give the same total: it does, to the euro."),
    code("consistency()"),
    code("data_quality()"),
    md("19% of spending concerns molecules that appear under two or more ATC codes: the WHO reclassified GLP-1 "
       "analogues in 2020 and many cancer drugs in 2021, and some labels are misspelt in some years. "
       "`build_db.py` links codes and labels into stable molecules (union-find) so that growth is not mistaken for a new drug."),
    md("## 1. Spending grows, volume does not"),
    code("t = totals(); t"),
    code("fig_totals(t); Image('../figures/01_spending_vs_volume.png')"),
    md("Reimbursements rose by 43% in six years while the number of boxes stayed flat: the growth comes from the price "
       "and the mix of medicines, not from people taking more."),
    code("g = growth_by_group(); fig_growth_by_group(g); Image('../figures/02_growth_by_group.png')"),
    code("m = molecule_movers(); fig_movers(m); Image('../figures/03_molecule_movers.png')"),
    code("concentration()"),
    md("Spending is concentrating: in 2025, 55 molecules out of about 1,100 make up half of all reimbursements (70 in 2019). "
       "Tafamidis, a treatment for a heart disease (transthyretin amyloidosis), went from 45 to 1,071 million euros "
       "and is now the most reimbursed molecule, for about 16,000 patients."),
    md("## 2. Three stories"),
    code("glp1()"),
    code("antibiotics().pivot(index='year', columns='age_group', values='patients_m')"),
    code("adhd().pivot(index='year', columns='age_group', values='patients_k')"),
    code("fig_stories(glp1(), glp1_molecules(), antibiotics(), adhd()); Image('../figures/04_three_stories.png')"),
    md("* **GLP-1 analogues** (diabetes): patients more than doubled, from 415,000 in 2020 to 932,000 in 2025, led by semaglutide.\n"
       "* **Antibiotics**: lockdowns and masks cut the number of patients by 17% in 2020 (25% for under-20s); "
       "it was back to its 2019 level in 2024.\n"
       "* **Methylphenidate** (ADHD): adult patients went from 17,000 to 114,000, children from 79,000 to 185,000."),
    md("## 3. Regions: compare like with like\nOlder regions spend more simply because their population is older. "
       "Direct age standardisation removes that effect."),
    code("age_profile()"),
    code("r = regions(); r"),
    code("fig_regions(r); Image('../figures/05_regions.png')"),
    md("Île-de-France looks cheap only because it is young: once standardised it moves from 11th to 3rd. "
       "Grand Est is 5th of 12 before standardisation and 4th after, slightly above the median."),
]
nb = nbf.v4.new_notebook(cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3"}})
path = ROOT / "notebooks" / "medicine_spending.ipynb"
NotebookClient(nb, timeout=900, resources={"metadata": {"path": str(path.parent)}}).execute()
nbf.write(nb, path)
print("written", path)
