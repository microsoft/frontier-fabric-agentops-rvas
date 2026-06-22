# Coach Guide — Challenge 2: Build the Telemetry Landing Zone

> Attendee challenge: [`challenges/challenge-02-landing-zone.md`](../challenges/challenge-02-landing-zone.md)

## Snapshot

| | |
|---|---|
| **Est. time** | 1.5–2 h |
| **Difficulty** | ⭐⭐ (200) |
| **They build** | ADLS Gen2 landing zone for cost, metrics, logs, metadata, and diagnostics |
| **Key services** | ADLS Gen2, Azure Cost Management, Resource Graph, Log Analytics data export, Diagnostic Settings |

## Coaching objectives

This challenge turns scattered Azure signals into a single **landing zone** that Fabric can read with
OneLake shortcuts. Keep teams focused on the outcome: five domains landing in storage with enough
proof that Challenge 3 can shortcut to them.

**What good looks like:** the team shows the five containers, validates FOCUS and Resource Graph
Parquet, confirms the Log Analytics export rule, applies diagnostic settings to supported resources,
and records the storage account name, resource ID, and DFS endpoint.

## The reference path

Deploy the ingestion asset:

```bash
cd resources/observability-ingestion
azd auth login
azd up        # env name, region (same as Challenge 0), subscription
```

`azd up` provisions ADLS Gen2 storage, five containers, Log Analytics workspace + data export rule,
Cost Management FOCUS export, Key Vault, and a user-assigned managed identity. Capture outputs:

```bash
azd env get-values
```

Install script dependencies:

```bash
cd resources/observability-ingestion/src/scripts
pip install -r requirements.txt
```

Preview diagnostic settings:

```bash
python setup_diagnostic_settings.py \
  --subscription-id <SUBSCRIPTION_ID> \
  --workspace-id <WORKSPACE_RESOURCE_ID> \
  --storage-account-id <STORAGE_ACCOUNT_RESOURCE_ID> \
  --dry-run
```

Apply diagnostic settings:

```bash
python setup_diagnostic_settings.py \
  --subscription-id <SUBSCRIPTION_ID> \
  --workspace-id <WORKSPACE_RESOURCE_ID> \
  --storage-account-id <STORAGE_ACCOUNT_RESOURCE_ID>
```

Run Resource Graph export:

```bash
python resource_graph_export.py \
  --subscription-id <SUBSCRIPTION_ID> \
  --storage-account <STORAGE_ACCOUNT_NAME> \
  --container metadata
```

Trigger the Cost Management export. The current Azure CLI `costmanagement export` group may not expose
a `run` command, so use the ARM action directly:

```bash
EXPORT_NAME=export-<env-name>-focus-daily
SCOPE="/subscriptions/<SUBSCRIPTION_ID>"

az rest --method post \
  --url "https://management.azure.com${SCOPE}/providers/Microsoft.CostManagement/exports/${EXPORT_NAME}/run?api-version=2023-11-01"
```

Check export execution history:

```bash
az costmanagement export show \
  --name "$EXPORT_NAME" \
  --scope "$SCOPE"
```

Validate the landing zone:

```bash
python validate_exports.py \
  --storage-account <STORAGE_ACCOUNT_NAME>
```

## Checkpoint verification

Ask the team to show:

1. **Storage account** with hierarchical namespace enabled and containers:
   `costs`, `metrics`, `logs`, `metadata`, `diagnostics`.
2. **FOCUS cost Parquet** under `costs/focus/...` after trigger/wait.
3. **Resource Graph Parquet** under `metadata/resource-graph/year=*/month=*/day=*/`.
4. **Log Analytics data export** enabled for `AppRequests`, `AppDependencies`, `AppTraces`,
   `AppExceptions`, and `AppMetrics`.
5. **Diagnostic settings** created on supported resources; unsupported types skipped gracefully.
6. `validate_exports.py` output with file counts, sizes, latest timestamps, and sample schemas.
7. Recorded Fabric coordinates:
   - storage account name
   - storage account resource ID
   - `https://<storage-account>.dfs.core.windows.net`

✅ Pass when the storage landing zone is validated and the team can explain how Challenge 3 will
shortcut to it.

## Common pitfalls & fixes

| Pitfall | Fix |
|---|---|
| Missing **Cost Management Reader** | Grant at the billing/subscription scope; Contributor on the resource group is not enough for cost exports |
| `costs` container empty | Cost export is daily; trigger it manually with the ARM `run` action and wait for execution to complete |
| Cost export name unknown | It is `export-<environmentName>-focus-daily` from `infra/main.bicep`; confirm with `az costmanagement export list --scope /subscriptions/<id>` |
| Expecting Log Analytics export to backfill | Data export is continuous from enablement forward; generate Challenge 1 traffic after enabling it |
| Assuming data export requires a dedicated cluster | It does not for this reference path; verify the rule is enabled and treat it as continuous export |
| Diagnostic settings fail on some resources | Normal. The script skips known unsupported types and logs warnings for resources without categories |
| Storage access denied from scripts | Ensure the caller/identity has Storage Blob Data Contributor on the storage account or resource group |
| No metrics/log files yet | Confirm the data export rule is enabled, traffic exists in the workspace, and allow time for export latency |

## Talking points (mini-briefing)

- **FOCUS = FinOps lingua franca.** It standardizes cost fields so spend can be joined to tags,
  resources, services, and agent namespaces.
- **One landing zone beats five silos.** Cost, logs, metrics, metadata, and diagnostics become
  queryable together instead of trapped in separate portals.
- **Date partitions are Spark fuel.** The storage layout is already shaped for Fabric notebooks and
  medallion processing.
- **Continuous vs batch matters.** Log Analytics and diagnostics stream continuously; cost and
  Resource Graph are scheduled/triggered snapshots.
- **This is Challenge 3's shortcut target.** The storage DFS endpoint is the bridge into OneLake with
  no data copy.

## If they finish early

- Add tags (`team`, `agent`, `environment`, `costCenter`) to Challenge 1 resources, rerun Resource
  Graph export, and prove tags appear in Parquet.
- Generate more agent traffic and watch the `metrics` / `logs` containers grow.
- Compare `ResourceId` in FOCUS with `id` in Resource Graph and sketch the future `dim_resource` join.
- Review [`docs/architecture.md`](../docs/architecture.md) Gold tables and map which raw container
  feeds each one.

## Reference assets

- [`resources/observability-ingestion/README.md`](../resources/observability-ingestion/README.md) — deployment, data layout, script usage
- [`resources/observability-ingestion/infra/main.bicep`](../resources/observability-ingestion/infra/main.bicep) — outputs and resource naming
- [`resources/observability-ingestion/infra/modules/storage.bicep`](../resources/observability-ingestion/infra/modules/storage.bicep) — five containers and ADLS Gen2 settings
- [`resources/observability-ingestion/infra/modules/monitoring.bicep`](../resources/observability-ingestion/infra/modules/monitoring.bicep) — Log Analytics data export tables
- [`resources/observability-ingestion/infra/modules/cost-export.bicep`](../resources/observability-ingestion/infra/modules/cost-export.bicep) — FOCUS Parquet export
- [`resources/observability-ingestion/src/scripts/`](../resources/observability-ingestion/src/scripts/) — Resource Graph, diagnostic settings, validation
- [`docs/architecture.md`](../docs/architecture.md) — Ingest stage and Gold data products
