
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
    """
    Convert headcounts into weighted tickets using fixed WL multipliers.
    """
    return sum(counts[lv] * MULTIPLIERS[lv] for lv in counts)


def per_candidate_prob(p_ticket, m, method="independent"):
    """
    Convert per-ticket win prob to per-candidate win prob given m tickets.

    method:
      - "linear":        p = min(1, m * p_ticket)
                         (Spreadsheet-style approximation used originally: proportional to ticket count)
      - "independent":   p = 1 - (1 - p_ticket)^m
                         (Complement: lose all m tickets, assuming independence)
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
    bachelor_share=0.644,                  # undergrad share
    wage_shares_bachelors=None,            # dict: {1:...,2:...,3:...,4:...}
    wage_shares_masters=None,              # dict: {1:...,2:...,3:...,4:...}
    years=3,
    method="linear",
):
    """
    Returns a dict with:
      - intermediate totals (counts, tickets, p_ticket)
      - final annual win rates & multi-year probabilities by (degree, wage level)
    """

    if wage_shares_bachelors is None:
        wage_shares_bachelors = {1: 0.20, 2: 0.61, 3: 0.13, 4: 0.06}
    if wage_shares_masters is None:
        wage_shares_masters = {1: 0.36, 2: 0.50, 3: 0.11, 4: 0.03}

    # Degree totals
    bachelors_total = int(round(total_unique * bachelor_share))
    masters_total = int(total_unique) - bachelors_total

    # Wage-level counts
    bachelors_counts = allocate_counts(bachelors_total, wage_shares_bachelors)
    masters_counts = allocate_counts(masters_total, wage_shares_masters)

    # Round 1 tickets (everyone)
    bach_tickets = tickets_from_counts(bachelors_counts)
    mast_tickets = tickets_from_counts(masters_counts)
    total_tickets_r1 = bach_tickets + mast_tickets

    p1_ticket = 1.0 if total_tickets_r1 <= 0 else min(1.0, cap_regular / total_tickets_r1)

    # Round 1 per-candidate win prob by wage level
    p1_by_level = {
        lv: per_candidate_prob(p1_ticket, MULTIPLIERS[lv], method=method)
        for lv in MULTIPLIERS
    }

    # Expected Masters winners in Round 1, then survivors into Round 2
    exp_mast_winners_r1 = {lv: masters_counts[lv] * p1_by_level[lv] for lv in MULTIPLIERS}
    mast_survivors = {lv: masters_counts[lv] - exp_mast_winners_r1[lv] for lv in MULTIPLIERS}

    # Round 2 tickets (Masters survivors only)
    total_tickets_r2 = sum(mast_survivors[lv] * MULTIPLIERS[lv] for lv in MULTIPLIERS)
    p2_ticket = 1.0 if total_tickets_r2 <= 0 else min(1.0, cap_masters / total_tickets_r2)

    # Round 2 conditional win prob for a Masters candidate by wage level
    p2_cond_by_level = {
        lv: per_candidate_prob(p2_ticket, MULTIPLIERS[lv], method=method)
        for lv in MULTIPLIERS
    }

    # Combine annual probabilities
    annual_bachelors = {lv: p1_by_level[lv] for lv in MULTIPLIERS}
    annual_masters = {
        lv: p1_by_level[lv] + (1.0 - p1_by_level[lv]) * p2_cond_by_level[lv]
        for lv in MULTIPLIERS
    }

    # Multi-year (e.g., 3 attempts on STEM OPT)
    multi_bachelors = {lv: multi_year_prob(annual_bachelors[lv], years=years) for lv in MULTIPLIERS}
    multi_masters = {lv: multi_year_prob(annual_masters[lv], years=years) for lv in MULTIPLIERS}

    return {
        "inputs": {
            "total_unique": total_unique,
            "cap_regular": cap_regular,
            "cap_masters": cap_masters,
            "bachelor_share": bachelor_share,
            "years": years,
            "method": method,
            "wage_shares_bachelors": wage_shares_bachelors,
            "wage_shares_masters": wage_shares_masters,
            "multipliers_fixed": MULTIPLIERS,
        },
        "intermediate": {
            "bachelors_total": bachelors_total,
            "masters_total": masters_total,
            "bachelors_counts": bachelors_counts,
            "masters_counts": masters_counts,
            "tickets_round1_bachelors": bach_tickets,
            "tickets_round1_masters": mast_tickets,
            "tickets_round1_total": total_tickets_r1,
            "p1_ticket": p1_ticket,
            "masters_survivors_counts": mast_survivors,
            "tickets_round2_masters_survivors": total_tickets_r2,
            "p2_ticket": p2_ticket,
        },
        "results": {
            "annual_win_rate": {
                "Bachelors": {f"WL{lv}": annual_bachelors[lv] for lv in sorted(MULTIPLIERS)},
                "Masters/PhD": {f"WL{lv}": annual_masters[lv] for lv in sorted(MULTIPLIERS)},
            },
            "multi_year_win_rate": {
                "Bachelors": {f"WL{lv}": multi_bachelors[lv] for lv in sorted(MULTIPLIERS)},
                "Masters/PhD": {f"WL{lv}": multi_masters[lv] for lv in sorted(MULTIPLIERS)},
            },
            "round1_win_rate": {f"WL{lv}": p1_by_level[lv] for lv in sorted(MULTIPLIERS)},
            "round2_win_rate_conditional_masters": {
                f"WL{lv}": p2_cond_by_level[lv] for lv in sorted(MULTIPLIERS)
            },
        },
    }


# ----------------------------
# Streamlit helpers
# ----------------------------

def build_raw_results_df(out, years):
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


def format_percent_df(df, years):
    dff = df.copy()
    dff["Annual"] = (dff["Annual"] * 100).round(2).astype(str) + "%"
    dff[f"{years}-Year"] = (dff[f"{years}-Year"] * 100).round(2).astype(str) + "%"
    dff = dff.rename(columns={"Annual": "Annual Win Rate", f"{years}-Year": f"{years}-Year Win Rate"})
    return dff


def scenario_panel(key_prefix, title, preset_dict, container=None):
    """
    Renders one scenario's input panel + results.
    Returns (out_dict, raw_results_df)

    Fix for your error:
    - If `container` is None, we create a container so `with container:` always works.
    """
    if container is None:
        container = st.container()

    with container:
        st.markdown(f"### {title}")

        preset_name = st.selectbox(
            "Scenario preset",
            ["Custom"] + list(preset_dict.keys()),
            key=f"{key_prefix}_preset",
        )

        defaults = preset_dict["Baseline (historical)"] if preset_name == "Custom" else preset_dict[preset_name]

        colA, colB = st.columns(2)
        with colA:
            total_unique = st.number_input(
                "Total applicants (unique)",
                min_value=0,
                value=int(defaults["total_unique"]),
                step=1000,
                key=f"{key_prefix}_total_unique",
            )
            cap_regular = st.number_input(
                "Regular cap (Round 1)",
                min_value=0,
                value=int(defaults["cap_regular"]),
                step=1000,
                key=f"{key_prefix}_cap_regular",
            )
            bachelor_share = st.slider(
                "Bachelor share",
                0.0,
                1.0,
                float(defaults["bachelor_share"]),
                0.001,
                key=f"{key_prefix}_bachelor_share",
            )

        with colB:
            cap_masters = st.number_input(
                "Masters cap (Round 2)",
                min_value=0,
                value=int(defaults["cap_masters"]),
                step=1000,
                key=f"{key_prefix}_cap_masters",
            )
            years = st.number_input(
                "Years (e.g., STEM OPT attempts)",
                min_value=1,
                value=int(defaults["years"]),
                step=1,
                key=f"{key_prefix}_years",
            )
            method = st.selectbox(
                "Probability method",
                ["linear", "independent"],
                index=0 if defaults["method"] == "linear" else 1,
                key=f"{key_prefix}_method",
            )

        st.markdown("**Wage-level shares** (the model will normalize within each degree group)")

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Bachelors**")
            b1 = st.number_input("BA WL1 share", min_value=0.0, value=float(defaults["wage_b"][1]),
                                step=0.01, format="%.4f", key=f"{key_prefix}_b1")
            b2 = st.number_input("BA WL2 share", min_value=0.0, value=float(defaults["wage_b"][2]),
                                step=0.01, format="%.4f", key=f"{key_prefix}_b2")
            b3 = st.number_input("BA WL3 share", min_value=0.0, value=float(defaults["wage_b"][3]),
                                step=0.01, format="%.4f", key=f"{key_prefix}_b3")
            b4 = st.number_input("BA WL4 share", min_value=0.0, value=float(defaults["wage_b"][4]),
                                step=0.01, format="%.4f", key=f"{key_prefix}_b4")

            bsum = b1 + b2 + b3 + b4
            st.caption(f"BA shares sum = {bsum:.4f} (will normalize if not 1.0)")

        with c2:
            st.markdown("**Masters/PhD**")
            m1 = st.number_input("MS WL1 share", min_value=0.0, value=float(defaults["wage_m"][1]),
                                step=0.01, format="%.4f", key=f"{key_prefix}_m1")
            m2 = st.number_input("MS WL2 share", min_value=0.0, value=float(defaults["wage_m"][2]),
                                step=0.01, format="%.4f", key=f"{key_prefix}_m2")
            m3 = st.number_input("MS WL3 share", min_value=0.0, value=float(defaults["wage_m"][3]),
                                step=0.01, format="%.4f", key=f"{key_prefix}_m3")
            m4 = st.number_input("MS WL4 share", min_value=0.0, value=float(defaults["wage_m"][4]),
                                step=0.01, format="%.4f", key=f"{key_prefix}_m4")

            msum = m1 + m2 + m3 + m4
            st.caption(f"MS shares sum = {msum:.4f} (will normalize if not 1.0)")

        wage_shares_bachelors = {1: b1, 2: b2, 3: b3, 4: b4}
        wage_shares_masters = {1: m1, 2: m2, 3: m3, 4: m4}

        if (b1 + b2 + b3 + b4) <= 0:
            st.warning("Bachelors wage shares sum to 0. All BA candidates will effectively be assigned to WL4 by residual allocation.")
        if (m1 + m2 + m3 + m4) <= 0:
            st.warning("Masters wage shares sum to 0. All MS candidates will effectively be assigned to WL4 by residual allocation.")

        out = h1b_weighted_win_rates(
            total_unique=total_unique,
            cap_regular=cap_regular,
            cap_masters=cap_masters,
            bachelor_share=bachelor_share,
            wage_shares_bachelors=wage_shares_bachelors,
            wage_shares_masters=wage_shares_masters,
            years=years,
            method=method,
        )

        raw_df = build_raw_results_df(out, years=years)
        view_df = format_percent_df(raw_df, years=years)

        st.markdown("#### Results")
        st.dataframe(view_df, use_container_width=True)

        st.download_button(
            "Download results as CSV",
            view_df.to_csv(index=False).encode("utf-8"),
            file_name=f"h1b_win_rates_{key_prefix}.csv",
            mime="text/csv",
            key=f"{key_prefix}_download",
        )

        with st.expander("Intermediate numbers (debug)"):
            st.json(out["intermediate"])

        return out, raw_df


def compare_two(rawA, rawB, yearsA, yearsB):
    """
    Compare two result tables (A vs B).
    If years differ, we compare both Annual and each scenario's multi-year column separately.
    """
    # Ensure consistent join keys
    key_cols = ["Profile", "Wage Level"]
    a = rawA.copy()
    b = rawB.copy()

    a = a.rename(columns={"Annual": "Annual_A", f"{yearsA}-Year": f"{yearsA}-Year_A"})
    b = b.rename(columns={"Annual": "Annual_B", f"{yearsB}-Year": f"{yearsB}-Year_B"})

    merged = a.merge(b, on=key_cols, how="inner")

    merged["Annual_diff_pp"] = (merged["Annual_B"] - merged["Annual_A"]) * 100  # percentage points

    # If same years, add a unified multi-year diff
    if yearsA == yearsB:
        my_col = f"{yearsA}-Year"
        merged[f"{my_col}_diff_pp"] = (merged[f"{yearsA}-Year_B"] - merged[f"{yearsA}-Year_A"]) * 100

    # Pretty formatting for display
    disp = merged[key_cols].copy()
    disp["Annual A"] = (merged["Annual_A"] * 100).round(2).astype(str) + "%"
    disp["Annual B"] = (merged["Annual_B"] * 100).round(2).astype(str) + "%"
    disp["Annual (B - A)"] = merged["Annual_diff_pp"].round(2).astype(str) + " pp"

    disp[f"{yearsA}-Year A"] = (merged[f"{yearsA}-Year_A"] * 100).round(2).astype(str) + "%"
    disp[f"{yearsB}-Year B"] = (merged[f"{yearsB}-Year_B"] * 100).round(2).astype(str) + "%"

    if yearsA == yearsB:
        disp[f"{yearsA}-Year (B - A)"] = merged[f"{yearsA}-Year_diff_pp"].round(2).astype(str) + " pp"

    return disp


# ----------------------------
# Streamlit UI
# ----------------------------

st.set_page_config(page_title="H-1B Win Rate Calculator", layout="wide")
st.title("H-1B Weighted Lottery Win Rate Calculator")
st.caption("Round 1: regular cap across ALL tickets. Round 2: masters cap across surviving Masters/PhD tickets.")

PRESETS = {
    "Baseline (historical)": {
        "total_unique": 320_711,
        "cap_regular": 65_000,
        "cap_masters": 20_000,
        "bachelor_share": 0.644,
        "wage_b": {1: 0.20, 2: 0.61, 3: 0.13, 4: 0.06},
        "wage_m": {1: 0.36, 2: 0.50, 3: 0.11, 4: 0.03},
        "years": 3,
        "method": "independent",
    },
    "Concern-based (best guess)": {
        "total_unique": 250_000,
        "cap_regular": 65_000,
        "cap_masters": 20_000,
        "bachelor_share": 0.58,
        "wage_b": {1: 0.12, 2: 0.74, 3: 0.10, 4: 0.04},
        "wage_m": {1: 0.40, 2: 0.52, 3: 0.06, 4: 0.02},
        "years": 3,
        "method": "independent",
    },
    "Ticket inflation (wage-upcoding sensitivity)": {
        "total_unique": 320_711,
        "cap_regular": 65_000,
        "cap_masters": 20_000,
        "bachelor_share": 0.60,
        "wage_b": {1: 0.10, 2: 0.55, 3: 0.22, 4: 0.13},
        "wage_m": {1: 0.25, 2: 0.45, 3: 0.20, 4: 0.10},
        "years": 3,
        "method": "independent",
    },
}

mode = st.radio(
    "Mode",
    ["Single scenario", "Compare two scenarios"],
    horizontal=True,
)

if mode == "Single scenario":
    scenario_panel("S", "Scenario", PRESETS)

else:
    st.info("Tip: Use different presets/inputs for A and B. The table below shows B − A differences in percentage points (pp).")

    colA, colB = st.columns(2)
    outA, rawA = scenario_panel("A", "Scenario A", PRESETS, container=colA)
    outB, rawB = scenario_panel("B", "Scenario B", PRESETS, container=colB)

    yearsA = int(outA["inputs"]["years"])
    yearsB = int(outB["inputs"]["years"])

    st.markdown("---")
    st.subheader("Comparison (Scenario B − Scenario A)")
    cmp_df = compare_two(rawA, rawB, yearsA=yearsA, yearsB=yearsB)
    st.dataframe(cmp_df, use_container_width=True)

    st.download_button(
        "Download comparison as CSV",
        cmp_df.to_csv(index=False).encode("utf-8"),
        file_name="h1b_scenario_comparison.csv",
        mime="text/csv",
        key="cmp_download",
    )

