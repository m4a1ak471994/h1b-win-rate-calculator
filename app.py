import random

import pandas as pd
import streamlit as st

# ----------------------------
# SEO & PAGE CONFIGURATION
# ----------------------------
st.set_page_config(
    page_title="H-1B Weighted Lottery Win Rate Calculator (2025 Rule)",
    page_icon="chart_with_upwards_trend",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": "https://public-inspection.federalregister.gov/2025-23853.pdf",
        "About": "H-1B Weighted Lottery Calculator based on DHS Dec. 29, 2025 Final Rule.",
    },
)

# ----------------------------
# VISIBLE UI CONTENT
# ----------------------------

st.title("H-1B Weighted Lottery Win Rate Calculator")
st.markdown(
    """
A Streamlit app that estimates H-1B lottery win rates under a 2-round selection process with weighted tickets **by wage level and degree type**.

On Dec. 29, 2025, DHS/USCIS finalized an H-1B rule that introduces **weighted selection** by wage level (WL1-WL4). This app estimates win rates under that system while preserving the existent two-round structure. **The final rule itself does not publish the degree-split or multi-year win-rate calculations**, so this app computes them.

Weights are based on **wage levels** (WL1-WL4): **WL1 = 1 ticket, WL2 = 2, WL3 = 3, WL4 = 4**.

The app now uses a **Monte Carlo simulation** of the two-round process:
- **Round 1 (Regular cap):** selects unique candidates from all applicants.
- **Round 2 (Masters cap):** selects unique candidates from the remaining Masters/PhD applicants who did not get selected in Round 1.

Once a candidate is selected in any round, all of that candidate's tickets are removed from later draws.
The app reports **annual** and **multi-year win rates** separately for Bachelors and Masters/PhD.

**Rule text:** https://public-inspection.federalregister.gov/2025-23853.pdf
"""
)
st.caption("Need help with the inputs? Open the `Parameter Guide` tab.")

# ----------------------------
# LOGIC & CALCULATOR
# ----------------------------

MULTIPLIERS = {1: 1, 2: 2, 3: 3, 4: 4}
DEFAULT_SIMULATIONS = 200
DEFAULT_SEED = 42

GROUP_DEFINITIONS = (
    ("Bachelors", "WL1", False, MULTIPLIERS[1]),
    ("Bachelors", "WL2", False, MULTIPLIERS[2]),
    ("Bachelors", "WL3", False, MULTIPLIERS[3]),
    ("Bachelors", "WL4", False, MULTIPLIERS[4]),
    ("Masters/PhD", "WL1", True, MULTIPLIERS[1]),
    ("Masters/PhD", "WL2", True, MULTIPLIERS[2]),
    ("Masters/PhD", "WL3", True, MULTIPLIERS[3]),
    ("Masters/PhD", "WL4", True, MULTIPLIERS[4]),
)


def allocate_counts(total, shares_by_level, levels=(1, 2, 3, 4), normalize=True):
    shares = {lv: float(shares_by_level.get(lv, 0.0)) for lv in levels}
    share_sum = sum(shares.values())

    if share_sum <= 0:
        raise ValueError("Wage-level shares must sum to more than 0 for each degree group.")

    if normalize:
        shares = {lv: share / share_sum for lv, share in shares.items()}

    counts = {}
    remaining = int(total)
    for lv in levels[:-1]:
        count = int(round(total * shares[lv]))
        count = max(0, min(count, remaining))
        counts[lv] = count
        remaining -= count

    counts[levels[-1]] = remaining
    return counts


def multi_year_prob(p_annual, years=3):
    p_annual = max(0.0, min(1.0, float(p_annual)))
    return 1.0 - (1.0 - p_annual) ** years


def build_bucket_pool(bachelors_counts, masters_counts):
    group_rows = []
    group_sizes = []
    group_candidate_weights = []

    for profile, wage_label, is_master, weight in GROUP_DEFINITIONS:
        level = int(wage_label[-1])
        counts = masters_counts if is_master else bachelors_counts
        count = int(counts[level])
        group_rows.append((profile, wage_label))
        group_sizes.append(count)
        group_candidate_weights.append(weight)

    group_rows = tuple(group_rows)
    group_sizes = tuple(group_sizes)
    group_candidate_weights = tuple(group_candidate_weights)
    initial_bucket_ticket_weights = tuple(
        group_sizes[group_id] * group_candidate_weights[group_id]
        for group_id in range(len(group_rows))
    )

    return {
        "group_rows": group_rows,
        "group_sizes": group_sizes,
        "group_candidate_weights": group_candidate_weights,
        "initial_bucket_ticket_weights": initial_bucket_ticket_weights,
        "total_candidates": sum(group_sizes),
        "total_masters": sum(group_sizes[4:]),
        "initial_total_weight": sum(initial_bucket_ticket_weights),
        "initial_masters_total_weight": sum(initial_bucket_ticket_weights[4:]),
    }


def run_single_simulation(pool, cap_regular, cap_masters, rng, accumulated_wins=None):
    group_candidate_weights = pool["group_candidate_weights"]
    bucket_ticket_weights = list(pool["initial_bucket_ticket_weights"])
    total_weight = pool["initial_total_weight"]
    masters_total_weight = pool["initial_masters_total_weight"]

    wins_by_group = accumulated_wins if accumulated_wins is not None else [0] * len(pool["group_rows"])
    regular_draws = min(int(cap_regular), pool["total_candidates"])
    masters_draws = min(int(cap_masters), pool["total_masters"])

    for _ in range(regular_draws):
        if total_weight <= 0:
            break

        target = rng.random() * total_weight
        cumulative = bucket_ticket_weights[0]
        if target < cumulative:
            group_id = 0
        else:
            cumulative += bucket_ticket_weights[1]
            if target < cumulative:
                group_id = 1
            else:
                cumulative += bucket_ticket_weights[2]
                if target < cumulative:
                    group_id = 2
                else:
                    cumulative += bucket_ticket_weights[3]
                    if target < cumulative:
                        group_id = 3
                    else:
                        cumulative += bucket_ticket_weights[4]
                        if target < cumulative:
                            group_id = 4
                        else:
                            cumulative += bucket_ticket_weights[5]
                            if target < cumulative:
                                group_id = 5
                            else:
                                cumulative += bucket_ticket_weights[6]
                                if target < cumulative:
                                    group_id = 6
                                else:
                                    group_id = 7

        candidate_weight = group_candidate_weights[group_id]
        wins_by_group[group_id] += 1
        bucket_ticket_weights[group_id] -= candidate_weight
        total_weight -= candidate_weight
        if group_id >= 4:
            masters_total_weight -= candidate_weight

    for _ in range(masters_draws):
        if masters_total_weight <= 0:
            break

        target = rng.random() * masters_total_weight
        cumulative = bucket_ticket_weights[4]
        if target < cumulative:
            group_id = 4
        else:
            cumulative += bucket_ticket_weights[5]
            if target < cumulative:
                group_id = 5
            else:
                cumulative += bucket_ticket_weights[6]
                if target < cumulative:
                    group_id = 6
                else:
                    group_id = 7

        candidate_weight = group_candidate_weights[group_id]
        wins_by_group[group_id] += 1
        bucket_ticket_weights[group_id] -= candidate_weight
        total_weight -= candidate_weight
        masters_total_weight -= candidate_weight

    return wins_by_group


@st.cache_data(show_spinner=False)
def simulate_annual_rates(bachelors_counts_items, masters_counts_items, cap_regular, cap_masters, simulations, seed):
    simulations = int(simulations)
    bachelors_counts = {level: int(count) for level, count in bachelors_counts_items}
    masters_counts = {level: int(count) for level, count in masters_counts_items}
    pool = build_bucket_pool(bachelors_counts, masters_counts)
    rng = random.Random(int(seed))
    total_wins = [0] * len(pool["group_rows"])

    for _ in range(simulations):
        run_single_simulation(pool, cap_regular, cap_masters, rng, accumulated_wins=total_wins)

    annual_rates = {"Bachelors": {}, "Masters/PhD": {}}
    for group_id, (profile, wage_label) in enumerate(pool["group_rows"]):
        group_size = pool["group_sizes"][group_id]
        if group_size <= 0:
            annual_probability = 0.0
        else:
            annual_probability = total_wins[group_id] / (group_size * simulations)
        annual_rates[profile][wage_label] = annual_probability

    return annual_rates


def h1b_weighted_win_rates(
    total_unique=320_711,
    cap_regular=65_000,
    cap_masters=20_000,
    bachelor_share=0.644,
    wage_shares_bachelors=None,
    wage_shares_masters=None,
    years=3,
    simulations=DEFAULT_SIMULATIONS,
    seed=DEFAULT_SEED,
):
    if wage_shares_bachelors is None:
        wage_shares_bachelors = {1: 0.20, 2: 0.61, 3: 0.13, 4: 0.06}
    if wage_shares_masters is None:
        wage_shares_masters = {1: 0.36, 2: 0.50, 3: 0.11, 4: 0.03}

    bachelors_total = int(round(total_unique * bachelor_share))
    masters_total = int(total_unique) - bachelors_total

    bachelors_counts = allocate_counts(bachelors_total, wage_shares_bachelors)
    masters_counts = allocate_counts(masters_total, wage_shares_masters)

    annual_rates = simulate_annual_rates(
        tuple((level, bachelors_counts[level]) for level in sorted(MULTIPLIERS)),
        tuple((level, masters_counts[level]) for level in sorted(MULTIPLIERS)),
        int(cap_regular),
        int(cap_masters),
        int(simulations),
        int(seed),
    )

    multi_year_rates = {
        profile: {
            wage_level: multi_year_prob(probability, years=years)
            for wage_level, probability in annual_rates[profile].items()
        }
        for profile in annual_rates
    }

    return {
        "inputs": {
            "total_unique": total_unique,
            "cap_regular": cap_regular,
            "cap_masters": cap_masters,
            "bachelor_share": bachelor_share,
            "years": years,
            "simulations": simulations,
            "seed": seed,
            "method": "exact_bucket_level_simulation",
            "wage_shares_bachelors": wage_shares_bachelors,
            "wage_shares_masters": wage_shares_masters,
            "multipliers_fixed": MULTIPLIERS,
        },
        "results": {
            "annual_win_rate": annual_rates,
            "multi_year_win_rate": multi_year_rates,
        },
    }


def build_raw_results_df(out, years):
    annual = out["results"]["annual_win_rate"]
    multi = out["results"]["multi_year_win_rate"]

    rows = []
    for profile in ["Bachelors", "Masters/PhD"]:
        for wage_level in ["WL1", "WL2", "WL3", "WL4"]:
            rows.append(
                {
                    "Profile": profile,
                    "Wage Level": wage_level,
                    "Annual": float(annual[profile][wage_level]),
                    f"{years}-Year": float(multi[profile][wage_level]),
                }
            )
    return pd.DataFrame(rows)


def format_percent_df(df, years):
    formatted = df.copy()
    formatted["Annual"] = (formatted["Annual"] * 100).round(2).astype(str) + "%"
    formatted[f"{years}-Year"] = (formatted[f"{years}-Year"] * 100).round(2).astype(str) + "%"
    return formatted.rename(
        columns={"Annual": "Annual Win Rate", f"{years}-Year": f"{years}-Year Win Rate"}
    )


def render_parameter_guide():
    st.markdown(
        """
### Parameter Guide

These definitions match the documentation in the README.

#### Ticket multipliers
- `WL1`: 1 ticket
- `WL2`: 2 tickets
- `WL3`: 3 tickets
- `WL4`: 4 tickets

#### Inputs
- `Total applicants (total_unique)`: total number of unique candidates in the lottery.
- `Round 1 Regular cap (cap_regular)`: number of selections in Round 1.
- `Round 2 cap (cap_masters)`: number of selections in Round 2 among remaining Masters/PhD candidates.
- `Bachelor share (bachelor_share)`: fraction of applicants that are Bachelors. Masters/PhD share is `1 - bachelor_share`.
- `Wage-level shares (wage_b, wage_m)`: wage-level composition within each degree group.
- `Years (years)`: number of attempts used for the multi-year probability.
- `Simulation runs (simulations)`: number of Monte Carlo trials used to estimate annual win rates.
- `Random seed (seed)`: seed for reproducible simulation results.

#### Notes
- Wage shares within each degree group are normalized if they do not sum to 1.
- If a degree group's wage shares sum to 0, the app raises an error instead of guessing a fallback allocation.

#### Probability summary
- Within each degree group, wage shares are converted into integer headcounts.
- The app simulates the lottery using 8 homogeneous buckets: `Bachelors-WL1` through `Bachelors-WL4`, and `Masters/PhD-WL1` through `Masters/PhD-WL4`.
- If bucket `b` has `n_b` remaining candidates and each candidate has `w_b` tickets, then that bucket contributes `T_b = n_b * w_b`.
- The probability that the next Round 1 winner comes from bucket `b` is `P(b) = T_b / sum(T_j)`.
- For `years` independent attempts, the multi-year probability is `p_multi = 1 - (1 - p_annual) ** years`.
"""
    )


def _apply_defaults_to_session(key_prefix, defaults):
    st.session_state[f"{key_prefix}_total_unique"] = int(defaults["total_unique"])
    st.session_state[f"{key_prefix}_cap_regular"] = int(defaults["cap_regular"])
    st.session_state[f"{key_prefix}_cap_masters"] = int(defaults["cap_masters"])
    st.session_state[f"{key_prefix}_bachelor_share"] = float(defaults["bachelor_share"])
    st.session_state[f"{key_prefix}_years"] = int(defaults["years"])

    st.session_state.setdefault(f"{key_prefix}_simulations", int(defaults.get("simulations", DEFAULT_SIMULATIONS)))
    st.session_state.setdefault(f"{key_prefix}_seed", int(defaults.get("seed", DEFAULT_SEED)))

    st.session_state[f"{key_prefix}_b1"] = float(defaults["wage_b"][1])
    st.session_state[f"{key_prefix}_b2"] = float(defaults["wage_b"][2])
    st.session_state[f"{key_prefix}_b3"] = float(defaults["wage_b"][3])
    st.session_state[f"{key_prefix}_b4"] = float(defaults["wage_b"][4])

    st.session_state[f"{key_prefix}_m1"] = float(defaults["wage_m"][1])
    st.session_state[f"{key_prefix}_m2"] = float(defaults["wage_m"][2])
    st.session_state[f"{key_prefix}_m3"] = float(defaults["wage_m"][3])
    st.session_state[f"{key_prefix}_m4"] = float(defaults["wage_m"][4])


def scenario_panel(key_prefix, title, preset_dict, container=None):
    if container is None:
        container = st.container()

    with container:
        st.markdown(f"### {title}")

        preset_options = ["Custom"] + list(preset_dict.keys())
        preset_key = f"{key_prefix}_preset"
        default_preset = next(iter(preset_dict))
        result_key = f"{key_prefix}_last_out"
        raw_key = f"{key_prefix}_last_raw_df"
        error_key = f"{key_prefix}_last_error"

        if (preset_key not in st.session_state) or (st.session_state[preset_key] not in preset_options):
            st.session_state[preset_key] = default_preset

        def on_preset_change():
            chosen = st.session_state[preset_key]
            if chosen in preset_dict:
                _apply_defaults_to_session(key_prefix, preset_dict[chosen])

        st.selectbox(
            "Scenario preset",
            preset_options,
            key=preset_key,
            on_change=on_preset_change,
        )

        preset_name = st.session_state[preset_key]
        locked = preset_name != "Custom"

        if f"{key_prefix}_total_unique" not in st.session_state:
            init_name = preset_name if preset_name in preset_dict else default_preset
            _apply_defaults_to_session(key_prefix, preset_dict[init_name])

        st.caption("Inputs below update only when you click Run.")

        with st.form(key=f"{key_prefix}_form"):
            col_a, col_b = st.columns(2)
            with col_a:
                total_unique = st.number_input(
                    "Total applicants",
                    min_value=0,
                    step=1000,
                    key=f"{key_prefix}_total_unique",
                    disabled=locked,
                )
                cap_regular = st.number_input(
                    "Round 1 Regular cap",
                    min_value=0,
                    step=1000,
                    key=f"{key_prefix}_cap_regular",
                    disabled=locked,
                )
                bachelor_share = st.slider(
                    "Bachelor share",
                    0.0,
                    1.0,
                    step=0.001,
                    key=f"{key_prefix}_bachelor_share",
                    disabled=locked,
                )
                years = st.number_input(
                    "Years",
                    min_value=1,
                    step=1,
                    key=f"{key_prefix}_years",
                    disabled=locked,
                )

            with col_b:
                cap_masters = st.number_input(
                    "Round 2 cap (MS/PhD)",
                    min_value=0,
                    step=1000,
                    key=f"{key_prefix}_cap_masters",
                    disabled=locked,
                )
                simulations = st.number_input(
                    "Simulation runs",
                    min_value=1,
                    step=100,
                    key=f"{key_prefix}_simulations",
                )
                seed = st.number_input(
                    "Random seed",
                    min_value=0,
                    step=1,
                    key=f"{key_prefix}_seed",
                )
                st.caption("Higher simulation counts improve stability but can take much longer.")

            st.markdown("**Wage-level shares** within each applicant degree group")
            col_left, col_right = st.columns(2)
            with col_left:
                st.markdown("**Bachelors**")
                b1 = st.number_input("BA WL1", min_value=0.0, step=0.01, format="%.4f", key=f"{key_prefix}_b1", disabled=locked)
                b2 = st.number_input("BA WL2", min_value=0.0, step=0.01, format="%.4f", key=f"{key_prefix}_b2", disabled=locked)
                b3 = st.number_input("BA WL3", min_value=0.0, step=0.01, format="%.4f", key=f"{key_prefix}_b3", disabled=locked)
                b4 = st.number_input("BA WL4", min_value=0.0, step=0.01, format="%.4f", key=f"{key_prefix}_b4", disabled=locked)

            with col_right:
                st.markdown("**Masters/PhD**")
                m1 = st.number_input("MS WL1", min_value=0.0, step=0.01, format="%.4f", key=f"{key_prefix}_m1", disabled=locked)
                m2 = st.number_input("MS WL2", min_value=0.0, step=0.01, format="%.4f", key=f"{key_prefix}_m2", disabled=locked)
                m3 = st.number_input("MS WL3", min_value=0.0, step=0.01, format="%.4f", key=f"{key_prefix}_m3", disabled=locked)
                m4 = st.number_input("MS WL4", min_value=0.0, step=0.01, format="%.4f", key=f"{key_prefix}_m4", disabled=locked)

            run_label = f"Run {title}" if title else "Run Scenario"
            run_clicked = st.form_submit_button(run_label, use_container_width=True)

        wage_shares_bachelors = {1: b1, 2: b2, 3: b3, 4: b4}
        wage_shares_masters = {1: m1, 2: m2, 3: m3, 4: m4}

        if run_clicked:
            try:
                with st.spinner("Running exact bucket-level simulation..."):
                    out = h1b_weighted_win_rates(
                        total_unique=total_unique,
                        cap_regular=cap_regular,
                        cap_masters=cap_masters,
                        bachelor_share=bachelor_share,
                        wage_shares_bachelors=wage_shares_bachelors,
                        wage_shares_masters=wage_shares_masters,
                        years=years,
                        simulations=simulations,
                        seed=seed,
                    )
                raw_df = build_raw_results_df(out, years=years)
                st.session_state[result_key] = out
                st.session_state[raw_key] = raw_df
                st.session_state.pop(error_key, None)
            except ValueError as exc:
                st.session_state[error_key] = str(exc)
                st.session_state.pop(result_key, None)
                st.session_state.pop(raw_key, None)

        error_message = st.session_state.get(error_key)
        if error_message:
            st.error(error_message)

        out = st.session_state.get(result_key)
        raw_df = st.session_state.get(raw_key)
        if out is None or raw_df is None:
            st.info("Click Run Scenario to generate results.")
            return None, None

        result_years = int(out["inputs"]["years"])
        view_df = format_percent_df(raw_df, years=result_years)

        st.caption(
            f"Showing the last completed run | Method: exact bucket-level Monte Carlo simulation | Runs: {int(out['inputs']['simulations']):,} | Seed: {int(out['inputs']['seed'])}"
        )
        st.markdown("#### Results")
        st.dataframe(view_df, use_container_width=True)

        st.download_button(
            "Download results as CSV",
            view_df.to_csv(index=False).encode("utf-8"),
            file_name=f"h1b_win_rates_{key_prefix}.csv",
            mime="text/csv",
            key=f"{key_prefix}_download",
        )
        return out, raw_df


def compare_two(raw_a, raw_b, years_a, years_b):
    key_cols = ["Profile", "Wage Level"]
    df_a = raw_a.copy().rename(columns={"Annual": "Annual_A", f"{years_a}-Year": f"{years_a}-Year_A"})
    df_b = raw_b.copy().rename(columns={"Annual": "Annual_B", f"{years_b}-Year": f"{years_b}-Year_B"})
    merged = df_a.merge(df_b, on=key_cols, how="inner")

    merged["Annual_diff_pp"] = (merged["Annual_B"] - merged["Annual_A"]) * 100
    if years_a == years_b:
        merged[f"{years_a}-Year_diff_pp"] = (merged[f"{years_a}-Year_B"] - merged[f"{years_a}-Year_A"]) * 100

    display = merged[key_cols].copy()
    display["Annual A"] = (merged["Annual_A"] * 100).round(2).astype(str) + "%"
    display["Annual B"] = (merged["Annual_B"] * 100).round(2).astype(str) + "%"
    display["Annual (B - A)"] = merged["Annual_diff_pp"].round(2).astype(str) + " pp"
    display[f"{years_a}-Year A"] = (merged[f"{years_a}-Year_A"] * 100).round(2).astype(str) + "%"
    display[f"{years_b}-Year B"] = (merged[f"{years_b}-Year_B"] * 100).round(2).astype(str) + "%"
    if years_a == years_b:
        display[f"{years_a}-Year (B - A)"] = merged[f"{years_a}-Year_diff_pp"].round(2).astype(str) + " pp"
    return display


# ----------------------------
# UI START
# ----------------------------
PRESETS = {
    "Baseline (purely based on historical data)": {
        "total_unique": 320_711,
        "cap_regular": 65_000,
        "cap_masters": 20_000,
        "bachelor_share": 0.644,
        "wage_b": {1: 0.20, 2: 0.61, 3: 0.13, 4: 0.06},
        "wage_m": {1: 0.36, 2: 0.50, 3: 0.11, 4: 0.03},
        "years": 3,
        "simulations": DEFAULT_SIMULATIONS,
        "seed": DEFAULT_SEED,
    },
    "Lower total volume, bachelor share, and WL1 share": {
        "total_unique": 250_000,
        "cap_regular": 65_000,
        "cap_masters": 20_000,
        "bachelor_share": 0.55,
        "wage_b": {1: 0.14, 2: 0.67, 3: 0.13, 4: 0.06},
        "wage_m": {1: 0.30, 2: 0.56, 3: 0.11, 4: 0.03},
        "years": 3,
        "simulations": DEFAULT_SIMULATIONS,
        "seed": DEFAULT_SEED,
    },
    "Same total volume, more WL3/WL4": {
        "total_unique": 320_711,
        "cap_regular": 65_000,
        "cap_masters": 20_000,
        "bachelor_share": 0.60,
        "wage_b": {1: 0.10, 2: 0.55, 3: 0.22, 4: 0.13},
        "wage_m": {1: 0.25, 2: 0.45, 3: 0.20, 4: 0.10},
        "years": 3,
        "simulations": DEFAULT_SIMULATIONS,
        "seed": DEFAULT_SEED,
    },
}

calculator_tab, guide_tab = st.tabs(["Calculator", "Parameter Guide"])

with calculator_tab:
    mode = st.radio("Mode", ["Single scenario", "Compare two scenarios"], horizontal=True)

    if mode == "Single scenario":
        scenario_panel("S", "Scenario", PRESETS)
    else:
        col_a, col_b = st.columns(2)
        out_a, raw_a = scenario_panel("A", "Scenario A", PRESETS, container=col_a)
        out_b, raw_b = scenario_panel("B", "Scenario B", PRESETS, container=col_b)

        st.markdown("---")
        st.subheader("Comparison (Scenario B - Scenario A)")

        if out_a is None or out_b is None or raw_a is None or raw_b is None:
            st.info("Run both scenarios to view the comparison table.")
        else:
            years_a = int(out_a["inputs"]["years"])
            years_b = int(out_b["inputs"]["years"])
            comparison_df = compare_two(raw_a, raw_b, years_a=years_a, years_b=years_b)
            st.dataframe(comparison_df, use_container_width=True)

            st.download_button(
                "Download comparison as CSV",
                comparison_df.to_csv(index=False).encode("utf-8"),
                file_name="h1b_scenario_comparison.csv",
                mime="text/csv",
                key="cmp_download",
            )

with guide_tab:
    render_parameter_guide()
