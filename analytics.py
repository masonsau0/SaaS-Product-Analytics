"""Pure analytical functions for the SaaS event log.

Each function takes a DataFrame of events (as produced by
`generate_data.py`) and returns a DataFrame ready for plotting or
display. No Streamlit / Plotly imports here so the same functions can
be reused in notebooks or unit tests.
"""

from __future__ import annotations

import pandas as pd

ACTIVATION_STAGES = ["signup", "email_verified", "first_session", "first_key_action"]
ACTIVE_EVENT_TYPES = ["first_session", "first_key_action", "feature_used"]


def compute_activation_funnel(
    events: pd.DataFrame, plan_filter: str | None = None
) -> pd.DataFrame:
    """Distinct users at each activation stage. Optionally filtered by plan.

    Returns a DataFrame with columns: stage, users, step_conversion (vs.
    previous stage), from_signup (vs. signup count).
    """
    if plan_filter and plan_filter != "All":
        events = events[events["plan"] == plan_filter]

    rows: list[dict] = []
    prev_count: int | None = None
    for stage in ACTIVATION_STAGES:
        n = events[events["event_type"] == stage]["user_id"].nunique()
        rows.append({
            "stage": stage,
            "users": n,
            "step_conversion": (n / prev_count) if prev_count else 1.0,
        })
        prev_count = n

    df = pd.DataFrame(rows)
    base = df.iloc[0]["users"] or 1
    df["from_signup"] = df["users"] / base
    return df


def compute_wau(events: pd.DataFrame) -> pd.DataFrame:
    """Weekly Active Users: distinct users with any active event in the week."""
    active = events[events["event_type"].isin(ACTIVE_EVENT_TYPES)].copy()
    if active.empty:
        return pd.DataFrame(columns=["week", "wau"])
    active["week"] = active["event_date"].dt.to_period("W").dt.start_time
    wau = active.groupby("week")["user_id"].nunique().reset_index(name="wau")
    return wau


def compute_cohort_retention(
    events: pd.DataFrame, max_weeks: int = 8
) -> pd.DataFrame:
    """Cohort retention as a wide DataFrame.

    Index: cohort_month (first day of signup month).
    Columns: w0, w1, ... w<max_weeks>. Values: % of cohort active that week.
    """
    signups = events[events["event_type"] == "signup"][
        ["user_id", "event_date", "plan"]
    ].copy()
    signups["cohort_month"] = signups["event_date"].dt.to_period("M").dt.start_time

    cohort_sizes = (
        signups.groupby("cohort_month")["user_id"].nunique().rename("cohort_size")
    )

    activity = events[events["event_type"].isin(ACTIVE_EVENT_TYPES)].copy()
    activity = activity.merge(
        signups[["user_id", "cohort_month"]], on="user_id", how="inner"
    )
    activity["weeks_since_signup"] = (
        (activity["event_date"] - activity["cohort_month"]).dt.days // 7
    ).clip(lower=0)

    counts = (
        activity.groupby(["cohort_month", "weeks_since_signup"])["user_id"]
        .nunique()
        .reset_index(name="active_users")
    )
    pivot = counts.pivot(
        index="cohort_month", columns="weeks_since_signup", values="active_users"
    ).fillna(0)

    pivot = pivot.iloc[:, : max_weeks + 1]
    pivot.columns = [f"w{int(c)}" for c in pivot.columns]
    pivot = pivot.div(cohort_sizes, axis=0).fillna(0) * 100
    return pivot


def compute_feature_adoption(
    events: pd.DataFrame, n_days: int = 30
) -> pd.DataFrame:
    """% of users who used each feature within `n_days` of signup, by plan.

    Returns long-format with columns: plan, feature_id, adopters, plan_size,
    adoption_rate.
    """
    signups = events[events["event_type"] == "signup"][
        ["user_id", "event_date", "plan"]
    ].rename(columns={"event_date": "signup_date"})

    feature_events = events[events["event_type"] == "feature_used"][
        ["user_id", "event_date", "feature_id"]
    ]
    if feature_events.empty:
        return pd.DataFrame(columns=["plan", "feature_id", "adopters", "plan_size", "adoption_rate"])

    merged = feature_events.merge(
        signups[["user_id", "signup_date", "plan"]], on="user_id", how="inner"
    )
    merged["days_since_signup"] = (merged["event_date"] - merged["signup_date"]).dt.days
    early = merged[(merged["days_since_signup"] >= 0) & (merged["days_since_signup"] <= n_days)]

    first_use = (
        early.groupby(["user_id", "feature_id", "plan"], as_index=False)["event_date"]
        .min()
    )

    plan_sizes = signups.groupby("plan")["user_id"].nunique().rename("plan_size")
    counts = (
        first_use.groupby(["plan", "feature_id"])["user_id"]
        .nunique()
        .reset_index(name="adopters")
    )
    counts = counts.merge(plan_sizes.reset_index(), on="plan")
    counts["adoption_rate"] = counts["adopters"] / counts["plan_size"]
    return counts.sort_values(["plan", "feature_id"]).reset_index(drop=True)


def segment_users(
    events: pd.DataFrame, today: pd.Timestamp | None = None
) -> pd.DataFrame:
    """Bucket each signed-up user into a behavioural segment.

    - **New**: signed up <7 days ago
    - **Champion**: 20+ active events in last 30 days
    - **Loyal**: active in last 14 days, fewer than 20 events
    - **At_Risk**: last active 14-30 days ago
    - **Churned**: last active 30+ days ago
    - **Never_Activated**: signed up but no active events ever
    """
    if today is None:
        today = events["event_date"].max()

    signups = events[events["event_type"] == "signup"][
        ["user_id", "event_date", "plan"]
    ].rename(columns={"event_date": "signup_date"})

    activity = events[events["event_type"].isin(ACTIVE_EVENT_TYPES)]
    last_active = activity.groupby("user_id")["event_date"].max().rename("last_active")

    recent_window = today - pd.Timedelta(days=30)
    recent = activity[activity["event_date"] >= recent_window]
    recent_count = recent.groupby("user_id")["event_date"].count().rename("recent_event_count")

    df = signups.merge(last_active, on="user_id", how="left").merge(
        recent_count, on="user_id", how="left"
    )
    df["recent_event_count"] = df["recent_event_count"].fillna(0).astype(int)
    df["days_since_signup"] = (today - df["signup_date"]).dt.days
    df["days_since_active"] = (today - df["last_active"]).dt.days

    def _segment(row: pd.Series) -> str:
        if pd.isna(row["last_active"]):
            return "Never_Activated"
        if row["days_since_signup"] < 7:
            return "New"
        if row["days_since_active"] > 30:
            return "Churned"
        if row["days_since_active"] > 14:
            return "At_Risk"
        if row["recent_event_count"] >= 20:
            return "Champion"
        return "Loyal"

    df["segment"] = df.apply(_segment, axis=1)
    return df
