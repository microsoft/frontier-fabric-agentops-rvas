# Coach Guide — Challenge 5: Stand Up the Control Tower

> Attendee challenge: [`challenges/challenge-05-control-tower-dashboards.md`](../challenges/challenge-05-control-tower-dashboards.md)

## Snapshot

| | |
|---|---|
| **Est. time** | 2–2.5 h |
| **Difficulty** | ⭐⭐⭐ (300) |
| **They build** | Direct Lake semantic model plus Power BI pages for reliability, cost, and performance |
| **Key services** | Direct Lake semantic model, Power BI, DAX |

## Coaching objectives

This is the customer-facing payoff. Keep teams focused on the business questions, not dashboard
ornamentation:

1. **Reliability** — Which agents are healthy? Where are errors and latency spikes coming from?
2. **Cost** — What is each agent, service, team, or use case costing?
3. **Performance** — Are we meeting SLAs, and how much traffic/tokens/capacity are we consuming?

Your job is to connect every visual back to one of those questions, then verify the semantic model is
trustworthy: correct relationships, correct DAX, and Direct Lake over the Challenge 4 Gold tables.

**What good looks like:** the team answers all three questions live from one report, slices by
agent/service/resource/date, and can explain which Gold table powers each answer.

## The reference path

1. **Start with populated Gold tables**
   - Confirm Challenge 4 produced the Gold data products listed in [`docs/architecture.md`](../docs/architecture.md):
     `gold_cost_summary`, `gold_operational_metrics`, `gold_agent_analytics`,
     `gold_capacity_usage`, `gold_resource_inventory`, `dim_date`, and `dim_resource`.
   - If using the provided JSON, note its display names: `CostSummary`, `OperationalMetrics`,
     `AgentAnalytics`, `CapacityUsage`, `ResourceInventory`, and `Calendar`.

2. **Create the Direct Lake semantic model**
   - Create a model from the Lakehouse Gold tables, or import/adapt:
     [`resources/fabric-control-tower/src/setup/semantic_model.json`](../resources/fabric-control-tower/src/setup/semantic_model.json).
   - Bind fact tables to the Gold Delta entities.
   - Build relationships from facts to the date and resource dimensions.
   - Mark/filter date fields consistently so YTD/MTD and rolling periods work.

3. **Author the key measures**
   Use the README measures as the baseline. At minimum, verify `TotalCost`, `ErrorRate`,
   `P95Latency`, and cost-per-agent/cost-per-request.

   ```DAX
   TotalCost = SUM(fact_costs[BilledCost])

   ErrorRate =
   DIVIDE(
       COUNTROWS(FILTER(fact_operations, [Severity] = "Error")),
       COUNTROWS(fact_operations)
   )

   P95Latency = PERCENTILE.INC(fact_operations[DurationMs], 0.95)

   CostMoM% =
   VAR CurrentMonth = [TotalCost]
   VAR PreviousMonth = CALCULATE([TotalCost], DATEADD(dim_date[Date], -1, MONTH))
   RETURN DIVIDE(CurrentMonth - PreviousMonth, PreviousMonth, 0)

   CostPerAgent =
   DIVIDE([TotalCost], DISTINCTCOUNT(fact_agent_analytics[AgentId]))
   ```

   Also check the README list: `CapacityUtilization`, `AvgSatisfaction`, and `ConversationCount`.
   If the team imported the provided JSON, adapt the column names to the model's table names rather
   than creating duplicate disconnected measures.

4. **Build the three report pages**
   - **Reliability:** error rate trend by agent/error type, P95/P99 latency, availability, pipeline health.
   - **Cost:** cost by service/agent, MoM trend and forecast, run rate by team/use case, top cost drivers.
   - **Performance:** throughput, prompt/completion token consumption, satisfaction trend, capacity utilization.

5. **Verify Direct Lake**
   - Gold-backed tables show storage mode = **Direct Lake**.
   - There is no imported data copy and no scheduled refresh dependency.
   - The report reads Delta directly after pipeline runs. If Gold schema changed, resync model metadata.

## Checkpoint verification

Have the team present the report as if leadership is in the room:

1. **Reliability:** "Which agent or service is least healthy right now, and why?"
2. **Cost:** "What is the biggest cost driver, and what is the cost per agent/request?"
3. **Performance:** "Are we meeting SLA expectations, and what is traffic/token usage doing?"

Then test the model:

- Select one agent/service/resource and confirm cross-filtering updates all relevant visuals.
- Open the model view and show fact-to-date/resource relationships.
- Show storage mode = Direct Lake for Gold-backed tables.
- Inspect at least `TotalCost`, `ErrorRate`, `P95Latency`, and cost-per-agent/request DAX.

✅ Pass when the team answers the three questions live and the model is confirmed Direct Lake.

## Common pitfalls & fixes

| Pitfall | Fix |
|---|---|
| Semantic model not bound to Lakehouse **Gold** tables | Rebind to the Gold Delta entities from Challenge 4; do not build visuals directly on Bronze/Silver or scratch tables |
| Relationships missing → totals look right but slicers lie | Recreate fact-to-date and fact-to-resource relationships; test with a single date/resource selection |
| Direct Lake falls back to DirectQuery because of unsupported DAX/model behavior | Simplify the measure/model pattern; keep transformations in Gold, not in the semantic model |
| Measures reference wrong columns after importing/adapting the JSON | Compare table names in `semantic_model.json` with the team's Lakehouse schema and update DAX once, centrally |
| Power BI license/capacity needed to publish or share | Use the Fabric workspace assigned to capacity from Challenge 0; publish within that workspace |
| Gold data changed but the model appears stale | Direct Lake auto-reflects data rows, but schema changes may require model metadata re-sync |

## Talking points (mini-briefing)

- **Direct Lake = import-style performance with no copy and no refresh window.** The Delta table is the
  source of truth; Power BI is not another data silo.
- **One model, three audiences.** SREs get reliability, FinOps gets cost, product/AI teams get
  performance — all filtered from the same semantic layer.
- **This is the deliverable leadership asked for.** Everything before this challenge was plumbing;
  this is where the Control Tower becomes visible and defensible.
- **Correct measures beat pretty visuals.** A beautiful report with broken relationships is worse than
  a plain report that answers the question accurately.

## If they finish early

- Add a KPI scorecard page that rolls up reliability, cost, and performance targets.
- Add drill-through from a summary visual to an agent detail page.
- Add conditional formatting and alt text for executive readability and accessibility.
- Create a mobile layout for incident reviews on the go.
- Add bookmarks for "SRE view", "FinOps view", and "Leadership view".
- Add a tooltip page that explains the KPI definitions in business language.
- Add a lightweight usage note so report consumers know which slicers to use first.

## Reference assets

- [`resources/fabric-control-tower/README.md`](../resources/fabric-control-tower/README.md) — semantic model measures and suggested report pages
- [`resources/fabric-control-tower/src/setup/semantic_model.json`](../resources/fabric-control-tower/src/setup/semantic_model.json) — actual provided semantic model definition
- [`docs/architecture.md`](../docs/architecture.md) — Gold tables, Core KPIs, and Direct Lake role in the architecture
- [`challenges/challenge-04-medallion-pipeline.md`](../challenges/challenge-04-medallion-pipeline.md) — prerequisite Gold pipeline
- [`challenges/challenge-06-operationalize.md`](../challenges/challenge-06-operationalize.md) — next operationalization stretch

Bring this guide to the final showcase rehearsal; Challenge 5 is where the story either lands or
exposes model gaps that must be fixed before operationalization.
