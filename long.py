import io
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Strength vs Endurance DNA Panel", page_icon="💪", layout="centered")
st.title("💪 Strength vs Endurance — DNA Panel (Ancestry/23andMe)")
st.caption("Upload your raw DNA text file. We’ll parse common formats, read a small trait panel, and summarize tendencies. Not medical advice.")

f = st.file_uploader("Upload raw DNA file (.txt)", type=["txt"])
if not f:
    st.stop()

# ---------- Load with robust column handling ----------
raw = f.getvalue().decode("utf-8", errors="ignore")
buf = io.StringIO(raw)

# Try header=0 then fallback to no header
def load_df(b):
    b.seek(0)
    try:
        df0 = pd.read_csv(b, sep="\t", comment="#", header=0, dtype=str, low_memory=False)
        return df0
    except Exception:
        b.seek(0)
        df1 = pd.read_csv(b, sep="\t", comment="#", header=None, dtype=str, low_memory=False)
        # Best guess for common 4/5-column formats
        if df1.shape[1] == 5:
            df1.columns = ["rsid","chromosome","position","allele1","allele2"]
        elif df1.shape[1] == 4:
            df1.columns = ["rsid","chromosome","position","genotype"]
        return df1

df = load_df(buf)

# normalize column names to lowercase
df.columns = [c.strip().lower() for c in df.columns]
# standardize expected names if user has variations (e.g., "chrom" vs "chromosome")
ren = {}
if "chrom" in df.columns and "chromosome" not in df.columns: ren["chrom"] = "chromosome"
if "pos" in df.columns and "position" not in df.columns: ren["pos"] = "position"
df.rename(columns=ren, inplace=True)

# enforce string & uppercase where relevant
for c in df.columns:
    df[c] = df[c].astype(str).str.strip()
if "rsid" in df.columns:
    df["rsid"] = df["rsid"].str.strip()

for c in ["allele1","allele2","genotype"]:
    if c in df.columns:
        df[c] = df[c].str.upper()

st.write(f"Parsed rows: **{len(df):,}**")
st.caption(f"Columns detected: {list(df.columns)}")

# ---------- Helpers ----------
NO_CALLS = {"-", "--", "0", "NA", "N", "", "NN"}
COMP = {"A":"T","T":"A","C":"G","G":"C"}

def split_genotype(gt):
    """Convert 'CT' -> ('C','T'); 'C/T' -> ('C','T'); handle no-calls."""
    if gt is None: return None, None
    gt = gt.replace("/", "").replace("|", "").strip().upper()
    if gt in NO_CALLS or len(gt) == 0: return "no-call", "no-call"
    if len(gt) == 1: return gt, gt
    return gt[0], gt[1]

def get_genotype(rsid):
    """Return normalized genotype like 'CC', 'CT', 'no-call', or None if rsid missing."""
    if "rsid" not in df.columns: return None
    rows = df[df["rsid"] == rsid]
    if rows.empty: return None

    # Prefer allele1/allele2 if present; fallback to genotype
    if "allele1" in df.columns and "allele2" in df.columns:
        a1 = rows.iloc[0]["allele1"].upper()
        a2 = rows.iloc[0]["allele2"].upper()
    elif "genotype" in df.columns:
        a1, a2 = split_genotype(rows.iloc[0]["genotype"])
    else:
        return None

    if a1 in NO_CALLS or a2 in NO_CALLS:
        return "no-call"
    return "".join(sorted([a1, a2]))

def harmonize(rsid, g, canon):
    """Map observed genotype to canonical allele space (A/G; complements allowed)."""
    if g in (None, "no-call"): return g
    a,b = g[0], g[1]
    if a in canon and b in canon:
        return "".join(sorted([a,b]))
    # try complement
    ac, bc = COMP.get(a, a), COMP.get(b, b)
    if ac in canon and bc in canon:
        return "".join(sorted([ac, bc]))
    return "".join(sorted([a,b]))  # leave as-is if uncertain

# ---------- Panel (expanded) ----------
# Primary strength/endurance markers + a few commonly discussed performance SNPs
PANEL = [
    # gene, rsid, canonical alleles set, scoring function (for simple tendency)
    ("ACTN3",    "rs1815739", {"C","T"}),         # R577X: C=functional (power), T=endurance tilt
    ("ACE",      "rs4343",    {"A","G"}),         # proxy for I/D: G≈D (power), A≈I (endurance)
    ("PPARGC1A", "rs8192678", {"A","G"}),         # Gly482Ser: A=strength-lean, G=endurance-lean
    ("MSTN",     "rs1805086", {"A","G"}),         # myostatin variant (rare G)
    ("CKM",      "rs8111989", {"A","G"}),         # muscle energy metabolism; G often linked to power
    ("AMPD1",    "rs17602729",{"C","T"}),         # AMPD1 deficiency (TT rare; affects fatigue)
    ("HIF1A",    "rs11549465",{"C","T"}),         # oxygen signaling; T linked to power in some cohorts
    ("NOS3",     "rs2070744", {"C","T"}),         # endothelial NO synthase; C often endurance-lean
    ("VEGFA",    "rs2010963", {"C","G"}),         # angiogenesis; G sometimes power, C endurance (mixed evidence)
    ("BDNF",     "rs6265",    {"C","T"}),         # recovery/learning; T may reduce neurotrophic response
    ("ADRB2",    "rs1042713", {"A","G"}),         # beta-2 receptor; power/exercise response variability
    ("ADRB2",    "rs1042714", {"C","G"}),         # beta-2 receptor; exercise/catecholamine response
    ("COL5A1",   "rs12722",   {"C","T"}),         # tendon/ligament injury risk (connective tissue)
    ("COL1A1",   "rs1800012", {"G","T"}),         # connective tissue remodeling
]

def interpret(gene, rsid, g):
    if g is None: return f"{gene}: not found"
    if g == "no-call": return f"{gene}: no-call"

    if gene == "ACTN3":
        return {"CC":"ACTN3: CC → fast-twitch/strength bias",
                "CT":"ACTN3: CT → mixed",
                "TT":"ACTN3: TT → endurance bias"}.get(g, f"ACTN3: {g}")

    if gene == "ACE":  # rs4343 proxy ≈ I/D
        return {"GG":"ACE proxy (≈DD): strength/power tilt",
                "AG":"ACE proxy (≈ID): mixed",
                "AA":"ACE proxy (≈II): endurance tilt"}.get(g, f"ACE proxy: {g}")

    if gene == "PPARGC1A":
        return {"AA":"PPARGC1A: AA → glycolytic/strength tilt",
                "AG":"PPARGC1A: AG → mixed",
                "GG":"PPARGC1A: GG → oxidative/endurance tilt"}.get(g, f"PPARGC1A: {g}")

    if gene == "MSTN":
        return {"GG":"MSTN: GG → rare; potential ↑ muscle mass",
                "AG":"MSTN: AG → rare carrier",
                "AA":"MSTN: AA → typical"}.get(g, f"MSTN: {g}")

    # Lite interpretations (directional, literature varies by cohort)
    LITE = {
        "CKM":      {"GG":"CKM: GG → power-lean", "AG":"CKM: AG → mixed", "AA":"CKM: AA → endurance-lean"},
        "AMPD1":    {"CC":"AMPD1: CC → typical", "CT":"AMPD1: CT → carrier (fatigue risk in long events)", "TT":"AMPD1: TT → deficiency (rare)"},
        "HIF1A":    {"TT":"HIF1A: TT → power-lean", "CT":"HIF1A: CT → mixed", "CC":"HIF1A: CC → typical"},
        "NOS3":     {"CC":"NOS3: CC → endurance-lean", "CT":"NOS3: CT → mixed", "TT":"NOS3: TT → power-lean"},
        "VEGFA":    {"GG":"VEGFA: GG → power-lean", "CG":"VEGFA: CG → mixed", "CC":"VEGFA: CC → endurance-lean"},
        "BDNF":     {"CC":"BDNF: CC → typical neuroplastic response", "CT":"BDNF: CT → slightly reduced", "TT":"BDNF: TT → reduced"},
        "ADRB2_2713":{"GG":"ADRB2 rs1042713: GG → power-lean", "AG":"ADRB2 rs1042713: AG → mixed", "AA":"ADRB2 rs1042713: AA → endurance-lean"},
        "ADRB2_2714":{"GG":"ADRB2 rs1042714: GG → power-lean", "CG":"ADRB2 rs1042714: CG → mixed", "CC":"ADRB2 rs1042714: CC → endurance-lean"},
        "COL5A1":   {"TT":"COL5A1: TT → ↑ tendon stiffness (injury risk)", "CT":"COL5A1: CT → intermediate", "CC":"COL5A1: CC → typical"},
        "COL1A1":   {"TT":"COL1A1: TT → altered collagen remodeling", "GT":"COL1A1: GT → intermediate", "GG":"COL1A1: GG → typical"},
    }

    key = gene
    if gene == "ADRB2" and rsid == "rs1042713": key = "ADRB2_2713"
    if gene == "ADRB2" and rsid == "rs1042714": key = "ADRB2_2714"
    table = LITE.get(key, {})
    return table.get(g, f"{gene}: {g}")

def score_gene(gene, g):
    if g in (None, "no-call"): return 0
    # Simple, illustrative scoring
    if gene == "ACTN3":
        return 2 if g == "CC" else (1 if g == "CT" else -2 if g == "TT" else 0)
    if gene == "ACE":
        return 1 if g == "GG" else (-1 if g == "AA" else 0)
    if gene == "PPARGC1A":
        return 1 if g == "AA" else (-1 if g == "GG" else 0)
    if gene == "MSTN":
        return 2 if g == "GG" else (1 if g == "AG" else 0)
    if gene in {"CKM","HIF1A","ADRB2"}:
        # treat 'power' homozygote as +1, mixed 0, endurance homozygote -1
        power_hom = {"CKM":"GG", "HIF1A":"TT"}
        if gene == "ADRB2":  # not precise; we treat GG at 2713 and GG at 2714 as power-lean
            return 1 if g == "GG" else (-1 if g in {"AA","CC"} else 0)
        if g == power_hom.get(gene, ""): return 1
        if g in {"AG","CG"}: return 0
        return -1
    if gene in {"NOS3","VEGFA"}:
        # endurance homozygote +1 for endurance (map to -1 for strength)
        endo_hom = {"NOS3":"CC", "VEGFA":"CC"}
        if g == endo_hom.get(gene, ""): return -1
        if g in {"CT","CG"}: return 0
        return 1
    return 0

# ---------- Compute ----------
rows = []
strength_score = 0
found = 0
notfound = 0

for gene, rsid, canon in PANEL:
    g_obs = get_genotype(rsid)
    g_h = harmonize(rsid, g_obs, canon)
    if g_obs is None: notfound += 1
    else: found += 1
    strength_score += score_gene(gene, g_h)
    rows.append({
        "gene": gene,
        "rsid": rsid,
        "genotype_raw": g_obs,
        "genotype": g_h,
        "interpretation": interpret(gene, rsid, g_h),
    })

panel_df = pd.DataFrame(rows, columns=["gene","rsid","genotype","interpretation","genotype_raw"])
panel_df = panel_df[["gene","rsid","genotype","interpretation","genotype_raw"]]

st.subheader("Panel Results")
st.dataframe(panel_df, use_container_width=True)

def overall(s):
    if s >= 4: return "Overall tendency: Strength/Power-leaning"
    if s <= -3: return "Overall tendency: Endurance-leaning"
    return "Overall tendency: Mixed / Balanced"

st.success(overall(strength_score))
st.caption(f"Found: {found} markers · Not found: {notfound} · Simple illustrative scoring (cohort-dependent).")

st.download_button(
    "⬇️ Download CSV report",
    data=panel_df.to_csv(index=False).encode("utf-8"),
    file_name="strength_panel_report.csv",
    mime="text/csv"
)
