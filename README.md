# H-1B Weighted Lottery Win Rate Calculator

A Streamlit app that estimates H-1B lottery win rates under a 2-round selection process with weighted tickets by wage level and degree type.

On December 29, 2025, DHS/USCIS finalized an H-1B rule that introduces weighted selection by wage level (`WL1`-`WL4`). This app estimates win rates under that system while preserving the two-round structure. The final rule itself does not publish degree-split or multi-year win-rate calculations, so this app computes them.

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

### Step 2) Build a candidate pool
Each candidate is represented explicitly in the simulation with:
- a degree group (`Bachelors` or `Masters/PhD`)
- a wage level (`WL1`-`WL4`)
- a ticket count from the fixed multipliers above

### Step 3) Simulate Round 1
For each simulation run, the app repeatedly draws unique winners from the full candidate pool using ticket weights.

A candidate with more tickets has a higher chance of being selected, but once selected:
- the candidate wins at most once
- all of that candidate's tickets are removed immediately

### Step 4) Simulate Round 2
After Round 1 finishes, the app simulates the masters cap from the remaining Masters/PhD candidates only.

### Step 5) Estimate annual win rates
Across all simulation runs, the app counts how often candidates in each profile and wage-level bucket are selected. The annual win rate for a bucket is:

`annual win rate = total wins in bucket / (bucket size * simulation runs)`

### Step 6) Compute multi-year probability
For `years` independent attempts:

`p_multi = 1 - (1 - p_annual) ** years`

---

## Accuracy and Tradeoffs

This version is materially more accurate than the earlier closed-form approximations because it simulates unique candidates across both rounds.

Tradeoffs:
- More simulation runs produce more stable estimates.
- Fewer simulation runs are faster but noisier.
- Results are estimates, not exact closed-form probabilities.

If you need reproducible results, keep the same random seed.

---

## App Features

- Candidate-level Monte Carlo simulation of the full two-round process.
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

---

## Running the App

Install dependencies from [requirements.txt](c:\Users\Hank_desktop\Dropbox\Visa\h1b-win-rate-calculator\requirements.txt), then run:

```bash
streamlit run app.py
```

---

## Reference

DHS/USCIS final rule on H-1B weighted selection (December 29, 2025).

Official copy: https://public-inspection.federalregister.gov/2025-23853.pdf
