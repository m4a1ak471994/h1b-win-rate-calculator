# H-1B Weighted Lottery Win Rate Calculator

A Streamlit app that estimates H-1B lottery win rates under a 2-round selection process with weighted tickets **by wage level and degree type**.

On Dec. 29, 2025, DHS/USCIS finalized an H-1B rule that introduces **weighted selection** by wage level (`WL1`-`WL4`). This app estimates win rates under that system while preserving the existent two-round structure. **The final rule itself does not publish the degree-split or multi-year win-rate calculations**, so this app computes them.

- Round 1 (`cap_regular`) selects from all applicants.
- Round 2 (`cap_masters`) selects from the remaining Masters/PhD applicants who were not selected in Round 1.
- Once a candidate wins in any round, that candidate is removed from later draws together with all of that candidate's tickets.

The app outputs annual win rates and multi-year win rates for Bachelors and Masters/PhD separately.

---

## Model Summary

### Ticket multipliers
Four wage levels are mapped to fixed ticket counts:

| Wage Level | Tickets |
|-----------:|--------:|
| WL1        | 1       |
| WL2        | 2       |
| WL3        | 3       |
| WL4        | 4       |

### Inputs
- Total applicants (`total_unique`): total number of unique candidates in the lottery.
- Regular cap (`cap_regular`): number of selections in Round 1.
- Masters cap (`cap_masters`): number of selections in Round 2 among remaining Masters/PhD candidates.
- Bachelor share (`bachelor_share`): fraction of applicants that are Bachelors. Masters/PhD share is `1 - bachelor_share`.
- Wage-level shares (`wage_b`, `wage_m`): wage-level composition within each degree group.
- Years (`years`): number of attempts used for the multi-year probability.
- Simulation runs (`simulations`): number of Monte Carlo trials used to estimate annual win rates.
- Random seed (`seed`): seed for reproducible simulation results.

Notes:
- Wage shares within each degree group are normalized if they do not sum to 1.
- If a degree group's wage shares sum to 0, the app raises an error instead of guessing a fallback allocation.

---

## How the Probability Is Computed

### Step 1) Convert wage shares to integer headcounts
Within each degree group, the app converts wage-level shares into integer candidate counts that sum to the group total.

### Step 2) Build the 8 simulation buckets
The app represents the lottery state using 8 homogeneous buckets:
- `Bachelors-WL1` through `Bachelors-WL4`
- `Masters/PhD-WL1` through `Masters/PhD-WL4`

For each bucket, the app tracks:
- the number of remaining candidates in that bucket
- the ticket count per candidate from the fixed multipliers above

### Step 3) Simulate Round 1
For each simulation run, the app repeatedly draws winners from all 8 buckets using exact bucket weights.

If bucket `b` has `n_b` remaining candidates and each candidate has `w_b` tickets, then that bucket contributes:

`T_b = n_b * w_b`

The probability that the next Round 1 winner comes from bucket `b` is:

`P(b) = T_b / sum(T_j)`

Once a winner is drawn from a bucket, that bucket's remaining count is reduced by 1, which exactly matches removing one unique candidate and all of that candidate's tickets.

### Step 4) Simulate Round 2
After Round 1 finishes, the app simulates the masters cap from the remaining `Masters/PhD` buckets only, using the same weighted-draw logic on the updated remaining counts.

### Step 5) Estimate annual win rates
Across all simulation runs, the app counts how often candidates in each profile and wage-level bucket are selected. The annual win rate for a bucket is:

`annual win rate = total wins in bucket / (bucket size * simulation runs)`

### Step 6) Compute multi-year probability
For `years` independent attempts:

`p_multi = 1 - (1 - p_annual) ** years`

---

## Accuracy and Tradeoffs

This version is materially more accurate than the earlier closed-form approximations because it simulates unique candidates across both rounds.

The current implementation uses an exact bucket-level representation of the same lottery process, so it is mathematically equivalent to an explicit candidate-level simulation but much faster.

Tradeoffs:
- More simulation runs produce more stable estimates.
- Fewer simulation runs are faster but noisier.
- Results are Monte Carlo estimates, not exact closed-form probabilities.

If you need reproducible results, keep the same random seed.

---

## App Features

- Exact bucket-level Monte Carlo simulation of the full two-round process.
- Preset sync: switching presets updates input widgets immediately.
- Preset locking: preset scenarios are fixed; choose `Custom` to edit inputs.
- Compare mode: side-by-side comparison of two scenarios, including deltas.
- CSV export: download per-scenario results and comparison tables.
- Reproducibility controls through simulation count and random seed.

---

## Presets

The app includes:
- Baseline (historical data): a default configuration based on historical data from the DHS December 29, 2025 rule.
- Additional presets for sensitivity analysis, such as lower total applicants or different wage-level mixes.

Choose `Custom` to modify parameters.

## Reference

DHS/USCIS final rule on H-1B weighted selection (December 29, 2025).

Official copy: https://public-inspection.federalregister.gov/2025-23853.pdf
