"""Streamlit dashboard for SaaS product analytics.

Five tabs covering the metric views a Product Manager looks at every
week: Overview (WAU + headlines), Activation Funnel, Cohort Retention,
Feature Adoption, and User Segments. Reads from `events.csv` produced
by `generate_data.py`.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from analytics import (
    compute_activation_funnel,
    compute_cohort_retention,
    compute_feature_adoption,
    compute_wau,
    segment_users,
)

EVENTS_PATH = Path(__file__).parent / "events.csv"

st.set_page_config(page_title="SaaS Product Analytics", layout="wide", page_icon="📊")


@st.cache_data(show_spinner="Loading event data...")
def load_events() -> pd.DataFrame:
    return pd.read_csv(EVENTS_PATH, parse_dates=["event_date"])


events = load_events()

st.title("SaaS Product Analytics")
st.caption(
    "End-to-end product-analytics dashboard: activation funnel, cohort "
    "retention, feature adoption, and behavioural user segmentation, "
    "computed live from a synthetic SaaS event log of 3,000 users and "
    f"{len(events):,} events spanning 14 months."
)

with st.expander("How to use this app", expanded=False):
    st.markdown("""
**What this app does in plain English.**
A SaaS company (think Slack, Notion, Figma) needs to know: are new
users actually getting value, are they sticking around, and are the
features the team is shipping actually being used? This dashboard
shows the four metric views a Product Manager looks at every week to
answer those questions.

**Quick start (30 seconds).**
1. Open the **Overview** tab to see total users, activation rate, and
   the Weekly Active Users trend.
2. Click **Activation Funnel** to see where users drop off between
   signing up and reaching the "aha" moment.
3. Click **Cohort Retention** for the classic heatmap of how each
   signup-month cohort retains over time.
4. Click **Feature Adoption** to see which features land with which
   plan tiers.
5. Click **User Segments** for the behavioural buckets (Champion /
   Loyal / At Risk / Churned).

**The 5 tabs at a glance.**
- **Overview** -- Weekly Active Users trend plus headline metrics
  (total signups, activation rate, current WAU).
- **Activation Funnel** -- signup, email verified, first session,
  first key action. Filter by plan to see how Pro / Enterprise activate
  better than Free (by design in the synthetic data).
- **Cohort Retention** -- heatmap of % of each signup-month cohort
  active in subsequent weeks. The colour intensity at week 4 / week 8
  is the key health signal.
- **Feature Adoption** -- % of users (by plan) who used each of the 5
  product features within their first 30 days. Helps a PM decide
  which features need better onboarding versus which are simply
  Enterprise-only.
- **User Segments** -- behavioural buckets and a sortable list of the
  At-Risk users (the win-back target).

**Try this.** Open **Cohort Retention** and notice that the right-hand
columns thin out: recent cohorts haven't had time to age yet. Then jump
to **Feature Adoption** -- F5_API runs at ~5 % on Free vs ~85 % on
Enterprise, the kind of pattern that tells a PM whether F5 is an
under-marketed Free-tier feature or simply gated for Enterprise.
""")

# --- Sidebar filters --------------------------------------------------------
st.sidebar.markdown("### Filters")
plan_options = ["All"] + sorted(events["plan"].unique().tolist())
plan_filter = st.sidebar.selectbox("Plan", plan_options, index=0)

date_min = events["event_date"].min().date()
date_max = events["event_date"].max().date()
date_range = st.sidebar.date_input(
    "Date range",
    value=(date_min, date_max),
    min_value=date_min,
    max_value=date_max,
)

if isinstance(date_range, tuple) and len(date_range) == 2:
    d_start, d_end = date_range
    filtered = events[
        (events["event_date"].dt.date >= d_start)
        & (events["event_date"].dt.date <= d_end)
    ]
else:
    filtered = events

if plan_filter != "All":
    filtered_plan = filtered[filtered["plan"] == plan_filter]
else:
    filtered_plan = filtered

# --- Tabs -------------------------------------------------------------------
tab_overview, tab_funnel, tab_cohort, tab_features, tab_segments = st.tabs(
    ["Overview", "Activation Funnel", "Cohort Retention",
     "Feature Adoption", "User Segments"]
)

with tab_overview:
    st.subheader("Headline metrics")

    n_signups = filtered_plan[filtered_plan["event_type"] == "signup"]["user_id"].nunique()
    n_activated = filtered_plan[filtered_plan["event_type"] == "first_key_action"]["user_id"].nunique()
    activation_rate = (n_activated / n_signups) if n_signups else 0.0

    last_week_start = filtered_plan["event_date"].max() - pd.Timedelta(days=7)
    wau_now = filtered_plan[
        (filtered_plan["event_date"] >= last_week_start)
        & (filtered_plan["event_type"].isin(
            ["first_session", "first_key_action", "feature_used"]))
    ]["user_id"].nunique()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total signups", f"{n_signups:,}")
    c2.metric("Activated users", f"{n_activated:,}")
    c3.metric("Activation rate", f"{activation_rate:.1%}")
    c4.metric("WAU (last 7d)", f"{wau_now:,}")

    st.subheader("Weekly Active Users")
    wau_df = compute_wau(filtered_plan)
    if wau_df.empty:
        st.info("No active events in the selected window.")
    else:
        fig = px.line(
            wau_df, x="week", y="wau", markers=True,
            labels={"wau": "Weekly Active Users", "week": "Week"},
        )
        fig.update_layout(height=400, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, width="stretch")


with tab_funnel:
    st.subheader(f"Activation funnel ({plan_filter})")
    funnel_df = compute_activation_funnel(filtered, plan_filter)

    fig = go.Figure(go.Funnel(
        y=funnel_df["stage"],
        x=funnel_df["users"],
        textposition="inside",
        textinfo="value+percent initial",
    ))
    fig.update_layout(height=420, margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig, width="stretch")

    display_df = funnel_df.assign(
        **{
            "Step conv. (%)": (funnel_df["step_conversion"] * 100).round(1),
            "% of signups": (funnel_df["from_signup"] * 100).round(1),
        }
    )[["stage", "users", "Step conv. (%)", "% of signups"]].rename(
        columns={"stage": "Stage", "users": "Users"}
    )
    st.caption("Step conversion = users at this stage / users at the previous stage.")
    st.dataframe(display_df, width="stretch", hide_index=True)


with tab_cohort:
    st.subheader("Cohort retention by signup month")
    st.caption(
        "% of each signup-month cohort active (any session, action, or "
        "feature event) in subsequent weeks. Read across each row to see "
        "that cohort's retention curve."
    )
    cohort_df = compute_cohort_retention(filtered)
    if cohort_df.empty:
        st.info("Not enough data to compute cohort retention.")
    else:
        cohort_df.index = cohort_df.index.strftime("%Y-%m")
        fig = px.imshow(
            cohort_df,
            color_continuous_scale="Blues",
            text_auto=".1f",
            labels=dict(x="Weeks since signup", y="Cohort month", color="Retention %"),
        )
        fig.update_layout(height=520, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, width="stretch")


with tab_features:
    st.subheader("Feature adoption (within 30 days of signup)")
    adoption = compute_feature_adoption(filtered, n_days=30)

    if adoption.empty:
        st.info("No feature-usage events in the selected window.")
    else:
        fig = px.bar(
            adoption, x="feature_id", y="adoption_rate",
            color="plan", barmode="group",
            labels={"feature_id": "Feature", "adoption_rate": "Adoption rate", "plan": "Plan"},
        )
        fig.update_yaxes(tickformat=".0%")
        fig.update_layout(height=420, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, width="stretch")

        pivot = adoption.pivot(
            index="feature_id", columns="plan", values="adoption_rate"
        ).fillna(0) * 100
        st.caption("Adoption rate (%):")
        st.dataframe(pivot.round(1), width="stretch")


with tab_segments:
    st.subheader("User segmentation")
    seg_df = segment_users(filtered_plan)

    seg_counts = seg_df["segment"].value_counts().reset_index()
    seg_counts.columns = ["Segment", "Users"]
    seg_counts["% of total"] = (
        seg_counts["Users"] / seg_counts["Users"].sum() * 100
    ).round(1)

    c1, c2 = st.columns([1, 2])
    with c1:
        fig = px.pie(seg_counts, names="Segment", values="Users", hole=0.5)
        fig.update_layout(height=380, margin=dict(l=0, r=0, t=10, b=0), showlegend=True)
        st.plotly_chart(fig, width="stretch")
    with c2:
        st.caption("Segment sizes:")
        st.dataframe(seg_counts, width="stretch", hide_index=True)

    st.subheader("At-risk users (win-back target)")
    st.caption(
        "Users active in the last 30 days but quiet for the last 14, "
        "ranked by days since their last action. The list a PM hands to "
        "lifecycle marketing for re-engagement."
    )
    at_risk = (
        seg_df[seg_df["segment"] == "At_Risk"][[
            "user_id", "plan", "signup_date", "last_active",
            "days_since_active", "recent_event_count",
        ]]
        .sort_values("days_since_active", ascending=False)
        .head(20)
    )
    st.dataframe(at_risk, width="stretch", hide_index=True)
