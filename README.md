# SaaS Product Analytics

**[Live demo](https://mason-saas-analytics.streamlit.app/)**: runs in the browser, no install required.

End-to-end **product-analytics dashboard** showing the metric views a
Product Manager looks at every week (activation funnel, cohort
retention, feature adoption, behavioural segmentation), computed live
from a synthetic SaaS event log of 3,000 users and ~53,000 events
spanning 14 months.

## What it shows

| View | Question it answers |
|---|---|
| **Overview** | How is Weekly Active Users trending? |
| **Activation funnel** | Where do new users drop off between signup and the "aha" moment? |
| **Cohort retention** | Are signup cohorts retaining? Which months retained best? |
| **Feature adoption** | Which features land with which plan tiers in the first 30 days? |
| **User segments** | How does the user base split into Champions / Loyal / At Risk / Churned? |

## What's actually demonstrated

| Concept | Where |
|---|---|
| **Funnel analysis** with step-conversion rates | Activation Funnel tab |
| **Cohort retention heatmap** by signup month | Cohort Retention tab |
| **Feature-adoption matrix** (% within 30 days, by plan) | Feature Adoption tab |
| **Behavioural segmentation** (recency / frequency thresholds) | User Segments tab |
| **Realistic plan-tier differences** baked into the data generator | All tabs |
| **Win-back target list** (At-Risk users, sortable) | User Segments tab |

## The data

`events.csv` (committed; regenerable via `generate_data.py`) has one row
per event:

| Column | Description |
|---|---|
| `user_id` | Stable user identifier (1 to 3,000) |
| `event_date` | Event timestamp |
| `event_type` | `signup`, `email_verified`, `first_session`, `first_key_action`, or `feature_used` |
| `plan` | Free / Pro / Enterprise (skewed 65 / 30 / 5) |
| `source_channel` | Marketing channel (Organic, Paid Search, Paid Social, Referral, Direct, Content, Affiliate, Partner) |
| `feature_id` | F1 to F5 (set only for `feature_used` events) |

The generator embeds plan-tier funnel rates (Free: 28 % activate;
Enterprise: 78 %), feature-adoption probabilities (F5_API: 5 % on Free
vs. 85 % on Enterprise), and retention curves so the visualisations show
realistic, interpretable patterns.

## Run it

```bash
pip install -r requirements.txt
streamlit run product_analytics_app.py
```

Regenerate the seed data with a different seed or scale by editing the
constants at the top of `generate_data.py` (`SEED`, `N_USERS`,
`START_DATE`, plan / funnel / adoption rate tables) and running:

```bash
python generate_data.py
```

## Repository layout

```
.
├── generate_data.py             ← synthetic event generator
├── events.csv                   ← committed seed (~53,000 rows)
├── analytics.py                 ← pure analytical functions (importable, testable)
├── product_analytics_app.py     ← Streamlit dashboard (5 tabs)
├── requirements.txt
├── LICENSE
└── README.md
```

## Stack

**Python** (`pandas`, `numpy`) for the data layer · **Plotly** for
interactive charts · **Streamlit** for the dashboard
