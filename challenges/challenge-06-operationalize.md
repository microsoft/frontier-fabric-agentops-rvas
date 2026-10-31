# Challenge 6 — Make It Operational

> **Est. time:** 1.5–2 h · **Level:** 400 (stretch / finale) · **Roles:** Fabric engineer, FinOps practitioner, platform engineer

---

This **stretch challenge** adds operational features to the Control Tower. Choose at least
two to build and demonstrate: alerts, chargeback/showback, access control, or pipeline automation.

## Objectives

Choose at least two of these objectives:

- Trigger an operational alert from a Gold-layer or semantic-model condition.
- Attribute blended AI-agent cost to teams, use cases, or clients.
- Protect dashboards with Power BI **Row-Level Security (RLS)**.
- Schedule the daily Fabric pipeline and wire failure notification.
- Explain how your chosen features support operational decisions.

## Prerequisites

- ✅ Challenge 5 complete — working semantic model and Control Tower dashboards.
- Gold tables available for reliability, cost, performance, and agent analytics.
- Access to edit the Power BI semantic model / report in your Fabric workspace.
- Permissions to configure Fabric pipeline schedules and notifications.
- Optional: Teams or email destination for alert notifications.

## The finale menu

Complete at least **two** paths. Completing all four is optional.

```text
Gold data products + Direct Lake semantic model
              │
              ├─ A. Real-time alerts     → notify when a KPI breaches
              ├─ B. FinOps chargeback    → show who owns the run rate
              ├─ C. Access control       → secure each team's slice
              └─ D. Automation           → run the tower every morning
```

### A. Real-time alerts

Use **Fabric Data Activator (Activator)** to trigger on a meaningful condition from a supported source
such as a Power BI visual/measure, Eventstream, or KQL-backed item.

Choose a KPI tied to the Control Tower targets:

| Signal | Example threshold |
|---|---|
| Error rate | Breaches the SDK alert target (for example > 2%) |
| P95 latency | Exceeds the latency SLA (15,000 ms in the SDK config) |
| Retry rate | Rises above 3% |
| Daily cost variance | Exceeds 20% day-over-day or against baseline |

Demonstrate one useful alert that fires and notifies an operator through Teams or email.

#### What to build

- Pick one Gold table or semantic-model measure that represents a business KPI.
- Define a threshold and a notification target.
- Simulate a breach by changing the filter context, test data, or threshold.
- Capture proof that the alert fired.

### B. FinOps chargeback/showback

The Cost dashboard answered "what are we spending?" Now answer: **who owns it?**

Attribute blended cost across model tokens, Cosmos DB RUs, compute, API Management, and supporting
platform resources using:

- Azure resource tags such as `team`, `costCenter`, `useCase`, `client`, or `environment`.
- The agent namespace pattern from the architecture:

```text
<organization>.<domain>.<agent-name>.<version>
```

Example: `contoso.finance.invoice-processor.v2`.

#### What to build

Create a chargeback or showback view that lets a leader see:

- Cost by **team** and **use case**.
- Agent run rate by day or month.
- Month-over-month change.
- An explicit **Unattributed** bucket for missing tags or unknown namespaces.

Aim for a matrix visual: team/use case down the rows, cost/run rate/MoM across the columns. If you can
show one agent rolling up to a team and use case, the pattern is working.

### C. Access control with RLS

Limit each team's view to the data it owns.

Use standard Power BI **Row-Level Security (RLS)** on the semantic model so report consumers are
filtered to their subscription, resource group, team, or agent namespace.

#### What to build

- Define at least two roles, such as `FinanceOps` and `RetailOps`, or `TeamA` and `TeamB`.
- Add a DAX filter on a dimension or ownership table.
- Test the report with **View as** for both roles.
- Show that the same page returns different slices for different roles.

A simple ownership table is enough for the RVAS. Production can map Entra groups to roles later.

### D. Pipeline automation

The reference Fabric assets include a **Daily Refresh Pipeline** intended to run around **06:00 UTC** and
process the current month incrementally. Configure its schedule and failure notifications.

#### What to build

- Schedule the Daily Refresh pipeline to run daily at about 06:00 UTC.
- Confirm the pipeline runs Bronze → Silver → Gold → semantic-model refresh in order.
- Enable failure notifications through Fabric alerts, email, or Teams webhook.
- Bonus: add a capacity-utilization forecast or threshold view for the next week.

## Success criteria

Complete **at least TWO** of the following:

- [ ] A live alert fires on a simulated threshold breach and sends a Teams/email notification.
- [ ] A chargeback/showback view exists by team or use case, including run rate and MoM trend.
- [ ] Power BI RLS is demonstrated with two roles viewing different data slices.
- [ ] The Daily Refresh pipeline is scheduled and failure alerting is configured.

> 🧭 **Checkpoint:** show your coach two operational features working live. Do not just describe them —
> fire the alert, switch the RLS role, open the schedule, or walk through the chargeback matrix.

## Hints

<details>
<summary>Choosing the best alert candidate</summary>

Pick a metric that already appears on your dashboard and maps to a Gold product: `ErrorRate`,
`P95Latency`, retry rate, or daily cost variance. If the real data is too healthy, temporarily lower the
threshold so the alert can fire during the demo, then explain the production threshold you would use.
</details>

<details>
<summary>What counts as a simulated breach?</summary>

For the RVAS, it is acceptable to simulate by lowering the threshold, filtering to a noisy agent,
or inserting a clearly marked test row into a development Gold table. Do not corrupt production-like
history; keep the test obvious and reversible.
</details>

<details>
<summary>Chargeback modeling idea</summary>

Start from `gold_cost_summary` and enrich it with `dim_resource` tags plus the agent namespace. Roll up
by `team`, `useCase`, and `client`. Keep any resource without a reliable owner in an `Unattributed`
bucket so data-quality gaps are visible instead of hidden.
</details>

<details>
<summary>RLS pattern</summary>

Use an ownership table with columns such as `RoleName`, `Team`, `SubscriptionId`, `ResourceGroup`, or
`AgentNamespacePrefix`. Apply a DAX filter to the dimension that all facts flow through, then test with
Power BI's **View as** feature before showing the coach.
</details>

<details>
<summary>Scheduling gotcha</summary>

Check the schedule timezone carefully. The reference operating rhythm is ~06:00 UTC, which may not be
06:00 local time. Also make sure the capacity is running if you use a paid capacity that can be paused.
</details>

## Resources

- [`docs/architecture.md`](../docs/architecture.md) — Serve & Act stage, Gold products, agent namespace, KPIs
- [`docs/faq.md`](../docs/faq.md) — chargeback/showback and security notes
- [`resources/fabric-control-tower/README.md`](../resources/fabric-control-tower/README.md) — pipelines, schedule, report design, RLS guidance
- [`resources/observability-sdk/README.md`](../resources/observability-sdk/README.md) — KPI targets and alert configuration

---

⬅️ Previous: **[Challenge 5 — Stand Up the Control Tower](challenge-05-control-tower-dashboards.md)**

## Showcase

Use the [Challenge Index](README.md) for showcase guidance and scoring.
Demonstrate your chosen operational features alongside the reliability, cost, and performance dashboards.
