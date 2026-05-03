"""Generate synthetic SaaS product-event data for the analytics dashboard.

Output: events.csv with columns (user_id, event_date, event_type, plan,
source_channel, feature_id) covering 3,000 users and ~150,000 events
over 14 months.

Design: plan-tier-specific funnel rates, feature-adoption probabilities,
and retention curves are baked in so the dashboard's visualisations
show realistic, interpretable patterns:
- Free funnel:       28 % activate, 25 % retained at week 12
- Pro funnel:        62 % activate, 72 % retained at week 12
- Enterprise funnel: 78 % activate, 88 % retained at week 12
- F5_API adoption:    5 % on Free vs 85 % on Enterprise

Run once locally to regenerate; output is committed so the Streamlit
dashboard works on first launch without running this script.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
N_USERS = 3000
START_DATE = date(2024, 9, 1)
END_DATE = date(2026, 4, 28)

PLANS = ["Free", "Pro", "Enterprise"]
PLAN_WEIGHTS = [0.65, 0.30, 0.05]

CHANNELS = [
    "Organic", "Paid_Search", "Paid_Social", "Referral",
    "Direct", "Content", "Affiliate", "Partner",
]
CHANNEL_WEIGHTS = [0.30, 0.20, 0.15, 0.12, 0.10, 0.07, 0.04, 0.02]

FEATURES = ["F1_Search", "F2_Reports", "F3_Integrations", "F4_Collaboration", "F5_API"]

# Marginal funnel rates (P(reach this stage | signup)). Conditional rates
# are derived from these.
FUNNEL = {
    "Free":       {"verify": 0.62, "first_session": 0.42, "first_action": 0.28},
    "Pro":        {"verify": 0.85, "first_session": 0.75, "first_action": 0.62},
    "Enterprise": {"verify": 0.92, "first_session": 0.88, "first_action": 0.78},
}

# Per-feature adoption probability among activated users, by plan.
# Index aligns with FEATURES.
FEATURE_ADOPTION = {
    "Free":       [0.65, 0.40, 0.10, 0.20, 0.05],
    "Pro":        [0.85, 0.75, 0.55, 0.65, 0.30],
    "Enterprise": [0.95, 0.92, 0.88, 0.90, 0.85],
}

# P(retained at week 4) and P(retained at week 12) among activated users.
RETENTION = {
    "Free":       {"w4": 0.45, "w12": 0.25},
    "Pro":        {"w4": 0.85, "w12": 0.72},
    "Enterprise": {"w4": 0.95, "w12": 0.88},
}


def main() -> None:
    rng = np.random.default_rng(SEED)
    rows: list[dict] = []
    span_days = (END_DATE - START_DATE).days

    for uid in range(1, N_USERS + 1):
        days_offset = int(rng.integers(0, span_days - 30))
        signup_date = START_DATE + timedelta(days=days_offset)
        plan = str(rng.choice(PLANS, p=PLAN_WEIGHTS))
        channel = str(rng.choice(CHANNELS, p=CHANNEL_WEIGHTS))

        rows.append({
            "user_id": uid, "event_date": signup_date,
            "event_type": "signup", "plan": plan,
            "source_channel": channel, "feature_id": None,
        })

        funnel = FUNNEL[plan]

        # Email verified
        if rng.random() >= funnel["verify"]:
            continue
        verify_date = signup_date + timedelta(days=int(rng.integers(0, 4)))
        rows.append({
            "user_id": uid, "event_date": verify_date,
            "event_type": "email_verified", "plan": plan,
            "source_channel": channel, "feature_id": None,
        })

        # First session (conditional on verify)
        cond_session = funnel["first_session"] / funnel["verify"]
        if rng.random() >= cond_session:
            continue
        session_date = verify_date + timedelta(days=int(rng.integers(0, 3)))
        rows.append({
            "user_id": uid, "event_date": session_date,
            "event_type": "first_session", "plan": plan,
            "source_channel": channel, "feature_id": None,
        })

        # First key action (activation) — conditional on session
        cond_action = funnel["first_action"] / funnel["first_session"]
        if rng.random() >= cond_action:
            continue
        action_date = session_date + timedelta(days=int(rng.integers(0, 8)))
        rows.append({
            "user_id": uid, "event_date": action_date,
            "event_type": "first_key_action", "plan": plan,
            "source_channel": channel, "feature_id": None,
        })

        # Determine retention window
        retention = RETENTION[plan]
        retained_w4 = rng.random() < retention["w4"]
        retained_w12 = retained_w4 and (rng.random() < retention["w12"] / retention["w4"])

        if retained_w12:
            active_days = int(rng.integers(80, 200))
        elif retained_w4:
            active_days = int(rng.integers(28, 60))
        else:
            active_days = int(rng.integers(7, 28))

        active_until = min(action_date + timedelta(days=active_days), END_DATE)
        active_window = (active_until - action_date).days
        if active_window <= 0:
            continue

        # Feature usage events with Poisson volume, decaying weight by recency
        n_events = int(rng.poisson(min(active_window * 0.5, 80)))
        feature_probs = np.array(FEATURE_ADOPTION[plan]) / sum(FEATURE_ADOPTION[plan])

        for _ in range(n_events):
            # Bias offset toward earlier days (decay) using triangular distribution
            offset = int(rng.triangular(0, active_window * 0.3, active_window))
            event_date = action_date + timedelta(days=offset)
            feature_idx = int(rng.choice(len(FEATURES), p=feature_probs))
            rows.append({
                "user_id": uid, "event_date": event_date,
                "event_type": "feature_used", "plan": plan,
                "source_channel": channel, "feature_id": FEATURES[feature_idx],
            })

    df = pd.DataFrame(rows)
    df["event_date"] = pd.to_datetime(df["event_date"])
    df = df.sort_values(["user_id", "event_date"]).reset_index(drop=True)

    out_path = Path(__file__).parent / "events.csv"
    df.to_csv(out_path, index=False)

    print(f"Wrote {out_path}")
    print(f"  {len(df):,} events")
    print(f"  {df['user_id'].nunique():,} users")
    print(f"  Date range: {df['event_date'].min().date()} to {df['event_date'].max().date()}")
    print(f"  By plan: {df.drop_duplicates('user_id')['plan'].value_counts().to_dict()}")
    print(f"  Activated: "
          f"{df[df['event_type'] == 'first_key_action']['user_id'].nunique():,}")


if __name__ == "__main__":
    main()
