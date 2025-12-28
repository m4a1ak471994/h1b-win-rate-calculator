# H-1B Weighted Lottery Win Rate Calculator (Streamlit)

A Streamlit app that estimates H-1B lottery win rates under a **2-round** selection process with **weighted tickets** by wage level.

- **Round 1 (Regular cap):** selects from *all* tickets (Bachelors + Masters/PhD).
- **Round 2 (Masters cap):** selects from *remaining* Masters/PhD tickets that did not win in Round 1.

The app outputs **annual win rates** and **multi-year win rates** (e.g., over 3 attempts).

---

## Model Summary

### Ticket multipliers (fixed policy assumption)
Wage levels map to ticket counts:

| Wage Level | Tickets |
|-----------:|--------:|
| WL1        | 1       |
| WL2        | 2       |
| WL3        | 3       |
| WL4        | 4       |

> These multipliers are treated as fixed constants in this app.

### Inputs
- **Total applicants (unique)** (`total_unique`): total number of individuals in the lottery.
- **Regular cap (Round 1)** (`cap_regular`): number of selections in Round 1.
- **Masters cap (Round 2)** (`cap_masters`): number of selections in Round 2 among remaining Masters/PhD candidates.
- **Bachelor share** (`bachelor_share`): fraction of total applicants that are Bachelors; Masters/PhD share is `1 - bachelor_share`.
- **Wage-level shares** (`wage_b`, `wage_m`): wage-level composition within each degree group.
  - The app will **normalize** shares within each degree group if they do not sum to 1.
  - If the sum is 0, the residual allocation logic effectively assigns all candidates to WL4.
- **Probability method** (`method`):
  - `independent`: per-candidate probability = `1 - (1 - p_ticket)^m`
  - `linear`: per-candidate probability = `min(1, m * p_ticket)`
- **Years** (`years`): number of attempts (used for multi-year probability).

### How the probability is computed

1) Convert wage shares into **integer headcounts** per wage level (WL1–WL4) for each degree group.

2) Convert headcounts into **weighted tickets** using the fixed multipliers.

3) **Round 1:** compute per-ticket win probability
$$
p_{1,\text{ticket}} = \min\left(1,\ \frac{\text{cap\_regular}}{\text{total\_tickets\_r1}}\right)
$$
Convert it to per-candidate win probability for each wage level (m tickets).

4) **Round 2:** estimate how many Masters/PhD candidates remain after Round 1 (in expectation), form remaining tickets, and compute:

$$
p_{2,\text{ticket}} = \min\left(1,\ \frac{\text{cap\_masters}}{\text{total\_tickets\_r2}}\right)
$$

Then compute per-candidate conditional win probabilities for Masters/PhD by wage level.

5) Combine Masters/PhD annual probability:
$$
p_{\text{annual}} = p_1 + (1-p_1)\cdot p_{2|\text{no win in r1}}
$$
Bachelors only participate in Round 1.

6) Multi-year probability over `years` attempts:
$$
p_{\text{multi}} = 1 - (1 - p_{\text{annual}})^{\text{years}}
$$

> Note: the app uses an **expected survivors** approximation for Round 2 rather than simulating discrete draws.

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

You can always choose **Custom** to modify parameters.

---

## Running Locally

### 1) Install dependencies
```bash
pip install -r requirements.txt
