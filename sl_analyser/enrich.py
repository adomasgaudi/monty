import streamlit as st
import pandas as pd
from utils import fetch_user_id, fetch_raw_workouts
from variables import NAME_TO_USERNAME, EXERCISE_DATA
from datetime import datetime, timedelta

def format_date(d: str) -> str:
    return datetime.strptime(d, "%Y-%m-%d").strftime("%b-%d")

def epley3_reps(w: float, w_rec: float, w_i: float) -> float:
    """Estimate reps given weight, 1RM, and internal load."""
    if w is None or w_rec is None or w_i is None:
        return None
    denom = 3.33 * (w + w_i)
    if denom == 0:
        return None
    try:
        reps = (100 * (w_rec + w_i)) / denom - 29
        return round(reps, 2)
    except Exception:
        return None

def epley3_record(w: float, reps: float, w_i: float) -> float:
    """Estimate 1RM given working weight, reps, and internal load."""
    if w is None or reps is None or w_i is None:
        return None
    try:
        return round((3.33 * (w + w_i) * (reps + 29)) / 100 - w_i, 2)
    except ZeroDivisionError:
        return None

def epley3_weight(w_rec: float, reps: float, w_i: float) -> float:
    """Estimate working weight given 1RM, target reps, and internal load."""
    if w_rec is None or reps is None or w_i is None:
        return None
    try:
        return round((100 * (w_rec + w_i)) / (3.33 * (reps + 29)) - w_i, 2)
    except ZeroDivisionError:
        return None


def enrich_workouts_with_bodyweight_load(raw_data):
    """Attach bodyweight contribution and equipment weight to each exercise."""

    # --- local helpers (fully collapsible inside outer function) -----

    def get_bodyweight(workout):
        return float(workout.get("bodyweight") or 0.0)

    def get_exercise_load_params(ex_name):
        name = (ex_name or "").strip()
        data = EXERCISE_DATA.get(name, {})
        bwp = float(data.get("bwp") or 0.0)
        eq_w = float(data.get("eq_w") or 0.0)
        return bwp, eq_w

    def compute_loads(bodyweight, bwp, eq_w):
        bw_load = round(bodyweight * bwp, 2)
        internal = round(bw_load + eq_w, 2)
        return bw_load, internal

    

    # --- main logic --------------------------------------------------

    for workout in raw_data:
        bw = get_bodyweight(workout)
        for exercise in workout.get("exercises", []):
            def attach_fields(exercise, bodyweight):
                bwp, eq_w = get_exercise_load_params(exercise.get("exercise_name", ""))
                bw_load, internal = compute_loads(bodyweight, bwp, eq_w)

                exercise["bodyweight_p"] = bwp
                exercise["bodyweight_load"] = bw_load
                exercise["equipment_weight"] = eq_w
                exercise["internal_load"] = internal
            attach_fields(exercise, bw)

    return raw_data
def enrich_workouts_with_1rm(raw_data):
    """Compute per-set and per-exercise 1RM using modified Epley3 formula."""

    def compute_set_1rm(weight, reps, internal_load):
        if weight > 0 and reps > 0:
            return epley3_record(weight, reps, internal_load)
        return None

    # --- main logic ------------------------------------------------

    for workout in raw_data:
        for exercise in workout.get("exercises", []):
            def process_exercise(exercise):
                internal_load = float(exercise.get("internal_load") or 0.0)
                set_1rms = []

                for s in exercise.get("sets", []):
                    w = float(s.get("weight") or 0.0)
                    r = int(s.get("reps") or 0)

                    one_rm = compute_set_1rm(w, r, internal_load)
                    s["one_rep_max"] = one_rm
                    if one_rm is not None:
                        set_1rms.append(one_rm)

                exercise["one_rep_max"] = max(set_1rms) if set_1rms else None
            process_exercise(exercise)

    return raw_data
def enrich_workouts_with_rir(raw_data):
    """Estimate Reps in Reserve (RIR) for each set based on exercise 1RM."""

    # --- helpers -----------------------------------------------------

    def compute_rir(weight, reps, one_rm, internal_load):
        if weight > 0 and reps > 0 and one_rm is not None:
            max_reps = epley3_reps(weight, one_rm, internal_load)
            if max_reps is None:
                return None, None
            rir = round(max_reps - reps, 2)
            return rir, max_reps
        return None, None

    def process_exercise(exercise):
        one_rm = exercise.get("one_rep_max")
        internal = float(exercise.get("internal_load") or 0.0)
        if one_rm is None:
            return
        for s in exercise.get("sets", []):
            w = float(s.get("weight") or 0.0)
            r = int(s.get("reps") or 0)
            rir, max_reps = compute_rir(w, r, one_rm, internal)
            s["RIR"] = rir
            s["max_reps"] = max_reps

    # --- main logic --------------------------------------------------

    for workout in raw_data:
        for exercise in workout.get("exercises", []):
            process_exercise(exercise)

    return raw_data
def enrich_workouts_with_hard_sets(raw_data):
    """Add count of 'hard sets' to each exercise (reps > 3 and RIR < 3)."""

    # --- helpers -----------------------------------------------------

    def is_hard_set(reps, rir):
        return (reps is not None and rir is not None
                and reps > 3 and rir < 3)

    def process_exercise(exercise):
        count = 0
        for s in exercise.get("sets", []):
            reps = s.get("reps")
            rir = s.get("RIR")
            if is_hard_set(reps, rir):
                count += 1
        exercise["hard_sets"] = count

    # --- main logic --------------------------------------------------

    for workout in raw_data:
        for exercise in workout.get("exercises", []):
            process_exercise(exercise)

    return raw_data
def enrich_workouts_with_volume(raw_data):
    """Compute per-exercise training volume."""

    # --- helpers -----------------------------------------------------

    def compute_volumes(exercise):
        one_rm = float(exercise.get("one_rep_max") or 0.0)
        total = 0.0
        relative = 0.0

        for s in exercise.get("sets", []):
            w = float(s.get("weight") or 0.0)
            r = int(s.get("reps") or 0)
            total += w * r
            if one_rm > 0:
                relative += (w * r) / (one_rm * 0.8)

        return round(total, 0), round(relative, 0)

    def process_exercise(exercise):
        vol_raw, vol_rel = compute_volumes(exercise)
        exercise["volume_raw"] = vol_raw
        exercise["volume_relative"] = vol_rel

    # --- main logic --------------------------------------------------

    for workout in raw_data:
        for exercise in workout.get("exercises", []):
            process_exercise(exercise)

    return raw_data

def enrich_workouts_with_heavy_volume(raw_data):
    """Compute heavy volume (85% & 93%) adjusted for internal load."""

    # --- helpers -----------------------------------------------------
    def calc_thresholds(one_rm, internal_load):
        t85 = (0.85 * (one_rm + internal_load)) - internal_load
        t93 = (0.93 * (one_rm + internal_load)) - internal_load
        return t85, t93

    def score_set(weight, reps, t85, t93):
        if weight > t93:
            return 2 * reps
        if weight > t85:
            return reps
        return 0

    def process_exercise(exercise):
        one_rm = float(exercise.get("one_rep_max") or 0.0)
        internal = float(exercise.get("internal_load") or 0.0)

        if one_rm <= 0:
            exercise["heavy_sets"] = 0
            return

        t85, t93 = calc_thresholds(one_rm, internal)
        score = 0

        for s in exercise.get("sets", []):
            w = float(s.get("weight") or 0.0)
            r = int(s.get("reps") or 0)
            score += score_set(w, r, t85, t93)

        exercise["heavy_sets"] = round(score / 3, 1)

    # --- main logic --------------------------------------------------

    for workout in raw_data:
        for exercise in workout.get("exercises", []):
            process_exercise(exercise)

    return raw_data
