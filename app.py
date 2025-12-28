
"""
H-1B (weighted tickets) win-rate calculator for the 2-round lottery:
- Round 1: Regular cap (e.g., 65,000) among ALL tickets (Bachelors + Masters/PhD)
- Round 2: Masters cap (e.g., 20,000) among remaining Masters/PhD candidates

You can run many "scenarios" by changing:
- total_unique: total numbers of applicants (e.g., 320,711)
- cap_regular / cap_masters (e.g., 65k + 20k)
- bachelor_share vs masters_share (e.g., 64.4% vs 35.6%)
- wage-level shares within each degree group
- probability method (default "independent")

Note: Ticket multipliers are FIXED by policy here:
WL1..WL4 => 1..4 tickets respectively.

UI features:
1) Preset auto-switch: if you start from a preset and change any input, the preset will auto-switch to "Custom".
2) Compare mode: optional side-by-side comparison of two scenarios (A vs B), including deltas.
"""

import streamlit as st
import pandas as pd

# Fixed ticket multipliers for different wage levels (policy)
MULTIPLIERS = {1: 1, 2: 2, 3: 3, 4: 4}


# ----------------------------
# Core helpers (simple + functional)
# ----------------------------

def allocate_counts(total, shares_by_level, levels=(1, 2, 3, 4), normalize=True):
    """
    Turn shares into integer counts that sum exactly to `total`.
    We allocate the first N-1 levels by rounding, and put the residual into the last level.
    """
    shares = {lv: float(shares_by_level.get(lv, 0.0)) for lv in levels}
    ssum = sum(shares.values())
    if normalize and ssum > 0:
        shares = {lv: sh / ssum for lv, sh in shares.items()}

    counts = {}
    remaining = int(total)

    for lv in levels[:-1]:
        c = int(round(total * shares[lv]))
        c = max(0, min(c, remaining))
        counts[lv] = c
        remaining -= c

    counts[levels[-1]] = remaining
    return counts


def tickets_from_counts(counts):
    """Convert headcounts into weighted tickets using fixed WL multipliers."""
    return sum(counts[lv] * MULTIPLIERS[lv] for lv in counts)


def per_candidate_prob(p_ticket, m, method="independent"):
    """
    Convert per-ticket win prob to per-candidate win prob given m tickets.
      - "linear":        p = min(1, m * p_ticket)   (original approximation)
      - "independent":   p = 1 - (1 - p_ticket)^m   (complement of losing all m tickets)
    """
    p_ticket = max(0.0, min(1.0, float(p_ticket)))
    if m <= 0:
        return 0.0

    if method == "linear":
        return min(1.0, m * p_ticket)
    elif method == "independent":
        return 1.0 - (1.0 - p_ticket) ** m
    else:
        raise ValueError('method must be "linear" or "independent"')


def multi_year_prob(p_annual, years=3):
    p_annual = max(0.0, min(1.0, float(p_annual)))
    return 1.0 - (1.0 - p_annual) ** years


# ----------------------------
# Main calculator
# ----------------------------

def h1b_weighted_win_rates(
    total_unique=320_711,
    cap_regular=65_000,
    cap_masters=20_000,
    bachelor_share=0.644,
    wage_shares_bachelors=None,
    wage_shares_masters=None,
    years=3,
    method="independent",
):
    if wage_shares_bachelors is None:
        wage_shares_bachelors = {1: 0.20, 2: 0.61, 3: 0.13, 4: 0.06}
    if wage_shares_masters is None:
        wage_shares_masters = {1: 0.36, 2: 0.50, 3: 0.11, 4: 0.03}

    bachelors_total = int(round(total_unique * bachelor_share))
    masters_total = int(total_unique) - bachelors_total

    bachelors_counts = allocate_counts(bachelors_total, wage_shares_bachelors)
    masters_counts = allocate_counts(masters_total, wage_shares_masters)

    # Round 1
    bach_tickets = tickets_from_counts(bachelors_counts)
    mast_tickets = tickets_from_counts(masters_counts)
    total_tickets_r1 = bach_tickets + mast_tickets
    p1_ticket = 1.0 if total_tickets_r1 <= 0 else min(1.0, cap_regular / total_tickets_r1)

    p1_by_level = {
        lv: per_candidate_prob(p1_ticket, MULTIPLIERS[lv], method=method)
        for lv in MULTIPLIERS
    }

    # Masters survivors into Round 2 (expected)
    exp_mast_winners_r1 = {lv: masters_counts[lv] * p1_by_level[lv] for lv in MULTIPLIERS}
    mast_survivors = {lv: masters_counts[lv] - exp_mast_winners_r1[lv] for lv in MULTIPLIERS}

    # Round 2
    total_tickets_r2 = sum(mast_survivors[lv] * MULTIPLIERS[lv] for lv in MULTIPLIERS)
    p2_ticket = 1.0 if total_tickets_r2 <= 0 else min(1.0, cap_masters / total_tickets_r2)

    p2_cond_by_level = {
        lv: per_candidate_prob(p2_ticket, MULTIPLIERS[lv], method=method)
        for lv in MULTIPLIERS
    }

    # Annual probabilities
    annual_bachelors = {lv: p1_by_level[lv] for lv in MULTIPLIERS}
    annual_masters = {
        lv: p1_by_level[lv] + (1.0 - p1_by_level[lv]) * p2_cond_by_level[lv]
        for lv in MULTIPLIERS
    }

    # Multi-year probabilities
    multi_bachelors = {lv: multi_year_prob(annual_bachelors[lv], years=years) for lv in MULTIPLIERS}
    multi_masters = {lv: multi_year_prob(annual_masters[lv], years=years) for lv in MULTIPLIERS}

    return {
        "results": {
            "annual_win_rate": {
                "Bachelors": {f"WL{lv}": annual_bachelors[lv] for lv in sorted(MULTIPLIERS)},
                "Masters/PhD": {f"WL{lv}": annual_masters[lv] for lv in sorted(MULTIPLIERS)},
            },
            "multi_year_win_rate": {
                "Bachelors": {f"WL{lv}": multi_bachelors[lv] for lv in sorted(MULTIPLIERS)},
                "Masters/PhD": {f"WL{lv}": multi_masters[lv] for lv in sorted(MULTIPLIERS)},
            },
        }
    }


# ----------------------------
# Streamlit UI helpers
# ----------------------------

PRESETS = {
    "Baseline (purely based on historical data)": {
        "total_unique": 320_711,
        "cap_regular": 65_000,
        "cap_masters": 20_000,
        "bachelor_share": 0.644,
        "wage_b": {1: 0.20, 2: 0.61, 3: 0.13, 4: 0.06},
        "wage_m": {1: 0.36, 2: 0.50, 3: 0.11, 4: 0.03},
        "method": "independent",
    },
    "Alternative Scenario 1": {
        "total_unique": 250_000,
        "cap_regular": 65_000,
        "cap_masters": 20_000,
        "bachelor_share": 0.58,
        "wage_b": {1: 0.12, 2: 0.74, 3: 0.10, 4: 0.04},
        "wage_m": {1: 0.40, 2: 0.52, 3: 0.06, 4: 0.02},
        "method": "independent",
    },
    "Alternative Scenario 2": {
        "total_unique": 320_711,
        "cap_regular": 65_000,
        "cap_masters": 20_000,
        "bachelor_share": 0.60,
        "wage_b": {1: 0.10, 2: 0.55, 3: 0.22, 4: 0.13},
        "wage_m": {1: 0.25, 2: 0.45, 3: 0.20, 4: 0.10},
        "method": "independent",
    },
}

BASELINE_KEY = "Baseline (purely based on historical data)"
PRESET_OPTIONS = ["Custom"] + list(PRESETS.keys())


def _set_loading(prefix, val):
    st.session_state[f"{prefix}_loading_preset"] = val


def load_preset_into_state(prefix, preset_name):
    """Programmatically load a preset into widget states."""
    if preset_name == "Custom":
        return
    p = PRESETS[preset_name]
    _set_loading(prefix, True)

    st.session_state[f"{prefix}_total_unique"] = int(p["total_unique"])
    st.session_state[f"{prefix}_cap_regular"] = int(p["cap_regular"])
    st.session_state[f"{prefix}_cap_masters"] = int(p["cap_masters"])
    st.session_state[f"{prefix}_bachelor_share"] = float(p["bachelor_share"])
    st.session_state[f"{prefix}_method"] = p["method"]

    st.session_state[f"{prefix}_b1"] = float(p["wage_b"][1])
    st.session_state[f"{prefix}_b2"] = float(p["wage_b"][2])
    st.session_state[f"{prefix}_b3"] = float(p["wage_b"][3])
    st.session_state[f"{prefix}_b4"] = float(p["wage_b"][4])

    st.session_state[f"{prefix}_m1"] = float(p["wage_m"][1])
    st.session_state[f"{prefix}_m2"] = float(p["wage_m"][2])
    st.session_state[f"{prefix}_m3"] = float(p["wage_m"][3])
    st.session_state[f"{prefix}_m4"] = float(p["wage_m"][4])

    _set_loading(prefix, False)


def on_preset_change(prefix):
    sel = st.session_state.get(f"{prefix}_preset", "Custom")
    if sel != "Custom":
        load_preset_into_state(prefix, sel)


def mark_custom_if_changed(prefix):
    """If user tweaks any field away from the selected preset, auto-switch preset to Custom."""
    if st.session_state.get(f"{prefix}_loading_preset", False):
        return

    sel = st.session_state.get(f"{prefix}_preset", "Custom")
    if sel == "Custom" or sel not in PRESETS:
        return

    p = PRESETS[sel]
    eps = 1e-12

    def fkey(k): return st.session_state.get(f"{prefix}_{k}")

    changed = False
    changed |= (int(fkey("total_unique")) != int(p["total_unique"]))
    changed |= (int(fkey("cap_regular")) != int(p["cap_regular"]))
    changed |= (int(fkey("cap_masters")) != int(p["cap_masters"]))
    changed |= (abs(float(fkey("bachelor_share")) - float(p["bachelor_share"])) > eps)
    changed |= (str(fkey("method")) != str(p["method"]))

    changed |= (abs(float(fkey("b1")) - float(p["wage_b"][1])) > eps)
    changed |= (abs(float(fkey("b2")) - float(p["wage_b"][2])) > eps)
    changed |= (abs(float(fkey("b3")) - float(p["wage_b"][3])) > eps)
    changed |= (abs(float(fkey("b4")) - float(p["wage_b"][4])) > eps)

    changed |= (abs(float(fkey("m1")) - float(p["wage_m"][1])) > eps)
    changed |= (abs(float(fkey("m2")) - float(p["wage_m"][2])) > eps)
    changed |= (abs(float(fkey("m3")) - float(p["wage_m"][3])) > eps)
    changed |= (abs(float(fkey("m4")) - float(p["wage_m"][4])) > eps)

    if changed:
        st.session_state[f"{prefix}_preset"] = "Custom"


def ensure_initialized(prefix):
    """Initialize widget state once per prefix."""
    if f"{prefix}_preset" in st.session_state:
        return
    st.session_state[f"{prefix}_preset"] = BASELINE_KEY
    load_preset_into_state(prefix, BASELINE_KEY)


def output_to_long_df(out, years):
    annual = out["results"]["annual_win_rate"]
    multi = out["results"]["multi_year_win_rate"]

    rows = []
    for profile in ["Bachelors", "Masters/PhD"]:
        for wl in ["WL1", "WL2", "WL3", "WL4"]:
            rows.append({
                "Profile": profile,
                "Wage Level": wl,
                "Annual": float(annual[profile][wl]),
                f"{years}-Year": float(multi[profile][wl]),
            })

    return pd.DataFrame(rows)


def format_percent(x):
    return f"{x * 100:.2f}%"


def scenario_panel(prefix, title, years, in_column=False):
    """Render one scenario panel and return its computed output + numeric dataframe."""
    container = st.container() if not in_column else st
    with container:
        st.markdown(f"### {title}")

        st.selectbox(
            "Scenario preset",
            PRESET_OPTIONS,
            key=f"{prefix}_preset",
            on_change=lambda: on_preset_change(prefix),
        )
        st.caption("Tip: if you change any input below, the preset will automatically switch to Custom.")

        cA, cB = st.columns(2)
        with cA:
            st.number_input(
                "Total applicants (unique)",
                min_value=0,
                step=1000,
                key=f"{prefix}_total_unique",
                on_change=lambda: mark_custom_if_changed(prefix),
            )
            st.number_input(
                "Regular cap (Round 1)",
                min_value=0,
                step=1000,
                key=f"{prefix}_cap_regular",
                on_change=lambda: mark_custom_if_changed(prefix),
            )
            st.slider(
                "Bachelor share",
                0.0,
                1.0,
                0.644,
                0.001,
                key=f"{prefix}_bachelor_share",
                on_change=lambda: mark_custom_if_changed(prefix),
            )

        with cB:
            st.number_input(
                "Masters cap (Round 2)",
                min_value=0,
                step=1000,
                key=f"{prefix}_cap_masters",
                on_change=lambda: mark_custom_if_changed(prefix),
            )
            st.selectbox(
                "Probability method",
                ["linear", "independent"],
                key=f"{prefix}_method",
                on_change=lambda: mark_custom_if_changed(prefix),
            )
            st.number_input(
                "Years (e.g., STEM OPT attempts)",
                min_value=1,
                step=1,
                value=int(years),
                key=f"{prefix}_years",
                on_change=lambda: mark_custom_if_changed(prefix),
            )

        st.markdown("**Wage-level shares (normalized within each degree group)**")
        w1, w2 = st.columns(2)
        with w1:
            st.markdown("**Bachelors**")
            st.number_input("BA WL1 share", min_value=0.0, step=0.01, format="%.4f", key=f"{prefix}_b1", on_change=lambda: mark_custom_if_changed(prefix))
            st.number_input("BA WL2 share", min_value=0.0, step=0.01, format="%.4f", key=f"{prefix}_b2", on_change=lambda: mark_custom_if_changed(prefix))
            st.number_input("BA WL3 share", min_value=0.0, step=0.01, format="%.4f", key=f"{prefix}_b3", on_change=lambda: mark_custom_if_changed(prefix))
            st.number_input("BA WL4 share", min_value=0.0, step=0.01, format="%.4f", key=f"{prefix}_b4", on_change=lambda: mark_custom_if_changed(prefix))

        with w2:
            st.markdown("**Masters/PhD**")
            st.number_input("MS WL1 share", min_value=0.0, step=0.01, format="%.4f", key=f"{prefix}_m1", on_change=lambda: mark_custom_if_changed(prefix))
            st.number_input("MS WL2 share", min_value=0.0, step=0.01, format="%.4f", key=f"{prefix}_m2", on_change=lambda: mark_custom_if_changed(prefix))
            st.number_input("MS WL3 share", min_value=0.0, step=0.01, format="%.4f", key=f"{prefix}_m3", on_change=lambda: mark_custom_if_changed(prefix))
            st.number_input("MS WL4 share", min_value=0.0, step=0.01, format="%.4f", key=f"{prefix}_m4", on_change=lambda: mark_custom_if_changed(prefix))

        wage_b = {1: st.session_state[f"{prefix}_b1"], 2: st.session_state[f"{prefix}_b2"], 3: st.session_state[f"{prefix}_b3"], 4: st.session_state[f"{prefix}_b4"]}
        wage_m = {1: st.session_state[f"{prefix}_m1"], 2: st.session_state[f"{prefix}_m2"], 3: st.session_state[f"{prefix}_m3"], 4: st.session_state[f"{prefix}_m4"]}

        out = h1b_weighted_win_rates(
            total_unique=int(st.session_state[f"{prefix}_total_unique"]),
            cap_regular=int(st.session_state[f"{prefix}_cap_regular"]),
            cap_masters=int(st.session_state[f"{prefix}_cap_masters"]),
            bachelor_share=float(st.session_state[f"{prefix}_bachelor_share"]),
            wage_shares_bachelors=wage_b,
            wage_shares_masters=wage_m,
            years=int(st.session_state[f"{prefix}_years"]),
            method=str(st.session_state[f"{prefix}_method"]),
        )

        df_num = output_to_long_df(out, years=int(st.session_state[f"{prefix}_years"]))
        return out, df_num


# ----------------------------
# Streamlit UI
# ----------------------------

st.set_page_config(page_title="H-1B Win Rate Calculator", layout="centered")
st.title("H-1B Weighted Lottery Win Rate Calculator")
st.caption("Two-round model: Round 1 (regular cap) across all tickets, then Round 2 (masters cap) across remaining Masters/PhD tickets.")

compare_mode = st.checkbox("Compare two scenarios (A vs B)", value=False)

if not compare_mode:
    ensure_initialized("S")
    _, dfS = scenario_panel("S", "Scenario", years=3)

    # Format for display
    yearsS = int(st.session_state["S_years"])
    df_show = dfS.copy()
    df_show["Annual Win Rate"] = df_show["Annual"].apply(format_percent)
    df_show[f"{yearsS}-Year Win Rate"] = df_show[f"{yearsS}-Year"].apply(format_percent)
    df_show = df_show[["Profile", "Wage Level", "Annual Win Rate", f"{yearsS}-Year Win Rate"]]

    st.subheader("Results")
    st.dataframe(df_show, use_container_width=True)

    st.download_button(
        "Download results as CSV",
        df_show.to_csv(index=False).encode("utf-8"),
        file_name="h1b_win_rates.csv",
        mime="text/csv",
    )

else:
    ensure_initialized("A")
    ensure_initialized("B")

    col1, col2 = st.columns(2)
    with col1:
        _, dfA = scenario_panel("A", "Scenario A", years=3, in_column=True)
    with col2:
        _, dfB = scenario_panel("B", "Scenario B", years=3, in_column=True)

    yearsA = int(st.session_state["A_years"])
    yearsB = int(st.session_state["B_years"])

    # Merge on Profile + Wage Level
    dfA2 = dfA.rename(columns={"Annual": "A_Annual", f"{yearsA}-Year": f"A_{yearsA}-Year"})
    dfB2 = dfB.rename(columns={"Annual": "B_Annual", f"{yearsB}-Year": f"B_{yearsB}-Year"})
    dfM = dfA2.merge(dfB2, on=["Profile", "Wage Level"], how="inner")

    # Deltas (B - A)
    dfM["Δ Annual (B-A)"] = dfM["B_Annual"] - dfM["A_Annual"]
    dfM[f"Δ {yearsA}-Year (B-A)"] = dfM[f"B_{yearsB}-Year"] - dfM[f"A_{yearsA}-Year"]

    # Format for display
    dfShow = dfM.copy()
    dfShow["A Annual"] = dfShow["A_Annual"].apply(format_percent)
    dfShow["B Annual"] = dfShow["B_Annual"].apply(format_percent)

    dfShow[f"A {yearsA}-Year"] = dfShow[f"A_{yearsA}-Year"].apply(format_percent)
    dfShow[f"B {yearsB}-Year"] = dfShow[f"B_{yearsB}-Year"].apply(format_percent)

    dfShow["Δ Annual (B-A)"] = dfShow["Δ Annual (B-A)"].apply(lambda x: f"{x*100:+.2f}%")
    dfShow[f"Δ {yearsA}-Year (B-A)"] = dfShow[f"Δ {yearsA}-Year (B-A)"].apply(lambda x: f"{x*100:+.2f}%")

    dfShow = dfShow[
        ["Profile", "Wage Level", "A Annual", "B Annual", "Δ Annual (B-A)", f"A {yearsA}-Year", f"B {yearsB}-Year", f"Δ {yearsA}-Year (B-A)"]
    ]

    st.subheader("Comparison Results (A vs B)")
    st.dataframe(dfShow, use_container_width=True)

    st.download_button(
        "Download comparison as CSV",
        dfShow.to_csv(index=False).encode("utf-8"),
        file_name="h1b_win_rate_comparison.csv",
        mime="text/csv",
    )


