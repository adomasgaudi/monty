# styles.py

def load_styles():
    return """
<style>
div[data-baseweb="select"] > div {
    width: fit-content !important;
    min-width: 180px !important;
    max-width: 90vw !important;
}
.stSelectbox { padding-left: 5px; padding-right: 5px; }
.stSelectbox > div > div { display: inline-block !important; }
[data-testid="stFormSubmitButton"], .stButton button {
    width: fit-content !important;
    padding: 0.4rem 1rem !important;
}

h3 {
    font-size: 1.2rem !important;
    font-weight: 600 !important;
}

.subheader-date {
    font-size: 1.6rem !important;
    font-weight: 700 !important;
    color: darkred !important;
    margin-top: 0.8rem !important;
    margin-bottom: 0.3rem !important;
}

.subheader-exercise {
    font-size: 1.2rem !important;
    font-weight: 600 !important;
    color: white !important;
    margin-top: 0.2rem !important;
    margin-bottom: 0.3rem !important;
}
</style>
"""
