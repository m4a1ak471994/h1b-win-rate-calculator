# H-1B Weighted Lottery Win Rate Calculator (Streamlit)

A Streamlit app that estimates H-1B lottery win rates under a 2-round selection process with weighted tickets **by wage level and degree type**.

- **Round 1 (Regular cap):** selects from *all* tickets (Bachelors + Masters/PhD).
- **Round 2 (Masters cap):** selects from *remaining* Masters/PhD candidates who did not win in Round 1.

The app outputs **annual win rates** and **multi-year win rates** (e.g., over 3 attempts for candidates with OPT STEM extension) for Bachelors and Masters/PhD separately.

---

## Model Summary

### Ticket multipliers (fixed assumption)
Four wage levels are mapped to different ticket counts:

| Wage Level | Tickets |
|-----------:|--------:|
| WL1        | 1       |
| WL2        | 2       |
| WL3        | 3       |
| WL4        | 4       |

Source: DHS/USCIS final rule on H-1B weighted selection (Dec. 29, 2025).
Official copy: https://public-inspection.federalregister.gov/2025-23853.pdf

### Inputs
- **Total applicants (unique)** (`total_unique`): total number of individuals in the lottery.
- **Regular cap (Round 1)** (`cap_regular`): number of selections in Round 1.
- **Masters cap (Round 2)** (`cap_masters`): number of selections in Round 2 among remaining Masters/PhD candidates.
- **Bachelor share** (`bachelor_share`): fraction of applicants that are Bachelors; Masters/PhD share is `1 - bachelor_share`.
- **Wage-level shares** (`wage_b`, `wage_m`): wage-level composition within each degree group.
  - The app will **normalize** shares within each degree group if they do not sum to 1.
  - If the sum is 0, the residual allocation logic effectively assigns all candidates to WL4.
- **Probability method** (`method`):
  - `independent`: per-candidate probability for `k` tickets is `p = 1 - (1 - p_ticket) ** k`
  - `linear`: per-candidate probability for `k` tickets is `p = min(1, k * p_ticket)`
- **Years** (`years`): number of attempts (used for multi-year probability).

---

## How the Probability Is Computed

### Step 1) Convert wage shares → integer headcounts
Within each degree group, shares are converted to integer counts that sum to the group total.

### Step 2) Convert headcounts → weighted tickets
Tickets are computed using the fixed multipliers (WL1..WL4 → 1..4 tickets).

### Step 3) Round 1 (Regular cap)
Compute per-ticket win probability:

`p1_ticket = min(1, cap_regular / total_tickets_r1)`

(If `total_tickets_r1` is 0, the implementation guards and treats the probability as 1.)

Convert per-ticket probability to per-candidate probability by wage level (`k` tickets):

- Independent model: `p1_candidate = 1 - (1 - p1_ticket) ** k`
- Linear model:      `p1_candidate = min(1, k * p1_ticket)`

Bachelors’ annual win probability is simply:

`p_annual_bachelors = p1_candidate`

### Step 4) Round 2 (Masters cap)
Estimate Masters/PhD winners in Round 1 **in expectation**, then compute the rest:

`expected_winners_r1 = count * p1_candidate`  
`remaining = count - expected_winners_r1`

Compute Round 2 per-ticket win probability among remaining Masters/PhD:

`p2_ticket = min(1, cap_masters / total_tickets_r2)`

Convert to per-candidate conditional probability by wage level (`k` tickets):

- Independent model: `p2_cond = 1 - (1 - p2_ticket) ** k`
- Linear model:      `p2_cond = min(1, k * p2_ticket)`

Combine Masters/PhD annual probability across rounds:

`p_annual_masters = p1_candidate + (1 - p1_candidate) * p2_cond`

### Step 5) Multi-year probability
For `years` independent attempts:

`p_multi = 1 - (1 - p_annual) ** years`

---

## App Features

- **Preset sync:** switching presets updates input widgets immediately.
- **Preset locking:** preset scenarios are fixed; choose **Custom** to edit inputs.
- **Compare mode:** side-by-side comparison of two scenarios (A vs B), including deltas.
- **CSV export:** download per-scenario results and comparison tables.

---

## Presets

The app includes:
- **Baseline (historical data):** a default configuration (edit values in `PRESETS`).
- Additional presets for sensitivity analysis (e.g., lower total applicants, different wage-level mixes).

Choose **Custom** to modify parameters.

---

## Running Locally

### 1) Install dependencies
```bash
pip install -r requirements.txt

