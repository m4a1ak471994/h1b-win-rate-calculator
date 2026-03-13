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
This app estimates H-1B selection probabilities under the DHS/USCIS **weighted lottery** rule (Dec. 29, 2025).
Weights are based on **wage levels** (WL1-WL4): **WL1 = 1 ticket, WL2 = 2, WL3 = 3, WL4 = 4**.

The app now uses a **candidate-level Monte Carlo simulation** of the two-round process:
- **Round 1 (Regular cap):** selects unique candidates from all applicants.
- **Round 2 (Masters cap):** selects unique candidates from the remaining Masters/PhD applicants.

Once a candidate is selected in any round, all of that candidate's tickets are removed from later draws.
The app reports **annual** and **multi-year win rates** separately for Bachelors and Masters/PhD.

**Rule text:** https://public-inspection.federalregister.gov/2025-23853.pdf
"""
)

# ----------------------------
# LOGIC & CALCULATOR
# ----------------------------

MULTIPLIERS = {1: 1, 2: 2, 3: 3, 4: 4}
DEFAULT_SIMULATIONS = 200
DEFAULT_SEED = 42


class FenwickTree:
    def __init__(self, values):
        self.values = [float(v) for v in values]
        self.size = len(self.values)
        self.tree = [0.0] * (self.size + 1)
        for index, value in enumerate(self.values, start=1):
            self.tree[index] += value
            parent = index + (index & -index)
            if parent <= self.size:
                self.tree[parent] += self.tree[index]

    def total(self):
        return self.prefix_sum(self.size - 1) if self.size else 0.0

    def prefix_sum(self, index):
        result = 0.0
        index += 1
        while index > 0:
            result += self.tree[index]
            index -= index & -index
        return result

    def add(self, index, delta):
        index += 1
        while index <= self.size:
            self.tree[index] += delta
            index += index & -index

    def remove(self, index):
        current = self.values[index]
        if current <= 0:
            return 0.0
        self.values[index] = 0.0
        self.add(index, -current)
        return current

    def find_by_cumulative_weight(self, target):
        index = 0
        bit = 1 << (self.size.bit_length() - 1)
        while bit:
            candidate = index + bit
            if candidate <= self.size and self.tree[candidate] <= target:
                target -= self.tree[candidate]
                index = candidate
            bit >>= 1
        return index


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


def build_candidate_pool(bachelors_counts, masters_counts):
    candidate_group_ids = []
    candidate_weights = []
    candidate_is_master = []
    group_rows = []
    group_sizes = []

    for profile, counts, is_master in [
        ("Bachelors", bachelors_counts, False),
        ("Masters/PhD", masters_counts, True),
    ]:
        for level in sorted(MULTIPLIERS):
            wage_label = f"WL{level}"
            count = int(counts[level])
            weight = MULTIPLIERS[level]
            group_id = len(group_rows)
            group_rows.append((profile, wage_label))
            group_sizes.append(count)
            candidate_group_ids.extend([group_id] * count)
            candidate_weights.extend([weight] * count)
            candidate_is_master.extend([is_master] * count)

    masters_total = sum(1 for flag in candidate_is_master if flag)
    masters_weights = [
        candidate_weights[index] if candidate_is_master[index] else 0
        for index in range(len(candidate_weights))
    ]

    return {
        "group_rows": group_rows,
        "group_sizes": group_sizes,
        "candidate_group_ids": candidate_group_ids,
        "candidate_weights": candidate_weights,
        "candidate_is_master": candidate_is_master,
        "masters_weights": masters_weights,
        "masters_total": masters_total,
    }


def run_single_simulation(pool, cap_regular, cap_masters, rng):
    wins_by_group = [0] * len(pool["group_rows"])
    total_tree = FenwickTree(pool["candidate_weights"])
    masters_tree = FenwickTree(pool["masters_weights"])
    remaining_candidates = len(pool["candidate_weights"])
    remaining_masters = pool["masters_total"]

    for _ in range(min(int(cap_regular), remaining_candidates)):
        total_weight = total_tree.total()
        if total_weight <= 0:
            break

        target = rng.random() * total_weight
        candidate_index = total_tree.find_by_cumulative_weight(target)
        removed_weight = total_tree.remove(candidate_index)
        if removed_weight <= 0:
            continue

        wins_by_group[pool["candidate_group_ids"][candidate_index]] += 1
        if pool["candidate_is_master"][candidate_index]:
            masters_tree.remove(candidate_index)
            remaining_masters -= 1

    for _ in range(min(int(cap_masters), remaining_masters)):
        total_weight = masters_tree.total()
        if total_weight <= 0:
            break

        target = rng.random() * total_weight
        candidate_index = masters_tree.find_by_cumulative_weight(target)
        removed_weight = masters_tree.remove(candidate_index)
        if removed_weight <= 0:
            continue

        total_tree.remove(candidate_index)
        wins_by_group[pool["candidate_group_ids"][candidate_index]] += 1
        remaining_masters -= 1

    return wins_by_group


@st.cache_data(show_spinner=False)
def simulate_annual_rates(bachelors_counts_items, masters_counts_items, cap_regular, cap_masters, simulations, seed):
    bachelors_counts = {level: int(count) for level, count in bachelors_counts_items}
    masters_counts = {level: int(count) for level, count in masters_counts_items}
    pool = build_candidate_pool(bachelors_counts, masters_counts)
    rng = random.Random(int(seed))
    total_wins = [0] * len(pool["group_rows"])

    for _ in range(int(simulations)):
        trial_wins = run_single_simulation(pool, cap_regular, cap_masters, rng)
        for group_id, wins in enumerate(trial_wins):
            total_wins[group_id] += wins

    annual_rates = {"Bachelors": {}, "Masters/PhD": {}}
    for group_id, (profile, wage_label) in enumerate(pool["group_rows"]):
        group_size = pool["group_sizes"][group_id]
        if group_size <= 0:
            annual_probability = 0.0
        else:
            annual_probability = total_wins[group_id] / (group_size * int(simulations))
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
            "method": "candidate_level_simulation",
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

        wage_shares_bachelors = {1: b1, 2: b2, 3: b3, 4: b4}
        wage_shares_masters = {1: m1, 2: m2, 3: m3, 4: m4}

        try:
            with st.spinner("Running candidate-level simulation..."):
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
        except ValueError as exc:
            st.error(str(exc))
            st.stop()

        raw_df = build_raw_results_df(out, years=years)
        view_df = format_percent_df(raw_df, years=years)

        st.caption(
            f"Method: candidate-level Monte Carlo simulation | Runs: {int(simulations):,} | Seed: {int(seed)}"
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
    "Lower total volume and bachelor share, more WL2": {
        "total_unique": 250_000,
        "cap_regular": 65_000,
        "cap_masters": 20_000,
        "bachelor_share": 0.58,
        "wage_b": {1: 0.12, 2: 0.74, 3: 0.10, 4: 0.04},
        "wage_m": {1: 0.40, 2: 0.52, 3: 0.06, 4: 0.02},
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

mode = st.radio("Mode", ["Single scenario", "Compare two scenarios"], horizontal=True)

if mode == "Single scenario":
    scenario_panel("S", "Scenario", PRESETS)
else:
    col_a, col_b = st.columns(2)
    out_a, raw_a = scenario_panel("A", "Scenario A", PRESETS, container=col_a)
    out_b, raw_b = scenario_panel("B", "Scenario B", PRESETS, container=col_b)

    years_a = int(out_a["inputs"]["years"])
    years_b = int(out_b["inputs"]["years"])

    st.markdown("---")
    st.subheader("Comparison (Scenario B - Scenario A)")
    comparison_df = compare_two(raw_a, raw_b, years_a=years_a, years_b=years_b)
    st.dataframe(comparison_df, use_container_width=True)

    st.download_button(
        "Download comparison as CSV",
        comparison_df.to_csv(index=False).encode("utf-8"),
        file_name="h1b_scenario_comparison.csv",
        mime="text/csv",
        key="cmp_download",
    )
