

import streamlit as st
import pandas as pd

# ----------------------------
# SEO & PAGE CONFIGURATION
# ----------------------------
# This must be the very first Streamlit command.
# The 'page_title' here is what shows up in Google Search results (the blue link text).
st.set_page_config(
    page_title="H-1B Weighted Lottery Win Rate Calculator (2025 Rule)",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://public-inspection.federalregister.gov/2025-23853.pdf',
        'About': "H-1B Weighted Lottery Calculator based on DHS Dec 29, 2025 Final Rule."
    }
)

# ----------------------------
# VISIBLE UI CONTENT
# ----------------------------

st.title("H-1B Weighted Lottery Win Rate Calculator")

# This is your EXACT text, rendered as HTML so Google can read it.
st.markdown("""
This app estimates H-1B selection probabilities under the DHS/USCIS **weighted lottery** rule (Dec 29, 2025). 
Weights are based on **wage levels** (WL1–WL4): **WL1 = 1 ticket, WL2 = 2, WL3 = 3, WL4 = 4**, and each ticket represents one lottery entry with the same chance of being selected. 

The app models the **two-round** process (regular cap + advanced-degree cap) and reports **annual** and **multi-year win rates** separately for Bachelors and Masters/PhD. 
The DHS document provides illustrative comparisons but does not publish degree-split or multi-year win-rate calculations.

**Rule text:** https://public-inspection.federalregister.gov/2025-23853.pdf
""")

# ----------------------------
# LOGIC & CALCULATOR (Unchanged)
# ----------------------------

# Fixed ticket multipliers for different wage levels (policy)
MULTIPLIERS = {1: 1, 2: 2, 3: 3, 4: 4}

def allocate_counts(total, shares_by_level, levels=(1, 2, 3, 4), normalize=True):
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
    return sum(counts[lv] * MULTIPLIERS[lv] for lv in counts)


def per_candidate_prob(p_ticket, m, method="independent"):
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

    bach_tickets = tickets_from_counts(bachelors_counts)
    mast_tickets = tickets_from_counts(masters_counts)
    total_tickets_r1 = bach_tickets + mast_tickets

    p1_ticket = 1.0 if total_tickets_r1 <= 0 else min(1.0, cap_regular / total_tickets_r1)

    p1_by_level = {
        lv: per_candidate_prob(p1_ticket, MULTIPLIERS[lv], method=method)
        for lv in MULTIPLIERS
    }

    exp_mast_winners_r1 = {lv: masters_counts[lv] * p1_by_level[lv] for lv in MULTIPLIERS}
    mast_survivors = {lv: masters_counts[lv] - exp_mast_winners_r1[lv] for lv in MULTIPLIERS}

    total_tickets_r2 = sum(mast_survivors[lv] * MULTIPLIERS[lv] for lv in MULTIPLIERS)
    p2_ticket = 1.0 if total_tickets_r2 <= 0 else min(1.0, cap_masters / total_tickets_r2)

    p2_cond_by_level = {
        lv: per_candidate_prob(p2_ticket, MULTIPLIERS[lv], method=method)
        for lv in MULTIPLIERS
    }

    annual_bachelors = {lv: p1_by_level[lv] for lv in MULTIPLIERS}
    annual_masters = {
        lv: p1_by_level[lv] + (1.0 - p1_by_level[lv]) * p2_cond_by_level[lv]
        for lv in MULTIPLIERS
    }

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
        "results": {
            "annual_win_rate": {
                "Bachelors": {f"WL{lv}": annual_bachelors[lv] for lv in sorted(MULTIPLIERS)},
                "Masters/PhD": {f"WL{lv}": annual_masters[lv] for lv in sorted(MULTIPLIERS)},
            },
            "multi_year_win_rate": {
                "Bachelors": {f"WL{lv}": multi_bachelors[lv] for lv in sorted(MULTIPLIERS)},
                "Masters/PhD": {f"WL{lv}": multi_masters[lv] for lv in sorted(MULTIPLIERS)},
            },
        },
    }

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


def _apply_defaults_to_session(key_prefix, defaults):
    st.session_state[f"{key_prefix}_total_unique"] = int(defaults["total_unique"])
    st.session_state[f"{key_prefix}_cap_regular"] = int(defaults["cap_regular"])
    st.session_state[f"{key_prefix}_cap_masters"] = int(defaults["cap_masters"])
    st.session_state[f"{key_prefix}_bachelor_share"] = float(defaults["bachelor_share"])
    st.session_state[f"{key_prefix}_years"] = int(defaults["years"])
    st.session_state[f"{key_prefix}_method"] = str(defaults["method"])

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
        locked = (preset_name != "Custom")

        if f"{key_prefix}_total_unique" not in st.session_state:
            init_name = preset_name if preset_name in preset_dict else default_preset
            _apply_defaults_to_session(key_prefix, preset_dict[init_name])

        colA, colB = st.columns(2)
        with colA:
            total_unique = st.number_input("Total applicants", min_value=0, step=1000, key=f"{key_prefix}_total_unique", disabled=locked)
            cap_regular = st.number_input("Round 1 Regular cap", min_value=0, step=1000, key=f"{key_prefix}_cap_regular", disabled=locked)
            bachelor_share = st.slider("Bachelor share", 0.0, 1.0, step=0.001, key=f"{key_prefix}_bachelor_share", disabled=locked)

        with colB:
            cap_masters = st.number_input("Round 2 cap (MS/PhD)", min_value=0, step=1000, key=f"{key_prefix}_cap_masters", disabled=locked)
            years = st.number_input("Years", min_value=1, step=1, key=f"{key_prefix}_years", disabled=locked)
            method = st.selectbox("Probability method", ["linear", "independent"], key=f"{key_prefix}_method", disabled=locked)

        st.markdown("**Wage-level shares** within each applicant degree group")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Bachelors**")
            b1 = st.number_input("BA WL1", min_value=0.0, step=0.01, format="%.4f", key=f"{key_prefix}_b1", disabled=locked)
            b2 = st.number_input("BA WL2", min_value=0.0, step=0.01, format="%.4f", key=f"{key_prefix}_b2", disabled=locked)
            b3 = st.number_input("BA WL3", min_value=0.0, step=0.01, format="%.4f", key=f"{key_prefix}_b3", disabled=locked)
            b4 = st.number_input("BA WL4", min_value=0.0, step=0.01, format="%.4f", key=f"{key_prefix}_b4", disabled=locked)
        
        with c2:
            st.markdown("**Masters/PhD**")
            m1 = st.number_input("MS WL1", min_value=0.0, step=0.01, format="%.4f", key=f"{key_prefix}_m1", disabled=locked)
            m2 = st.number_input("MS WL2", min_value=0.0, step=0.01, format="%.4f", key=f"{key_prefix}_m2", disabled=locked)
            m3 = st.number_input("MS WL3", min_value=0.0, step=0.01, format="%.4f", key=f"{key_prefix}_m3", disabled=locked)
            m4 = st.number_input("MS WL4", min_value=0.0, step=0.01, format="%.4f", key=f"{key_prefix}_m4", disabled=locked)

        wage_shares_bachelors = {1: b1, 2: b2, 3: b3, 4: b4}
        wage_shares_masters = {1: m1, 2: m2, 3: m3, 4: m4}

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
        return out, raw_df


def compare_two(rawA, rawB, yearsA, yearsB):
    key_cols = ["Profile", "Wage Level"]
    a = rawA.copy()
    b = rawB.copy()
    a = a.rename(columns={"Annual": "Annual_A", f"{yearsA}-Year": f"{yearsA}-Year_A"})
    b = b.rename(columns={"Annual": "Annual_B", f"{yearsB}-Year": f"{yearsB}-Year_B"})
    merged = a.merge(b, on=key_cols, how="inner")
    
    merged["Annual_diff_pp"] = (merged["Annual_B"] - merged["Annual_A"]) * 100
    if yearsA == yearsB:
        merged[f"{yearsA}-Year_diff_pp"] = (merged[f"{yearsA}-Year_B"] - merged[f"{yearsA}-Year_A"]) * 100

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
        "method": "independent",
    },
    "Lower total volume and bachelor share, more WL2": {
        "total_unique": 250_000,
        "cap_regular": 65_000,
        "cap_masters": 20_000,
        "bachelor_share": 0.58,
        "wage_b": {1: 0.12, 2: 0.74, 3: 0.10, 4: 0.04},
        "wage_m": {1: 0.40, 2: 0.52, 3: 0.06, 4: 0.02},
        "years": 3,
        "method": "independent",
    },
    "Same total volume, more WL3/WL4": {
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

mode = st.radio("Mode", ["Single scenario", "Compare two scenarios"], horizontal=True)

if mode == "Single scenario":
    scenario_panel("S", "Scenario", PRESETS)
else:
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