import io
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Strength Genetics Mini", page_icon="💪", layout="centered")
st.title("💪 Strength vs Endurance — Mini DNA Panel")
st.caption("Upload your AncestryDNA / 23andMe raw file (.txt). We read ~4 SNPs for a simple tendency. Not medical advice.")

# ---- Upload ----
f = st.file_uploader("Upload your raw DNA file (.txt)", type=["txt"])
if not f:
    st.stop()

# ---- Load (tab-delimited with # comments) ----
content = io.StringIO(f.getvalue().decode("utf-8", errors="ignore"))
try:
    df = pd.read_csv(content, sep="\t", comment="#", header=0, dtype=str)
    if "rsid" not in df.columns:  # handle files without header row
        content.seek(0)
        df = pd.read_csv(content, sep="\t", comment="#", header=None, dtype=str,
                         names=["rsid","chromosome","position","allele1","allele2"])
except Exception:
    st.error("Could not parse file. Make sure it's the raw text export (tab-delimited).")
    st.stop()

for c in ["allele1","allele2","rsid"]:
    if c in df.columns:
        df[c] = df[c].astype(str).str.strip().str.upper()

# ---- Helpers ----
NO_CALLS = {"-", "--", "0", "NA", "N", ""}

def fetch(rsid: str):
    rows = df[df["rsid"] == rsid]
    if rows.empty: return None
    a1, a2 = rows.iloc[0]["allele1"], rows.iloc[0]["allele2"]
    if a1 in NO_CALLS or a2 in NO_CALLS: return "no-call"
    return "".join(sorted([a1, a2]))

# Canonical allele sets for harmonization (PPARGC1A/MSTN often appear complemented on some arrays)
CANON = {
    "rs1815739": {"C","T"},  # ACTN3
    "rs4343":    {"A","G"},  # ACE proxy for I/D
    "rs1805086": {"A","G"},  # MSTN
    "rs8192678": {"A","G"},  # PPARGC1A
}
COMP = {"A":"T","T":"A","C":"G","G":"C"}

def harmonize(rsid, g):
    if g in (None, "no-call"): return g
    a,b = g[0], g[1]
    canon = CANON.get(rsid)
    if not canon: return g
    obs = {a,b}
    if obs.issubset(canon): return "".join(sorted([a,b]))
    comp = {COMP.get(a,a), COMP.get(b,b)}
    if comp.issubset(canon):
        return "".join(sorted([COMP.get(a,a), COMP.get(b,b)]))
    return "".join(sorted([a,b]))

# ---- Targets ----
panel = [
    ("ACTN3",    "rs1815739"),             # R577X — power vs endurance
    ("ACE",      "rs4343"),                # proxy for I/D (G≈D, A≈I)
    ("MSTN",     "rs1805086"),             # myostatin variant
    ("PPARGC1A", "rs8192678"),             # endurance adaptation
]

# ---- Interpretations ----
def interp(gene, rsid, g):
    if g is None:        return f"{gene}: not found"
    if g == "no-call":   return f"{gene}: no-call"

    if gene == "ACTN3":              # rs1815739 C/T
        return {"CC":"ACTN3: CC → fast-twitch/strength bias",
                "CT":"ACTN3: CT → mixed",
                "TT":"ACTN3: TT → endurance bias"}.get(g, f"ACTN3: {g}")
    if gene == "ACE":                # rs4343 A/G proxy ≈ I/D
        return {"GG":"ACE proxy (≈DD): strength/power tilt",
                "AG":"ACE proxy (≈ID): mixed",
                "AA":"ACE proxy (≈II): endurance tilt"}.get(g, f"ACE proxy: {g}")
    if gene == "MSTN":               # rs1805086 A/G
        return {"GG":"MSTN: GG → rare; potential ↑ muscle mass",
                "AG":"MSTN: AG → rare carrier",
                "AA":"MSTN: AA → typical"}.get(g, f"MSTN: {g}")
    if gene == "PPARGC1A":           # rs8192678 A/G
        return {"AA":"PPARGC1A: AA → glycolytic/strength tilt",
                "AG":"PPARGC1A: AG → mixed",
                "GG":"PPARGC1A: GG → oxidative/endurance tilt"}.get(g, f"PPARGC1A: {g}")
    return f"{gene}: {g}"

# ---- Compute panel ----
records = []
score = 0

for gene, rsid in panel:
    g_raw = fetch(rsid)
    g = harmonize(rsid, g_raw)

    # scoring (rough illustrative weights)
    if gene == "ACTN3":
        if g == "CC": score += 2
        elif g == "CT": score += 1
        elif g == "TT": score -= 2
    elif gene == "PPARGC1A":
        if g == "AA": score += 1
        elif g == "GG": score -= 1
    elif gene == "MSTN":
        if g == "GG": score += 2
        elif g == "AG": score += 1
    elif gene == "ACE":
        if g == "GG": score += 1
        elif g == "AA": score -= 1

    records.append({
        "gene": gene,
        "rsid_used": rsid,
        "genotype_raw": g_raw,
        "genotype": g,
        "interpretation": interp(gene, rsid, g)
    })

panel_df = pd.DataFrame(records, columns=["gene","rsid_used","genotype","interpretation","genotype_raw"])
panel_df = panel_df[["gene","rsid_used","genotype","interpretation","genotype_raw"]]

# ---- Summary ----
def summary(s):
    if s >= 3:  return "Overall tendency: Strength/Power-leaning"
    if s <= -2: return "Overall tendency: Endurance-leaning"
    return "Overall tendency: Mixed / Balanced"

st.subheader("Results")
st.dataframe(panel_df, use_container_width=True)
st.success(summary(score))
st.caption("Tiny SNP panel for illustration. Non-diagnostic; training, nutrition, sleep dominate outcomes.")

# ---- Download CSV ----
st.download_button(
    label="⬇️ Download CSV report",
    data=panel_df.to_csv(index=False).encode("utf-8"),
    file_name="strength_panel_report.csv",
    mime="text/csv"
)
