import streamlit as st
import pandas as pd
from utils import page_setup, data_editor1



page_setup()

# --- INPUTS ---
input_record_df = pd.DataFrame([{"W_Lift": 60.0, "Reps": 1}])
input_details_df = pd.DataFrame([{"BWP": 80.0, "BPart": 0.00}])

st.markdown('<div class="input-grid">', unsafe_allow_html=True)

edited_details = data_editor1(
    input_details_df,
    key="details_editor",
    cols={
        "BWP": dict(
            label="Scale KG",
            min_value=1.0,
            max_value=1000.0,
            step=0.1,
            format="%.1f",
            width="small",
        ),
        "BPart": dict(
            label="Body Part 0–1",
            min_value=0.0,
            max_value=1.0,
            step=0.01,
            format="%.2f",
            width="small",
        ),
    },
)

edited_record = data_editor1(
    input_record_df,
    key="record_editor",
    cols={
        "W_Lift": dict(
            label="W_Lift",
            min_value=0.0,
            max_value=500.0,
            step=2.5,
            format="%.1f",
            width="small",
        ),
        "Reps": dict(
            label="Reps",
            min_value=1,
            max_value=50,
            step=1,
            format="%d",
            width="small",
        ),
    },
)

st.markdown("</div>", unsafe_allow_html=True)

# Read values
weight = float(edited_record.loc[0, "W_Lift"])
reps = int(edited_record.loc[0, "Reps"])
body_weight = float(edited_details.loc[0, "BWP"])
body_part = float(edited_details.loc[0, "BPart"])

st.divider()

if st.button("Submit Record", type="primary"):
    estimated_1rm = weight * (reps + 29) / 30

    # --- METRICS (cells, no wrapping) ---
    metrics_df = pd.DataFrame([{
        "Estimated 1RM (kg)": estimated_1rm,
        "1RM/BW": (estimated_1rm / body_weight) if body_weight > 0 else None,
        "BPart": body_part,
    }])

    st.markdown('<div class="metric-grid">', unsafe_allow_html=True)
    data_editor1(
        metrics_df,
        key="metrics_editor",
        disabled=True,
        cols={
            "Estimated 1RM (kg)": dict(label="Estimated 1RM (kg)", format="%.1f", width="medium"),
            "1RM/BW": dict(label="1RM/BW", format="%.2f", width="small"),
            "BPart": dict(label="BPart", format="%.2f", width="small"),
        },
    )
    st.markdown("</div>", unsafe_allow_html=True)

    # Warmup routine
    st.subheader("🔥 Warmup Routine")
    warmup_df = pd.DataFrame({
        "Reps": ["10", "8", "5", "4", "1", "1"],
        "W_Lift": [
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
        "W_Lift": [
            f"{round(estimated_1rm * 0.94):.0f}",
            f"{round(estimated_1rm * 0.88):.0f}",
            f"{round(estimated_1rm * 0.87):.0f}",
        ],
        "Percentage": ["94%", "88%", "87%"],
    })
    st.dataframe(strength_df, use_container_width=True, hide_index=True)
    st.caption("Take 2–7 min rest between strength sets. Perfect form. Explosive intent.")