import streamlit as st
import pandas as pd
import numpy as np

st.title("🏋️ Bench Press Calculator")

# Create two columns for weight and reps input
col1, col2 = st.columns(2)

with col1:
    weight = st.number_input(
        "Enter your best bench press weight (kg):",
        min_value=0.0,
        max_value=500.0,
        value=60.0,
        step=2.5,
        help="Enter the weight in kilograms"
    )

with col2:
    reps = st.number_input(
        "Enter the number of reps:",
        min_value=1,
        max_value=50,
        value=1,
        step=1,
        help="How many reps did you complete?"
    )

# Display the results
if st.button("Submit Bench Press Record"):
    estimated_1rm = weight * (1 + (reps / 30))
    st.info(f"Your estimated 1RM is approximately {estimated_1rm:.1f} kg")
    
    # Create warmup routine table
    st.subheader("🔥 Warmup Routine")
    
    warmup_data = {
        'Reps': ['10', '8', '5', '4', '1', '1'],
        'Weight (kg)': [
            f"{round(estimated_1rm * 0.30 / 5) * 5:.0f}",
            f"{round(estimated_1rm * 0.50 / 5) * 5:.0f}",
            f"{round(estimated_1rm * 0.60 / 2.5) * 2.5:.1f}",
            f"{round(estimated_1rm * 0.70 / 2.5) * 2.5:.1f}",
            f"{round(estimated_1rm * 0.85):.0f}",
            f"{round(estimated_1rm * 0.87):.0f}"
        ],
        'Percentage': ['30%', '50%', '60%', '70%', '85%', '87%']
    }
    
    warmup_df = pd.DataFrame(warmup_data)
    
    # Add custom CSS for font sizing
    st.markdown("""
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
    """, unsafe_allow_html=True)
    
    st.dataframe(warmup_df, use_container_width=True, hide_index=True)
    
    st.write("💡 **Tips:** Take 30-60 seconds of rest between warmup sets. For each rep imagine your lifting your 1 rep max.")
    
    

