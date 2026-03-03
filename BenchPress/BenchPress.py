import streamlit as st
import pandas as pd
from utils import h3_title, page_setup, InputTable, record






DETAILS_COLS = {
    "BWP": dict(
        label="Scale KG",
        step=0.1,
        format="%.1f",
        width="small",
    ),
    "BPart": dict(
        label="Body Part 0–1",
        step=0.01,
        format="%.2f",
        width="small",
    ),
}
RECORD_COLS = {
    "W_Lift": dict(
        label="W_Lift",
        step=2.5,
        format="%.1f",
        width="small",
    ),
    "Reps": dict(
        label="Reps",
        step=1,
        format="%d",
        width="small",
    ),
}
METRIC_COLS = {
    "Estimated 1RM (kg)": dict(
        label="Estimated 1RM (kg)", 
        format="%.1f", 
        width="medium"
    ),
    "1RM/BW": dict(
        label="1RM/BW", 
        format="%.2f", 
        width="small"
    ),
    "BPart": dict(
        label="BPart", 
        format="%.2f", 
        width="small"
    ),
}

input_record_df = pd.DataFrame([{"W_Lift": 60.0, "Reps": 1}])
input_details_df = pd.DataFrame([{"BWP": 80.0, "BPart": 0.00}])










page_setup()
h3_title("Bench Press Calculator")
st.divider()

# --- INPUTS ---
detailsTable = InputTable(
    input_details_df,
    key="details_editor",
    cols=DETAILS_COLS,
)
recordTable = InputTable(
    input_record_df,
    key="record_editor",
    cols=RECORD_COLS,
)








# /////////////////////////////////////////////////////////









weight = float(recordTable.loc[0, "W_Lift"])
reps = int(recordTable.loc[0, "Reps"])
body_weight = float(detailsTable.loc[0, "BWP"])
body_part = float(detailsTable.loc[0, "BPart"])

recordW = record(weight, reps)

metrics_df = pd.DataFrame([{
        "Record": recordW,
        "Rec/BW": (recordW / body_weight) if body_weight > 0 else None,
        "BPart": body_part,
    }])

WARMUP_COLS = {
        "Reps": ["10", "8", "5", "4", "1", "1"],
        "W_Lift": [
            f"{round(recordW * 0.30 / 5) * 5:.0f}",
            f"{round(recordW * 0.50 / 5) * 5:.0f}",
            f"{round(recordW * 0.60 / 2.5) * 2.5:.1f}",
            f"{round(recordW * 0.70 / 2.5) * 2.5:.1f}",
            f"{round(recordW * 0.85):.0f}",
            f"{round(recordW * 0.87):.0f}",
        ],
        "Percentage": ["30%", "50%", "60%", "70%", "85%", "87%"],
    }






# /////////////////////////////////////////////////////////////////






InputTable(
        metrics_df,
        key="metrics_editor",
        cols=METRIC_COLS
    )
def toggle_routines():
    st.session_state.show_routines = not st.session_state.get("show_routines", False)
    st.rerun()

if "show_routines" not in st.session_state:
    st.session_state.show_routines = False

st.button(
    "Hide Routines" if st.session_state.show_routines else "Show Routines",
    type="secondary",
    on_click=toggle_routines,
)

if st.session_state.show_routines:
    st.subheader("Warmup Routine")
    warmup_df = pd.DataFrame(WARMUP_COLS)
    st.dataframe(warmup_df, use_container_width=True, hide_index=True)
    st.caption("Take 30–60s rest between warmup sets. Treat every rep like practice for your max.")

    st.subheader("💪 Strength Training Session")
    strength_df = pd.DataFrame({
        "Reps": ["1", "4", "4"],
        "W_Lift": [
            f"{round(recordW * 0.94):.0f}",
            f"{round(recordW * 0.88):.0f}",
            f"{round(recordW * 0.87):.0f}",
        ],
        "Percentage": ["94%", "88%", "87%"],
    })
    st.dataframe(strength_df, use_container_width=True, hide_index=True)
    st.caption("Take 2–7 min rest between strength sets. Perfect form. Explosive intent.")