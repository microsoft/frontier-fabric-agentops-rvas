# Coach Guide — Challenge 6: Make It Operational

> Attendee challenge: [`challenges/challenge-06-operationalize.md`](../challenges/challenge-06-operationalize.md)

## Snapshot

| | |
|---|---|
| **Est. time** | 1.5–2 h |
| **Difficulty** | ⭐⭐⭐⭐ (400) — stretch / finale |
| **They build** | Operational alerts, chargeback/showback, RLS, and scheduled refresh |
| **Key services** | Data Activator, Power BI RLS, Fabric pipelines/scheduling, FinOps |

## Coaching objectives

This is where reliability, cost, and performance become **actionable**. The team already has a Control
Tower; now they prove the customer can operate it on Monday morning.

Treat this as a menu. Teams only need two success criteria, but push them toward the options that best
fit their skills and showcase story.

**What good looks like:** the team demonstrates two live operational controls — an alert fires, a
chargeback matrix attributes cost, RLS filters two roles differently, or the daily pipeline is scheduled
with failure notification.

## The reference path

### A. Real-time alerts with Activator

Goal: create a reflex on a Gold/semantic condition and notify an operator.

1. Pick a KPI already modeled in Gold or the semantic model: `ErrorRate`, `P95Latency`, retry rate, or
   daily cost variance.
2. Confirm the data is available through a source Activator supports, such as Power BI, Eventstream, or
   KQL.
3. Define the condition and threshold:
   - error rate > 2%
   - P95 latency > 15,000 ms
   - retry rate > 3%
   - daily cost variance > 20%
4. Configure notification to Teams or email.
5. Simulate a breach by lowering the threshold or filtering to a noisy agent; preserve the production
   threshold in the narrative.

Coach prompt: "If this alert fired at 06:15, who would receive it and what would they do next?"

### B. FinOps chargeback/showback

Goal: attribute blended agent cost to accountable owners.

Reference modeling approach:

1. Start with `gold_cost_summary` for billed/resource costs.
2. Join to `dim_resource` or resource metadata for tags: `team`, `costCenter`, `useCase`, `client`, and
   `environment`.
3. Join agent metrics or `gold_agent_analytics` by agent namespace where model-token cost is agent-level.
4. Parse namespace levels from `<org>.<domain>.<agent>.<version>` and use them as rollup columns.
5. Build measures for total cost, run rate, and MoM change.
6. Put missing tags/namespaces into an explicit `Unattributed` bucket.

Watch for double-counting. If a model-token estimate is already included in a blended cost measure, do
not add the same value again.

### C. Power BI Row-Level Security

Goal: demonstrate governed views by owner/team.

Reference path:

1. Create or identify an ownership dimension with role/team to subscription, resource group, or agent
   namespace mappings.
2. In the semantic model, define two roles such as `TeamA` and `TeamB`.
3. Add a DAX filter on the ownership/resource/agent dimension. Examples:
   - `dim_resource[Team] = "FinanceOps"`
   - `LEFT(dim_agent[AgentNamespace], 16) = "contoso.finance"`
4. Test with **View as** for both roles.
5. Assign users or groups if the tenant/workspace permits; for RVAS validation, View as is enough.

Coach prompt: "Show me the exact same report page as Role A and Role B, and tell me why the totals
changed."

### D. Daily pipeline automation

Goal: schedule the Control Tower operating rhythm.

Reference path:

1. Open the **Daily Refresh Pipeline** from the Fabric workspace.
2. Schedule it daily at about **06:00 UTC**.
3. Confirm it processes the current month incrementally.
4. Verify the dependency order: Bronze → Silver → Gold → semantic-model refresh.
5. Configure failure notification through Fabric alerts, email, or Teams webhook.
6. Bonus: add a capacity-utilization forecast from `gold_capacity_usage` or a threshold visual.

The reference `resources/fabric-control-tower/README.md` describes the Daily Refresh schedule, retry
policy, and failure notifications.

## Checkpoint verification

Ask the team to demo at least two:

1. **Alert:** trigger the simulated breach and show the Teams/email notification or alert history.
2. **Chargeback:** open a matrix by team/use case with total cost, run rate, and MoM trend; point to the
   unattributed bucket if tags are missing.
3. **RLS:** use **View as** for two roles and verify totals/details differ appropriately.
4. **Automation:** open the Daily Refresh schedule and failure-notification configuration; show the last
   run or a test run if available.

✅ Pass when two operational features are working live and the team can explain how each supports the
three business questions.

## Common pitfalls & fixes

| Pitfall | Fix |
|---|---|
| Activator cannot see the intended data | Use a supported source such as Power BI, Eventstream, or KQL; if needed, alert on an existing semantic measure instead of a raw table |
| Alert never fires during the demo | Lower the threshold temporarily or filter to a known noisy agent; state the real production threshold |
| RLS roles defined but not assigned or tested | Use **View as** at minimum; if time allows, assign Entra users/groups to roles |
| RLS filter is on a disconnected table | Ensure the filtered dimension has relationships to the fact tables driving visuals |
| Chargeback double-counts model cost | Decide whether token estimates are additive or already blended into cost; document the measure logic |
| Tags missing on resources | Route unknown owners into `Unattributed`; make tag coverage a governance KPI |
| Pipeline schedule uses local time by mistake | Confirm UTC vs local timezone; the reference rhythm is ~06:00 UTC |
| Trial capacity feature limits or tenant settings block a path | Validate what the tenant allows; accept a documented demo using supported features in that environment |

## Talking points (mini-briefing)

- **Close the loop:** detect → alert → act. Dashboards explain; operations require a trigger and an
  owner.
- **Showback drives behavior.** When teams see their run rate and MoM change, they optimize prompts,
  model choice, cache hit rate, and resource sizing.
- **Governance is part of observability.** RLS turns one enterprise Control Tower into safe views for
  many teams.
- **Production-ready means scheduled, owned, and monitored.** A report that only updates manually is a
  demo; a scheduled pipeline with failure alerting is an operating system.
- **Unattributed cost is a signal.** Missing tags are not a reason to hide cost — they are a backlog for
  platform governance.

## If they go further

- Add anomaly detection over error rate, token volume, or daily cost variance.
- Wire the alert to a Teams workflow or ticketing action with owner routing.
- Add write-back for incident notes, suppression windows, or chargeback approvals.
- Split multiple business units into separate workspaces with shared semantic-model patterns.
- Add a capacity-utilization forecast and alert before the Fabric capacity saturates.
- Build a governance scorecard: tag coverage, RLS coverage, pipeline freshness, and alert ownership.

## Reference assets

- [`challenges/challenge-06-operationalize.md`](../challenges/challenge-06-operationalize.md) — attendee-facing finale menu
- [`resources/fabric-control-tower/README.md`](../resources/fabric-control-tower/README.md) — Daily Refresh pipeline, report design, RLS notes
- [`resources/observability-sdk/README.md`](../resources/observability-sdk/README.md) — KPI targets and alert configuration
- [`docs/architecture.md`](../docs/architecture.md) — Serve & Act stage, Gold products, agent namespace, Core KPIs
- [`docs/faq.md`](../docs/faq.md) — chargeback/showback and security context
