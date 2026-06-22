# Challenge 5 — Stand Up the Control Tower

> **Est. time:** 2–2.5 h · **Level:** 300 · **Roles:** BI engineer, data engineer, FinOps practitioner

---

> **Mission log.**
> The lake is full, the Gold tables are polished, and leadership is done waiting for screenshots from
> five different portals. This is the payoff: turn the medallion data products into a live **AgentOps
> Control Tower** that answers the three questions in one place — reliability, cost, and performance.

In this challenge your team builds the semantic model and Power BI report that the customer will use
in the showcase. The goal is not a beautiful wallpaper dashboard; it is a single pane of glass that can
answer operational questions **live** from the Gold Delta tables.

## Objectives

By the end of this challenge you will have:

- A **Direct Lake semantic model** over the Challenge 4 Gold tables.
- Relationships from facts to the date and resource dimensions so filters behave correctly.
- Core DAX measures for cost, reliability, performance, and agent adoption.
- Power BI report pages mapped to the three business questions:
  **Reliability**, **Cost**, and **Performance**.
- Proof that the model reads Delta directly — no import dataset, no scheduled data refresh.

## Prerequisites

- ✅ Challenge 4 complete — populated Gold tables in the Fabric Lakehouse.
- The Fabric Control Tower assets in
  [`resources/fabric-control-tower/`](../resources/fabric-control-tower/).
- The semantic model reference at
  [`resources/fabric-control-tower/src/setup/semantic_model.json`](../resources/fabric-control-tower/src/setup/semantic_model.json).
- The architecture north star in [`docs/architecture.md`](../docs/architecture.md), especially the
  Gold data products and Core KPIs.

## The dashboard contract

Your report must answer the same questions the customer asked on day one:

| Business question | What the Control Tower must show |
|---|---|
| **Reliability** | Which agents are healthy? Where are errors, latency spikes, and pipeline issues coming from? |
| **Cost** | What is each service, agent, team, or use case costing? Which drivers are changing fastest? |
| **Performance** | Are we meeting SLAs? How much traffic, token usage, satisfaction, and capacity are we seeing? |

The Gold layer gives you the data products. The semantic model makes them trustworthy. The report makes
them usable under pressure.

## Your mission

### 1. Create the Direct Lake semantic model

Build or import a semantic model over the Gold Delta tables produced in Challenge 4:

- `gold_cost_summary`
- `gold_operational_metrics`
- `gold_agent_analytics`
- `gold_capacity_usage`
- `gold_resource_inventory`
- `dim_date`
- `dim_resource`

Use the provided
[`src/setup/semantic_model.json`](../resources/fabric-control-tower/src/setup/semantic_model.json) as
the reference for table bindings, Direct Lake partitions, relationships, and starter measures. If your
workspace uses the provided display names, you may see tables such as `CostSummary`,
`OperationalMetrics`, `AgentAnalytics`, `CapacityUsage`, `ResourceInventory`, and `Calendar` mapped to
the Gold entities.

Make sure the model has relationships from the fact tables to the date and resource dimensions. This is
what allows one date slicer or one resource filter to control the whole report.

### 2. Define the key measures

Create the core measures called out in the Fabric Control Tower README:

- `TotalCost`
- `CostMoM%`
- `CapacityUtilization`
- `ErrorRate`
- `P95Latency`
- `AvgSatisfaction`
- `ConversationCount`
- A cost-per-request or cost-per-agent measure

Add time intelligence so the report can show **YTD**, **MTD**, prior period, and rolling 30-day views.
The measures do not need to be fancy, but they must be correct and reusable across pages.

### 3. Build the Reliability page

Design this page around the question: **Which agents are healthy, and where are the errors?**

Include visuals that cover:

- Error rate trend by agent, service, or error type.
- P95/P99 latency trends and outliers.
- Availability scorecards.
- Pipeline health or latest Gold refresh status if your team captured it.

A coach should be able to point at one unhealthy agent or service and ask, "What changed?" Your page
should make the answer obvious.

### 4. Build the Cost page

Design this page around the question: **What is each agent or team costing us?**

Include visuals that cover:

- Total cost by service, resource group, agent, or tag.
- Month-over-month trend and forecast.
- Run rate by team or use case where tags support it.
- Top cost drivers table.
- Cost-per-request or cost-per-agent KPI.

Make the page useful for a FinOps conversation: show where spend is, who owns it, and whether it is
getting better or worse.

### 5. Build the Performance page

Design this page around the question: **Are we meeting SLAs, and how much are we scaling?**

Include visuals that cover:

- Throughput by minute or hour.
- Prompt and completion token consumption.
- Satisfaction trend.
- Capacity utilization.
- Conversation volume and response-time trends.

Connect performance to reliability and cost. High traffic is good only if latency, errors, satisfaction,
and spend stay under control.

### 6. Confirm Direct Lake mode

Before you claim victory, prove the model is actually Direct Lake:

- Storage mode is **Direct Lake** for the Gold-backed tables.
- The report is not using an imported copy of the data.
- There is no scheduled data refresh required for the report to see newly written Delta rows.
- After a pipeline run updates Gold, the report reflects the latest data once the model schema is in
  sync.

## Success criteria

- [ ] A working Power BI Control Tower report answers **Reliability**, **Cost**, and **Performance** live
- [ ] The semantic model is confirmed as **Direct Lake** over the Gold Delta tables
- [ ] Relationships to the date and resource dimensions are present and filters work across pages
- [ ] Measures are correct for at least `TotalCost`, `ErrorRate`, `P95Latency`, and cost-per-agent or cost-per-request
- [ ] Cross-filtering works: selecting an agent/service/resource changes the related cost, reliability, and performance visuals
- [ ] Your team can explain which Gold table powers each major page

> 🧭 **Checkpoint:** show your coach the report and answer the three business questions live, using
> slicers and cross-filtering instead of switching back to raw tables.

## Hints

<details>
<summary>Starting from the provided semantic model</summary>

Use the JSON model definition as your map:

[`resources/fabric-control-tower/src/setup/semantic_model.json`](../resources/fabric-control-tower/src/setup/semantic_model.json)

Look for:

- Gold table bindings such as `gold_cost_summary`, `gold_operational_metrics`,
  `gold_agent_analytics`, `gold_capacity_usage`, and `gold_resource_inventory`.
- `mode: "directLake"` partitions on the Gold-backed tables.
- Date relationships into the provided calendar/date table.
- Resource relationships into the resource inventory/dimension table.

If you build manually in Fabric, reproduce the same model shape rather than inventing a new schema.
</details>

<details>
<summary>DAX starter pack</summary>

The reference README lists the key measures. Adapt names only if your semantic model uses different
physical table names.

```DAX
TotalCost = SUM(fact_costs[BilledCost])

CapacityUtilization = AVERAGE(fact_metrics[CPUPercent])

ErrorRate =
DIVIDE(
    COUNTROWS(FILTER(fact_operations, [Severity] = "Error")),
    COUNTROWS(fact_operations)
)

P95Latency = PERCENTILE.INC(fact_operations[DurationMs], 0.95)

AvgSatisfaction = AVERAGE(fact_agent_analytics[SatisfactionScore])

ConversationCount = DISTINCTCOUNT(fact_agent_analytics[ConversationId])
```

If you imported the provided JSON model, compare these with the measures already defined on
`CostSummary`, `OperationalMetrics`, `CapacityUsage`, and `AgentAnalytics`.
</details>

<details>
<summary>Testing cross-filtering</summary>

Pick one agent, service, or resource and select it on a visual. Confirm all three pages respond:

- Cost cards and trend narrow to that selection.
- Error rate and latency visuals change.
- Conversation volume, token usage, and satisfaction update.

If only one visual changes, check relationships, inactive relationships, or mismatched dimension keys.
</details>

<details>
<summary>Direct Lake sanity checks</summary>

In the semantic model settings or model view, confirm the Gold-backed tables use **Direct Lake** storage
mode. Avoid unsupported transformations or DAX patterns that force a fallback path. If the Gold schema
changed after your model was created, resync the model schema — Direct Lake reflects data changes, but
new columns and renamed tables still need model metadata alignment.
</details>

## Resources

- [`resources/fabric-control-tower/README.md`](../resources/fabric-control-tower/README.md) — semantic model, measures, and report page guidance
- [`resources/fabric-control-tower/src/setup/semantic_model.json`](../resources/fabric-control-tower/src/setup/semantic_model.json) — provided semantic model definition
- [`docs/architecture.md`](../docs/architecture.md) — Gold tables, Core KPIs, and the three business questions
- [Direct Lake overview](https://learn.microsoft.com/fabric/get-started/direct-lake-overview)

---

⬅️ Previous: **[Challenge 4 — Refine the Signal](challenge-04-medallion-pipeline.md)**  
➡️ Next: **[Challenge 6 — Make It Operational](challenge-06-operationalize.md)**
