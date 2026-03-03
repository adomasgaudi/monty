import streamlit as st
import pandas as pd

def InputTable(
    df: pd.DataFrame,
    *,
    cols: dict,          # { "df_col_name": {NumberColumn kwargs...}, ... }
    key: str,
    disabled: bool = False,
):
    column_config = {df_col: st.column_config.NumberColumn(**cfg) for df_col, cfg in cols.items()}
    return st.data_editor(
        df,
        num_rows="fixed",
        hide_index=True,
        use_container_width=True,
        column_config=column_config,
        disabled=disabled,
        key=key,
    )


def page_setup(
    title: str = "Bench Press Calculator",
    *,
    icon: str = "🏋️",
    layout: str = "wide",
    metric_max_width_px: int = 900,
    hide_toolbars: bool = True,
):
    st.set_page_config(page_title=title, page_icon=icon, layout=layout)

def h3_title(title: str, *, margin_bottom_px: int = 16):
    st.markdown(
        f'<h3 style="margin: 0 0 {margin_bottom_px}px 0;">{title}</h3>',
        unsafe_allow_html=True,
    )   

def record(w: float, r: float):
    return w * (r + 29) / 30

def recordB50(w: float, w_iq: float, reps: float) -> float:
    xrm = (153196 / (reps + 20.1)) ** (1.0 / 1.8) - 39.0
    return 100.0 * (w + w_iq) / xrm - w_iq

# end