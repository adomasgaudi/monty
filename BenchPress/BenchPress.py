import streamlit as st
import pandas as pd

st.markdown("<h3 style='margin-bottom: 16px;'>Bench Press Calculator</h3>", unsafe_allow_html=True)

# One-row "sheet" input (added Body Part 0–1 + Body Weight kg)
input_df = pd.DataFrame([{
    "Weight (kg)": 60.0,
    "Reps": 1,
    "Body Part (0–1)": 1.00,
    "Body Weight (kg)": 80.0,
}])

edited = st.data_editor(
    input_df,
    num_rows="fixed",
    hide_index=True,
    use_container_width=False,
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
        "Body Part (0–1)": st.column_config.NumberColumn(
            "Body Part (0–1)",
            min_value=0.0,
            max_value=1.0,
            step=0.01,
            format="%.2f",
            width="medium",
        ),
        "Body Weight (kg)": st.column_config.NumberColumn(
            "Body Weight (kg)",
            min_value=20.0,
            max_value=300.0,
            step=0.5,
            format="%.1f",
            width="medium",
        ),
    },
)

# Read values
weight = float(edited.loc[0, "Weight (kg)"])
reps = int(edited.loc[0, "Reps"])
body_part = float(edited.loc[0, "Body Part (0–1)"])
body_weight = float(edited.loc[0, "Body Weight (kg)"])

# Display the results
if st.button("Submit Bench Press Record"):
    estimated_1rm = weight * (reps + 29) / 30
    st.info(f"Your estimated 1RM is approximately {estimated_1rm:.1f} kg")

    # Optional: show extra metrics (uses body weight; doesn't assume meaning for body_part)
    if body_weight > 0:
        st.write(f"Relative strength (1RM / BW): {estimated_1rm / body_weight:.2f}")
    st.write(f"Body Part (0–1): {body_part:.2f}")

    # Warmup routine
    st.subheader("🔥 Warmup Routine")
    warmup_data = {
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
    }
    warmup_df = pd.DataFrame(warmup_data)

    st.markdown(
        """
        <style>
        .dataframe th:nth-child(1), .dataframe td:nth-child(1),
        .dataframe th:nth-child(2), .dataframe td:nth-child(2) {
            font-size: 16px;
            font-weight: bold;
        }
        .dataframe th:nth-child(3), .dataframe td:nth-child(3) {
            font-size: 11px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.dataframe(warmup_df, use_container_width=True, hide_index=True)
    st.write("💡 **Tips:** Take 30-60 seconds of rest between warmup sets. For each rep imagine your lifting your 1 rep max.")

    # Strength training session
    st.subheader("💪 Strength Training Session")
    strength_data = {
        "Reps": ["1", "4", "4"],
        "Weight (kg)": [
            f"{round(estimated_1rm * 0.94):.0f}",
            f"{round(estimated_1rm * 0.88):.0f}",
            f"{round(estimated_1rm * 0.87):.0f}",
        ],
        "Percentage": ["94%", "88%", "87%"],
    }
    strength_df = pd.DataFrame(strength_data)
    st.dataframe(strength_df, use_container_width=True, hide_index=True)
    st.write("💡 **Tips:** Take 2-7 minutes of rest between strength sets. Focus on perfect form and explosive movement.")