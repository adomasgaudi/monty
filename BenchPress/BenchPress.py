import streamlit as st
import pandas as pd

st.set_page_config(page_title="Bench Press Calculator", page_icon="🏋️", layout="wide")

# Title (smaller + space under)
st.markdown("<h3 style='margin: 0 0 16px 0;'>Bench Press Calculator</h3>", unsafe_allow_html=True)

# Hide the top-right toolbar icons for ONLY the input tables
st.markdown(
    """
    <style>
    .input-grid div[data-testid="stElementToolbar"] { display: none !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Input tables (split into Record + Details) ---
inputRecord_df = pd.DataFrame([{
    "Weight (kg)": 60.0,
    "Reps": 1,
}])

inputDetails_df = pd.DataFrame([{
    "BW (kg)": 80.0,
    "Body Part (0–1)": 0.00,
}])

st.markdown('<div class="input-grid">', unsafe_allow_html=True)

editedDetails = st.data_editor(
    inputDetails_df,
    num_rows="fixed",
    hide_index=True,
    use_container_width=True,
    column_config={
        "BW (kg)": st.column_config.NumberColumn(
            "BW (kg)",
            min_value=20.0,
            max_value=300.0,
            step=0.5,
            format="%.1f",
            width="small",
        ),
        "Body Part (0–1)": st.column_config.NumberColumn(
            "Body Part (0–1)",
            min_value=0.0,
            max_value=1.0,
            step=0.01,
            format="%.2f",
            width="small",
        ),
    },
)

editedRecord = st.data_editor(
    inputRecord_df,
    num_rows="fixed",
    hide_index=True,
    use_container_width=True,
    column_config={
        "Weight (kg)": st.column_config.NumberColumn(
            "Weight (kg)",
            min_value=0.0,
            max_value=500.0,
            step=2.5,
            format="%.1f",
            width="small",
        ),
        "Reps": st.column_config.NumberColumn(
            "Reps",
            min_value=1,
            max_value=50,
            step=1,
            format="%d",
            width="small",
        ),
    },
)

st.markdown("</div>", unsafe_allow_html=True)

# Read values (IMPORTANT: read from the right editor)
weight = float(editedRecord.loc[0, "Weight (kg)"])
reps = int(editedRecord.loc[0, "Reps"])
body_weight = float(editedDetails.loc[0, "BW (kg)"])
body_part = float(editedDetails.loc[0, "Body Part (0–1)"])

st.divider()

if st.button("Submit Bench Press Record", type="primary"):
    estimated_1rm = weight * (reps + 29) / 30

    c1, c2, c3 = st.columns(3)
    c1.metric("Estimated 1RM", f"{estimated_1rm:.1f} kg")
    c2.metric("Relative strength (1RM/BW)", f"{(estimated_1rm / body_weight):.2f}" if body_weight > 0 else "—")
    c3.metric("Body Part (0–1)", f"{body_part:.2f}")

    # Warmup routine
    st.subheader("🔥 Warmup Routine")
    warmup_df = pd.DataFrame({
        "Reps": ["10", "8", "5", "4", "1", "1"],
        "Weight (kg)": [
            f"{round(estimated_1rm * 0.30 / 5) * 5:.0f}",
            f"{round(estimated_1rm * 0.50 / 5) * 5:.0f}",
            f"{round(estimated_1rm * 0.60 / 2.5) * 2.5:.1f}",
            f"{round(estimated_1rm * 0.70 / 2.5) * 2.5:.1f}",
            f"{round(estimated_1rm * 0.85):.0f}",
            f"{round(estimated_1rm * 0.87):.0f}",
        ],
        "Percentage": ["30%", "50%", "60%", "70%", "85%", "87%"],
    })
    st.dataframe(warmup_df, use_container_width=True, hide_index=True)
    st.caption("Take 30–60s rest between warmup sets. Treat every rep like practice for your max.")

    # Strength training session
    st.subheader("💪 Strength Training Session")
    strength_df = pd.DataFrame({
        "Reps": ["1", "4", "4"],
        "Weight (kg)": [
            f"{round(estimated_1rm * 0.94):.0f}",
            f"{round(estimated_1rm * 0.88):.0f}",
            f"{round(estimated_1rm * 0.87):.0f}",
        ],
        "Percentage": ["94%", "88%", "87%"],
    })
    st.dataframe(strength_df, use_container_width=True, hide_index=True)
    st.caption("Take 2–7 min rest between strength sets. Perfect form. Explosive intent.")