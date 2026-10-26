"""Analyses of French spending on medicines dispensed in retail pharmacies, 2019-2025.

    python src/analysis.py        # writes figures/ and results/

Each function answers one question and returns a DataFrame; the fig_*
functions draw the matching chart. The notebook imports the same functions.
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "medicines.duckdb"
FIG, RES = ROOT / "figures", ROOT / "results"
YEARS = list(range(2019, 2026))
GRAND_EST = 44

INK, MUTED, GRID = "#1f2933", "#6b7280", "#e5e7eb"
BLUE, RED, ORANGE, GREEN, PURPLE, TEAL, GREY = "#2563eb", "#dc2626", "#ea8c2c", "#16a34a", "#7c3aed", "#0d9488", "#9ca3af"
plt.rcParams.update({
    "figure.dpi": 110, "savefig.dpi": 200, "savefig.bbox": "tight",
    "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "axes.edgecolor": MUTED, "axes.labelcolor": INK, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "xtick.color": MUTED, "ytick.color": MUTED,
    "legend.frameon": False,
})


def q(sql: str, **params) -> pd.DataFrame:
    with duckdb.connect(DB.as_posix(), read_only=True) as c:
        return c.execute(sql, params).df()


def save(fig, name: str) -> None:
    FIG.mkdir(exist_ok=True)
    fig.savefig(FIG / f"{name}.png")
    plt.close(fig)


def title_case(s: str) -> str:
    return s.capitalize() if s.isupper() else s


# ---------------------------------------------------------------- 0. data checks
def consistency() -> pd.DataFrame:
    """The same spending summed from three levels of detail must be equal."""
    return q("""
        SELECT a.year, a.r / 1e9 AS from_atc5_bn, b.r / 1e9 AS from_atc4_bn, c.r / 1e9 AS from_atc2_bn
        FROM (SELECT year, sum(reimbursed) r FROM atc5 GROUP BY year) a
        JOIN (SELECT year, sum(reimbursed) r FROM atc4 GROUP BY year) b USING (year)
        JOIN (SELECT year, sum(reimbursed) r FROM atc2 GROUP BY year) c USING (year) ORDER BY year""")


def data_quality() -> pd.DataFrame:
    """Share of spending we cannot place by age, sex or region (2019-2025)."""
    return q("""
        SELECT 'age group unknown'                   AS issue, sum(reimbursed) FILTER (WHERE age_group = 99) / sum(reimbursed) AS share FROM atc5
        UNION ALL SELECT 'sex unknown',                     sum(reimbursed) FILTER (WHERE sex = 9) / sum(reimbursed) FROM atc5
        UNION ALL SELECT 'region not a metropolitan region', sum(reimbursed) FILTER (WHERE region NOT IN (SELECT region FROM metro_regions)) / sum(reimbursed) FROM atc5
        UNION ALL SELECT 'molecule label missing',          sum(reimbursed) FILTER (WHERE label IS NULL) / sum(reimbursed) FROM atc5
        UNION ALL SELECT 'molecule appears under 2+ ATC codes', sum(reimbursed) FILTER (WHERE molecule IN (
                      SELECT molecule FROM molecule_map GROUP BY molecule HAVING count(DISTINCT atc5) > 1)) / sum(reimbursed) FROM atc5_mol""")


# ---------------------------------------------------------------- 1. the big picture
def totals() -> pd.DataFrame:
    return q("SELECT year, reimbursed / 1e9 AS reimbursed_bn, boxes / 1e9 AS boxes_bn, base_per_box FROM yearly ORDER BY year")


def fig_totals(df: pd.DataFrame) -> None:
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 3.7))
    a1.plot(df.year, 100 * df.reimbursed_bn / df.reimbursed_bn.iloc[0], marker="o", lw=2.2, color=RED, label="amount reimbursed")
    a1.plot(df.year, 100 * df.boxes_bn / df.boxes_bn.iloc[0], marker="o", lw=2.2, color=BLUE, label="boxes dispensed")
    a1.axhline(100, color=MUTED, lw=0.8, ls="--"); a1.set_xticks(YEARS); a1.legend()
    a1.set_title("Spending vs volume (index 2019 = 100)")
    for x, y in ((2019, 100), (2025, 100 * df.reimbursed_bn.iloc[-1] / df.reimbursed_bn.iloc[0])):
        a1.annotate(f"EUR {df.set_index('year').loc[x, 'reimbursed_bn']:.1f} bn", (x, y), xytext=(0, 8),
                    textcoords="offset points", ha="center", fontsize=8, color=RED)
    a2.bar(df.year, df.base_per_box, color=[GREY] * 6 + [RED])
    for x, v in zip(df.year, df.base_per_box):
        a2.text(x, v + 0.2, f"{v:.2f}", ha="center", fontsize=8)
    a2.set_title("Average price of a box (EUR, reimbursement base)"); a2.set_xticks(YEARS)
    save(fig, "01_spending_vs_volume")


def growth_by_group() -> pd.DataFrame:
    """Contribution of each main therapeutic group (ATC level 1) to the growth 2019 -> 2025."""
    return q("""
        SELECT atc1, any_value(atc1_label) AS label,
               sum(reimbursed) FILTER (WHERE year = 2019) / 1e9 AS bn_2019,
               sum(reimbursed) FILTER (WHERE year = 2025) / 1e9 AS bn_2025,
               (sum(reimbursed) FILTER (WHERE year = 2025) - sum(reimbursed) FILTER (WHERE year = 2019)) / 1e9 AS change_bn
        FROM atc5_mol GROUP BY atc1 ORDER BY change_bn DESC""")


SHORT = {"L": "Cancer & immunology (L)", "N": "Nervous system (N)", "A": "Digestive & metabolism (A)",
         "R": "Respiratory (R)", "J": "Anti-infectives (J)", "B": "Blood (B)", "C": "Cardiovascular (C)",
         "D": "Dermatology (D)", "M": "Musculo-skeletal (M)", "S": "Sensory organs (S)", "H": "Hormones (H)",
         "P": "Antiparasitics (P)", "G": "Genito-urinary (G)", "V": "Various (V)"}


def fig_growth_by_group(df: pd.DataFrame) -> None:
    d = df.sort_values("change_bn")
    fig, ax = plt.subplots(figsize=(8, 4.4))
    ax.barh([SHORT.get(a, a) for a in d.atc1], d.change_bn, color=[RED if a == "L" else BLUE if v > 0 else GREY for a, v in zip(d.atc1, d.change_bn)])
    total = df.change_bn.sum()
    for i, v in enumerate(d.change_bn):
        ax.text(v + (0.04 if v >= 0 else -0.04), i, f"{v:+.2f}", va="center", ha="left" if v >= 0 else "right", fontsize=8)
    ax.axvline(0, color=INK, lw=0.8); ax.set_xlim(d.change_bn.min() - 0.4, d.change_bn.max() + 0.6)
    ax.set_title(f"Where the extra EUR {total:.1f} bn went (2025 vs 2019, EUR bn)")
    save(fig, "02_growth_by_group")


def molecule_movers(n: int = 12) -> pd.DataFrame:
    """Molecules whose reimbursement grew or fell the most between 2019 and 2025."""
    return q("""
        WITH m AS (
            SELECT molecule,
                   COALESCE(sum(reimbursed) FILTER (WHERE year = 2019), 0) / 1e6 AS m_2019,
                   COALESCE(sum(reimbursed) FILTER (WHERE year = 2025), 0) / 1e6 AS m_2025
            FROM molecule_year GROUP BY molecule)
        SELECT *, m_2025 - m_2019 AS change_m,
               rank() OVER (ORDER BY m_2025 - m_2019 DESC) AS rank_up,
               rank() OVER (ORDER BY m_2025 - m_2019 ASC)  AS rank_down
        FROM m QUALIFY rank_up <= $n OR rank_down <= 6 ORDER BY change_m DESC""", n=n)


USE = {"TAFAMIDIS": "heart amyloidosis", "APIXABAN": "anticoagulant", "IVACAFTOR + TEZACAFTOR + ELEXACAFTOR": "cystic fibrosis",
       "DUPILUMAB": "eczema, asthma", "DAPAGLIFLOZINE": "diabetes, heart failure", "SEMAGLUTIDE": "diabetes (GLP-1)",
       "APALUTAMIDE": "prostate cancer", "ANTIGENE PURIFIE DE VIRUS DU ZONA": "shingles vaccine", "OSIMERTINIB": "lung cancer",
       "EMICIZUMAB": "haemophilia", "VALSARTAN + SACUBITRIL": "heart failure", "AFLIBERCEPT": "eye (AMD)",
       "IVACAFTOR": "cystic fibrosis", "RANIBIZUMAB": "eye (AMD)", "RIVAROXABAN": "anticoagulant",
       "PALBOCICLIB": "breast cancer", "LIRAGLUTIDE": "diabetes (GLP-1)", "FINGOLIMOD": "multiple sclerosis",
       "ABEMACICLIB": "breast cancer", "EVOLOCUMAB": "cholesterol"}


def fig_movers(df: pd.DataFrame) -> None:
    d = df.sort_values("change_m")
    labels = [f"{title_case(m)[:34]}" + (f"  ({USE[m]})" if m in USE else "") for m in d.molecule]
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.barh(labels, d.change_m, color=[RED if v > 0 else BLUE for v in d.change_m])
    for i, (v, a, b) in enumerate(zip(d.change_m, d.m_2019, d.m_2025)):
        ax.text(v + (15 if v >= 0 else -15), i, f"{a:,.0f} -> {b:,.0f}", va="center", ha="left" if v >= 0 else "right", fontsize=7.5, color=INK)
    ax.axvline(0, color=INK, lw=0.8); ax.set_xlim(d.change_m.min() - 260, d.change_m.max() + 330)
    ax.set_xlabel("change in amount reimbursed, 2025 vs 2019 (EUR million)")
    ax.set_title("Biggest movers among molecules (EUR million, 2019 -> 2025)")
    save(fig, "03_molecule_movers")


def concentration() -> pd.DataFrame:
    """How concentrated is spending? Share of the top 10 / top 50 molecules, and how many
    molecules make up half of all spending."""
    return q("""
        WITH r AS (
            SELECT year, molecule, sum(reimbursed) AS rem,
                   row_number() OVER (PARTITION BY year ORDER BY sum(reimbursed) DESC) AS rk,
                   sum(sum(reimbursed)) OVER (PARTITION BY year) AS total,
                   sum(sum(reimbursed)) OVER (PARTITION BY year ORDER BY sum(reimbursed) DESC) AS running
            FROM atc5_mol GROUP BY year, molecule)
        SELECT year, count(*) AS molecules,
               sum(rem) FILTER (WHERE rk <= 10) / any_value(total) AS top10_share,
               sum(rem) FILTER (WHERE rk <= 50) / any_value(total) AS top50_share,
               count(*) FILTER (WHERE running - rem < 0.5 * total) AS molecules_for_half
        FROM r GROUP BY year ORDER BY year""")


# ---------------------------------------------------------------- 2. three stories
def glp1() -> pd.DataFrame:
    """GLP-1 analogues (ATC4 A10BJ: semaglutide, dulaglutide, liraglutide, exenatide).
    Patient counts come from the ATC4 file, so a patient taking two of them counts once.
    The class code exists from 2020 (before, these drugs were filed under A10BX)."""
    return q("""
        SELECT year, sum(patients) / 1e3 AS patients_k, sum(reimbursed) / 1e6 AS reimbursed_m,
               sum(patients) FILTER (WHERE age_group = 60) / sum(patients) AS share_60_plus,
               sum(patients) FILTER (WHERE sex = 2) / sum(patients) AS share_women
        FROM atc4 WHERE atc4 = 'A10BJ' AND year >= 2020 GROUP BY year ORDER BY year""")


def glp1_molecules() -> pd.DataFrame:
    return q("""SELECT year, molecule, sum(patients) / 1e3 AS patients_k FROM atc5_mol
                WHERE molecule IN ('SEMAGLUTIDE', 'DULAGLUTIDE', 'LIRAGLUTIDE', 'EXENATIDE') AND year >= 2020
                GROUP BY ALL ORDER BY year""")


def antibiotics() -> pd.DataFrame:
    """Systemic antibiotics (ATC2 J01): patients by age group, index 2019 = 100."""
    return q("""
        SELECT year, age_group, sum(patients) / 1e6 AS patients_m, sum(boxes) / 1e6 AS boxes_m
        FROM atc2 WHERE atc2 = 'J01' AND age_group IN (0, 20, 60) GROUP BY ALL ORDER BY age_group, year""")


def adhd() -> pd.DataFrame:
    """Methylphenidate (ADHD treatment): children vs adults."""
    return q("""
        SELECT year, age_group, sum(patients) / 1e3 AS patients_k
        FROM atc5_mol WHERE molecule = 'METHYLPHENIDATE' AND age_group IN (0, 20, 60)
        GROUP BY ALL ORDER BY age_group, year""")


def fig_stories(g: pd.DataFrame, gm: pd.DataFrame, ab: pd.DataFrame, ad: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.9))
    a = axes[0]
    w = gm.pivot(index="year", columns="molecule", values="patients_k").fillna(0)[["SEMAGLUTIDE", "DULAGLUTIDE", "LIRAGLUTIDE", "EXENATIDE"]]
    a.stackplot(w.index, w.T.values, labels=[title_case(c) for c in w.columns], colors=[RED, ORANGE, GREY, "#cbd5e1"], alpha=0.9)
    a.plot(g.year, g.patients_k, color=INK, lw=1.5, ls="--", label="patients (class, no double count)")
    a.set_title("GLP-1 analogues: patients (thousands)"); a.legend(fontsize=7, loc="upper left"); a.set_ylim(0, 1250); a.set_xticks(w.index)
    a = axes[1]
    labels = {0: "0-19", 20: "20-59", 60: "60+"}
    for (ag, d), c in zip(ab.groupby("age_group"), (ORANGE, BLUE, PURPLE)):
        a.plot(d.year, 100 * d.patients_m / d.patients_m.iloc[0], marker="o", lw=2, color=c, label=labels[ag])
    a.axhline(100, color=MUTED, lw=0.8, ls="--"); a.set_xticks(YEARS); a.tick_params(axis="x", labelsize=8)
    a.set_title("Antibiotics: patients (index 2019 = 100)"); a.legend(title="age", fontsize=8)
    a = axes[2]
    for (ag, d), c in zip(ad[ad.age_group < 60].groupby("age_group"), (ORANGE, BLUE)):
        a.plot(d.year, d.patients_k, marker="o", lw=2, color=c, label=labels[ag])
    a.set_title("Methylphenidate (ADHD): patients (thousands)"); a.set_xticks(YEARS); a.tick_params(axis="x", labelsize=8)
    a.legend(title="age", fontsize=8)
    save(fig, "04_three_stories")


# ---------------------------------------------------------------- 3. regions
def regions(year: int = 2025) -> pd.DataFrame:
    """Spending per inhabitant by region, crude and age-standardised.

    Crude rate      = spending / population.
    Standardised    = what the region would spend per inhabitant if it had the
                      same age structure as metropolitan France (direct
                      standardisation): sum over age groups of
                      (regional spending per inhabitant of that age) x (national share of that age).
    Open Medic only has three age groups (0-19, 20-59, 60+), so the
    adjustment is coarse but captures the main effect: older regions spend more."""
    return q("""
        WITH r AS (SELECT * FROM region_age WHERE year = $y),
             nat AS (SELECT age_group, sum(population) / (SELECT sum(population) FROM r) AS weight FROM r GROUP BY age_group),
             share60 AS (SELECT region, sum(population) FILTER (WHERE age_group = 60) / sum(population) AS share_60_plus
                         FROM r GROUP BY region)
        SELECT r.region, any_value(r.region_name) AS region_name,
               sum(r.reimbursed) / sum(r.population)                         AS crude_per_inhabitant,
               sum(r.reimbursed / r.population * nat.weight)                 AS standardised_per_inhabitant,
               any_value(s.share_60_plus)                                    AS share_60_plus
        FROM r JOIN nat USING (age_group) JOIN share60 s USING (region)
        GROUP BY r.region ORDER BY standardised_per_inhabitant DESC""", y=year)


def fig_regions(df: pd.DataFrame) -> None:
    gj = json.loads((ROOT / "data" / "raw" / "regions.geojson").read_text(encoding="utf-8"))
    vals = df.set_index("region")["standardised_per_inhabitant"]
    cmap = plt.get_cmap("PuBu"); lo, hi = vals.min(), vals.max()
    fig = plt.figure(figsize=(12, 4.8))
    ax = fig.add_axes([0.0, 0.12, 0.42, 0.8])
    for f in gj["features"]:
        code = int(f["properties"]["code"])
        geoms = f["geometry"]["coordinates"] if f["geometry"]["type"] == "MultiPolygon" else [f["geometry"]["coordinates"]]
        for poly in geoms:
            xy = np.array(poly[0])
            color = cmap(0.15 + 0.85 * (vals[code] - lo) / (hi - lo)) if code in vals.index else "#eeeeee"
            ax.fill(xy[:, 0], xy[:, 1], color=color, ec=INK if code == GRAND_EST else "white", lw=2 if code == GRAND_EST else 0.6,
                    zorder=3 if code == GRAND_EST else 2)
    ax.set_aspect(1 / np.cos(np.radians(46.5))); ax.axis("off")
    ax.set_title("Age-standardised spending per inhabitant, 2025")
    sm = plt.cm.ScalarMappable(cmap=matplotlib.colors.LinearSegmentedColormap.from_list("c", [cmap(0.15), cmap(1.0)]),
                               norm=plt.Normalize(lo, hi))
    cax = fig.add_axes([0.08, 0.06, 0.26, 0.025])
    cb = fig.colorbar(sm, cax=cax, orientation="horizontal"); cb.set_label("EUR per inhabitant", fontsize=8)
    ax2 = fig.add_axes([0.62, 0.12, 0.37, 0.76])
    d = df.sort_values("standardised_per_inhabitant")
    y = np.arange(len(d))
    ax2.scatter(d.crude_per_inhabitant, y, color=GREY, s=30, label="crude", zorder=3)
    ax2.scatter(d.standardised_per_inhabitant, y, color=[RED if r == GRAND_EST else BLUE for r in d.region], s=45,
                label="age-standardised", zorder=4)
    for yi, a, b in zip(y, d.crude_per_inhabitant, d.standardised_per_inhabitant):
        ax2.plot([a, b], [yi, yi], color=GREY, lw=1, zorder=2)
    ax2.set_yticks(y, d.region_name); ax2.set_xlabel("EUR reimbursed per inhabitant")
    ax2.legend(loc="lower right", fontsize=8); ax2.set_title("Crude vs age-standardised (EUR per inhabitant)")
    save(fig, "05_regions")


def age_profile() -> pd.DataFrame:
    """Spending per inhabitant by age group (metropolitan regions, 2025)."""
    return q("""SELECT age_group, sum(reimbursed) / sum(population) AS per_inhabitant, sum(population) / 1e6 AS population_m
                FROM region_age WHERE year = 2025 GROUP BY age_group ORDER BY age_group""")


if __name__ == "__main__":
    RES.mkdir(exist_ok=True)
    pd.set_option("display.width", 160)
    for name, df in (("consistency", consistency()), ("data_quality", data_quality())):
        df.to_csv(RES / f"{name}.csv", index=False); print(df, "\n")
    t = totals(); t.to_csv(RES / "totals.csv", index=False); fig_totals(t); print(t, "\n")
    g = growth_by_group(); g.to_csv(RES / "growth_by_group.csv", index=False); fig_growth_by_group(g); print(g, "\n")
    m = molecule_movers(); m.to_csv(RES / "molecule_movers.csv", index=False); fig_movers(m)
    c = concentration(); c.to_csv(RES / "concentration.csv", index=False); print(c, "\n")
    g1, gm, ab, ad = glp1(), glp1_molecules(), antibiotics(), adhd()
    for name, df in (("glp1", g1), ("antibiotics", ab), ("methylphenidate", ad)):
        df.to_csv(RES / f"{name}.csv", index=False); print(df, "\n")
    fig_stories(g1, gm, ab, ad)
    r = regions(); r.to_csv(RES / "regions_2025.csv", index=False); fig_regions(r); print(r, "\n")
    a = age_profile(); a.to_csv(RES / "age_profile.csv", index=False); print(a)
