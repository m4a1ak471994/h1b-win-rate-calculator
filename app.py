
"""
H-1B (weighted tickets) win-rate calculator for the 2-round lottery:
- Round 1: Regular cap (e.g., 65,000) among ALL tickets (Bachelors + Masters/PhD)
- Round 2: Masters cap (e.g., 20,000) among remaining Masters/PhD candidates

You can run many "scenarios" by changing:
- total_unique: total numbers of applicants (e.g., 320,711)
- cap_regular / cap_masters (e.g., 65k + 20k)
- bachelor_share vs masters_share (e.g., 64.4% vs 35.6%)
- wage-level shares within each degree group
- probability method (default "linear")

Note: Ticket multipliers are FIXED by policy here:
WL1..WL4 => 1..4 tickets respectively.
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

    # Allocate first N-1 levels
    for lv in levels[:-1]:
        c = int(round(total * shares[lv]))
        c = max(0, min(c, remaining))
        counts[lv] = c
        remaining -= c

    # Residual to force exact sum
    counts[levels[-1]] = remaining
    return counts


def tickets_from_counts(counts):
    """
    Convert headcounts into weighted tickets using fixed WL multipliers.
    """
    return sum(counts[lv] * MULTIPLIERS[lv] for lv in counts)


def per_candidate_prob(p_ticket, m, method="linear"):
    """
    Convert per-ticket win prob to per-candidate win prob given m tickets.
    method:
      - "linear":        p = min(1, m * p_ticket)   (your spreadsheet-style approximation)
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
        },
    }


# ----------------------------
# Streamlit UI
# ----------------------------

st.set_page_config(page_title="H-1B Win Rate Calculator", layout="centered")
st.title("H-1B Weighted Lottery Win Rate Calculator")

st.caption(
    "Two-round model: Round 1 (regular cap) across all tickets, then Round 2 (masters cap) across remaining Masters/PhD tickets."
)

PRESETS = {
    "Baseline (historical)": {
        "total_unique": 320_711,
        "cap_regular": 65_000,
        "cap_masters": 20_000,
        "bachelor_share": 0.644,
        "wage_b": {1: 0.20, 2: 0.61, 3: 0.13, 4: 0.06},
        "wage_m": {1: 0.36, 2: 0.50, 3: 0.11, 4: 0.03},
        "years": 3,
        "method": "linear",
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

preset_name = st.selectbox("Scenario preset", ["Custom"] + list(PRESETS.keys()))

# Defaults: if Custom, start from baseline; otherwise use chosen preset
defaults = PRESETS["Baseline (historical)"] if preset_name == "Custom" else PRESETS[preset_name]

st.subheader("Inputs")
colA, colB = st.columns(2)

with colA:
    total_unique = st.number_input(
        "Total applicants (unique)",
        min_value=0,
        value=int(defaults["total_unique"]),
        step=1000,
    )
    cap_regular = st.number_input(
        "Regular cap (Round 1)",
        min_value=0,
        value=int(defaults["cap_regular"]),
        step=1000,
    )
    bachelor_share = st.slider(
        "Bachelor share",
        0.0,
        1.0,
        float(defaults["bachelor_share"]),
        0.001,
    )

with colB:
    cap_masters = st.number_input(
        "Masters cap (Round 2)",
        min_value=0,
        value=int(defaults["cap_masters"]),
        step=1000,
    )
    years = st.number_input(
        "Years (e.g., STEM OPT attempts)",
        min_value=1,
        value=int(defaults["years"]),
        step=1,
    )
    method = st.selectbox(
        "Probability method",
        ["linear", "independent"],
        index=0 if defaults["method"] == "linear" else 1,
    )

st.markdown("### Wage-level shares (normalized within each degree group)")
c1, c2 = st.columns(2)

with c1:
    st.markdown("**Bachelors**")
    b1 = st.number_input("BA WL1 share", min_value=0.0, value=float(defaults["wage_b"][1]), step=0.01, format="%.4f")
    b2 = st.number_input("BA WL2 share", min_value=0.0, value=float(defaults["wage_b"][2]), step=0.01, format="%.4f")
    b3 = st.number_input("BA WL3 share", min_value=0.0, value=float(defaults["wage_b"][3]), step=0.01, format="%.4f")
    b4 = st.number_input("BA WL4 share", min_value=0.0, value=float(defaults["wage_b"][4]), step=0.01, format="%.4f")

with c2:
    st.markdown("**Masters/PhD**")
    m1 = st.number_input("MS WL1 share", min_value=0.0, value=float(defaults["wage_m"][1]), step=0.01, format="%.4f")
    m2 = st.number_input("MS WL2 share", min_value=0.0, value=float(defaults["wage_m"][2]), step=0.01, format="%.4f")
    m3 = st.number_input("MS WL3 share", min_value=0.0, value=float(defaults["wage_m"][3]), step=0.01, format="%.4f")
    m4 = st.number_input("MS WL4 share", min_value=0.0, value=float(defaults["wage_m"][4]), step=0.01, format="%.4f")

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

annual = out["results"]["annual_win_rate"]
multi = out["results"]["multi_year_win_rate"]

rows = []
for profile in ["Bachelors", "Masters/PhD"]:
    for wl in ["WL1", "WL2", "WL3", "WL4"]:
        rows.append(
            {
                "Profile": profile,
                "Wage Level": wl,
                "Annual Win Rate": annual[profile][wl],
                f"{years}-Year Win Rate": multi[profile][wl],
            }
        )

df = pd.DataFrame(rows)
df["Annual Win Rate"] = (df["Annual Win Rate"] * 100).round(2).astype(str) + "%"
df[f"{years}-Year Win Rate"] = (df[f"{years}-Year Win Rate"] * 100).round(2).astype(str) + "%"

st.subheader("Results")
st.dataframe(df, use_container_width=True)

st.download_button(
    "Download results as CSV",
    df.to_csv(index=False).encode("utf-8"),
    file_name="h1b_win_rates.csv",
    mime="text/csv",
)

with st.expander("Intermediate numbers (debug)"):
    st.json(out["intermediate"])

