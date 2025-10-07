import pandas as pd
from pathlib import Path

# ---------- 1) Load ----------
PATH = "Ancestrydna.txt"  # change if needed (case-sensitive on some systems)

df = pd.read_csv(
    PATH,
    sep="\t",
    comment="#",
    names=["rsid", "chromosome", "position", "allele1", "allele2"],
    dtype=str
)

# Basic sanity prints
print("SUCCESS: file loaded")
print(f"Rows: {len(df):,}")
print(f"Columns: {list(df.columns)}\n")

# Normalize allele strings
for col in ["allele1", "allele2"]:
    df[col] = df[col].astype(str).str.strip().str.upper()

# ---------- 2) Targets & helpers ----------
# Primary SNPs
PRIMARY = {
    "rs1815739": "ACTN3",       # power/endurance (R577X)
    "rs1799752": "ACE",         # I/D; often missing on arrays
    "rs1805086": "MSTN",        # myostatin
    "rs8192678": "PPARGC1A"     # endurance adaptation
}

# Proxies to try if primary not found (ACE I/D ≈ rs4343 A/G; LD varies by population)
PROXIES = {
    "rs1799752": [("rs4343", "proxy for ACE I/D (G≈D, A≈I in many cohorts)")]
}

NO_CALLS = {"-", "--", "0", "NA", "N", ""}

def fetch_genotype(rsid: str):
    """Return normalized genotype like 'CC', 'CT', or 'no-call' if missing/invalid."""
    rows = df[df["rsid"] == rsid]
    if rows.empty:
        return None  # not present
    a1 = rows.iloc[0]["allele1"]
    a2 = rows.iloc[0]["allele2"]
    if a1 in NO_CALLS or a2 in NO_CALLS:
        return "no-call"
    return "".join(sorted([a1, a2]))

def fetch_with_proxy(primary_rsid: str):
    """Try primary; if missing, try proxies (returns (rsid_used, genotype, note))."""
    g = fetch_genotype(primary_rsid)
    if g is not None:
        return (primary_rsid, g, "")
    # try proxies
    for proxy_rsid, note in PROXIES.get(primary_rsid, []):
        pg = fetch_genotype(proxy_rsid)
        if pg is not None:
            return (proxy_rsid, pg, note)
    return (primary_rsid, None, "")

# ---------- 3) Interpretation rules ----------
def interpret_actn3(g):
    # rs1815739 (C/T): CC=functional (power), CT=mixed, TT=non-functional (endurance)
    if g in (None, "no-call"):
        return "ACTN3: unavailable"
    if g == "CC":
        return "ACTN3: CC → fast-twitch/strength bias (functional α-actinin-3)"
    if g == "CT":
        return "ACTN3: CT → mixed profile (both fast/slow features)"
    if g == "TT":
        return "ACTN3: TT → endurance bias (nonfunctional α-actinin-3)"
    return f"ACTN3: {g} (unexpected alleles)"

def interpret_ppargc1a(g):
    # rs8192678 (G/A): G=more oxidative/endurance; A=more glycolytic/strength
    if g in (None, "no-call"):
        return "PPARGC1A: unavailable"
    if g == "AA":
        return "PPARGC1A: AA → glycolytic/strength tilt"
    if g == "AG":
        return "PPARGC1A: AG → mixed"
    if g == "GG":
        return "PPARGC1A: GG → oxidative/endurance tilt"
    return f"PPARGC1A: {g} (unexpected alleles)"

def interpret_mstn(g):
    # rs1805086 (A/G): G is rare, associated with lower myostatin → muscle mass potential
    if g in (None, "no-call"):
        return "MSTN: unavailable"
    if g == "GG":
        return "MSTN: GG → rare; potential for increased muscle mass (myostatin variant)"
    if g == "AG":
        return "MSTN: AG → rare carrier; possible mild effect"
    if g == "AA":
        return "MSTN: AA → typical"
    return f"MSTN: {g} (unexpected alleles)"

def interpret_ace(rsid_used, g):
    # Primary rs1799752 often missing. If proxy rs4343 used: G≈D (power), A≈I (endurance) in many cohorts.
    if g is None:
        return "ACE: not found"
    if g == "no-call":
        return "ACE: no-call"
    if rsid_used == "rs1799752":
        return f"ACE (rs1799752): genotype {g} (I/D calling not directly represented on many arrays)"
    if rsid_used == "rs4343":
        # Map proxy genotype to tendency; this is an approximation.
        if g == "GG":
            return "ACE proxy (rs4343 GG): ≈ DD (power/strength tendency)"
        if g == "AG":
            return "ACE proxy (rs4343 AG): ≈ ID (mixed)"
        if g == "AA":
            return "ACE proxy (rs4343 AA): ≈ II (endurance tendency)"
        return f"ACE proxy (rs4343): genotype {g}"
    return f"ACE: genotype {g}"

# ---------- 4) Pull results ----------
records = []

# ACTN3
actn3 = fetch_genotype("rs1815739")
records.append({
    "gene": "ACTN3", "rsid_used": "rs1815739", "genotype": actn3,
    "interpretation": interpret_actn3(actn3)
})

# ACE (+ proxy)
ace_rsid_used, ace_g, ace_note = fetch_with_proxy("rs1799752")
records.append({
    "gene": "ACE", "rsid_used": ace_rsid_used, "genotype": ace_g,
    "interpretation": interpret_ace(ace_rsid_used, ace_g)
})

# MSTN
mstn = fetch_genotype("rs1805086")
records.append({
    "gene": "MSTN", "rsid_used": "rs1805086", "genotype": mstn,
    "interpretation": interpret_mstn(mstn)
})

# PPARGC1A
ppargc1a = fetch_genotype("rs8192678")
records.append({
    "gene": "PPARGC1A", "rsid_used": "rs8192678", "genotype": ppargc1a,
    "interpretation": interpret_ppargc1a(ppargc1a)
})

panel_df = pd.DataFrame(records, columns=["gene", "rsid_used", "genotype", "interpretation"])
print(panel_df.to_string(index=False), "\n")

# ---------- 5) Simple tendency score (very rough, for illustration only) ----------
score = 0
# ACTN3
if actn3 == "CC": score += 2
elif actn3 == "CT": score += 1
elif actn3 == "TT": score -= 2
# PPARGC1A
if ppargc1a == "AA": score += 1
elif ppargc1a == "GG": score -= 1
# MSTN
if mstn == "GG": score += 2
elif mstn == "AG": score += 1
# ACE proxy
if ace_rsid_used == "rs4343":
    if ace_g == "GG": score += 1
    elif ace_g == "AA": score -= 1

def summarize(score):
    if score >= 3: return "Overall tendency: Strength/Power-leaning"
    if score <= -2: return "Overall tendency: Endurance-leaning"
    return "Overall tendency: Mixed / Balanced"

print(summarize(score))
print("(Note: This is a simplistic, non-medical summary based on a tiny SNP panel.)\n")

# ---------- 6) Save a small CSV report ----------
out_path = Path("strength_panel_report.csv")
panel_df.to_csv(out_path, index=False)
print(f"Saved: {out_path.resolve()}")
