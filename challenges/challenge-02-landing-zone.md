# Challenge 2 — Build the Telemetry Landing Zone

> **Est. time:** 1.5–2 h · **Level:** 200 · **Roles:** Cloud/Platform engineer, FinOps practitioner, Data engineer

---

> **Mission log.**
> The agents are talking. Now the Control Tower needs a place for every signal to land — cost,
> metrics, logs, resource inventory, and platform diagnostics. Scattered telemetry is noise; a
> governed lake landing zone is the first step toward intelligence.

In this challenge your team builds the **Ingest** stage of the platform: a secure ADLS Gen2 landing
zone that Microsoft Fabric will read in Challenge 3 with OneLake shortcuts. You are not building the
dashboards yet. You are preparing the runway so the Control Tower can correlate reliability, cost, and
performance later.

## Objectives

By the end of this challenge you will have:

- Deployed the observability ingestion infrastructure in [`resources/observability-ingestion/`](../resources/observability-ingestion/).
- Created an **ADLS Gen2** storage account with five landing containers:
  `costs`, `metrics`, `logs`, `metadata`, and `diagnostics`.
- Enabled **Log Analytics data export** so application telemetry flows continuously to storage.
- Configured **Cost Management FOCUS** export for FinOps-ready Parquet cost data.
- Exported **Azure Resource Graph** metadata and tags to Parquet.
- Wired **diagnostic settings** so Azure platform logs and metrics land in the lake.
- Recorded the storage account coordinates Fabric will need next.

## Prerequisites

- ✅ Challenge 0 complete — Azure access, region, subscription, and roles confirmed.
- **Cost Management Reader** at the billing/subscription scope for the person configuring cost export.
- The reference ingestion asset in
  [`resources/observability-ingestion/`](../resources/observability-ingestion/).
- Challenge 1 is strongly recommended because it gives you real agent workload resources to diagnose,
  but Challenges 1 and 2 can run **in parallel** if you split the team.

## The landing zone

The provided ingestion layer lands four Azure signal families into one ADLS Gen2 account:

| Source | Container | Format | Cadence |
|---|---|---|---|
| Azure Cost Management | `costs` | FOCUS Parquet (Snappy) | Daily / triggered |
| Log Analytics data export | `metrics` | JSON | Continuous |
| Log Analytics data export | `logs` | JSON | Continuous |
| Azure Resource Graph | `metadata` | Parquet (Snappy) | On demand / scheduled |
| Diagnostic settings | `diagnostics` | JSON | Continuous |

That storage account becomes the **OneLake shortcut target** in Challenge 3. Treat its name, resource
ID, and DFS endpoint as mission-critical coordinates.

```
Azure Monitor + Cost + Resource Graph + Diagnostics
                         │
                         ▼
ADLS Gen2 landing zone: costs · metrics · logs · metadata · diagnostics
                         │
                         ▼
Challenge 3: Fabric Lakehouse + OneLake shortcuts
```

## Your mission

### 1. Deploy the ingestion infrastructure

- Provision the ingestion stack from [`resources/observability-ingestion/`](../resources/observability-ingestion/).
- Confirm the deployment creates:
  - ADLS Gen2 storage with hierarchical namespace enabled
  - Five containers: `costs`, `metrics`, `logs`, `metadata`, `diagnostics`
  - Log Analytics workspace with data export enabled
  - Cost Management FOCUS export
  - Key Vault
  - User-assigned managed identity
- Capture the outputs for the storage account and Log Analytics workspace.

### 2. Wire platform diagnostics into the lake

- Discover which Azure resources in your subscription support diagnostic settings.
- Configure supported resources to send logs and metrics to both:
  - the landing zone storage account, and
  - the Log Analytics workspace.
- Include the resources deployed in Challenge 1 if they exist: Container Apps, API Management,
  Cosmos DB, Application Insights/Log Analytics, and related platform services.
- Use a dry run first so the team can see what will change before applying it.

### 3. Land cost and resource metadata

- Trigger or confirm the **Cost Management FOCUS** export into the `costs` container.
- Run the **Resource Graph** metadata export into the `metadata` container.
- Confirm metadata includes resource IDs, names, types, locations, resource groups, tags, and
  subscription IDs.
- Watch for date-partitioned paths — this layout is what makes Spark reads efficient later.

### 4. Validate the data lake

- Inspect all five containers and confirm files are appearing where expected.
- Validate file counts, total sizes, latest timestamps, and sample Parquet schemas.
- Pay special attention to:
  - `costs/focus/...` — FOCUS Parquet
  - `metadata/resource-graph/...` — Resource Graph Parquet
  - `metrics/...` and `logs/...` — Log Analytics exports
  - `diagnostics/...` — diagnostic settings output

### 5. Record the coordinates for Fabric

Before moving on, write down:

- Storage account name
- Storage account resource ID
- DFS endpoint URL: `https://<storage-account>.dfs.core.windows.net`
- Log Analytics workspace name and resource ID
- Cost export name

Challenge 3 depends on these values to create OneLake shortcuts without copying data.

## Success criteria

- [ ] ADLS Gen2 storage exists with hierarchical namespace enabled
- [ ] All five containers exist: `costs`, `metrics`, `logs`, `metadata`, `diagnostics`
- [ ] FOCUS cost Parquet is present in `costs` and validated
- [ ] Resource Graph metadata Parquet is present in `metadata`
- [ ] Log Analytics data export rule is enabled for app request/dependency/trace/exception/metric tables
- [ ] Diagnostic settings are configured for supported resources and begin flowing
- [ ] `validate_exports.py` reports file counts, sizes, latest timestamps, and schemas
- [ ] The team has recorded the storage account name, resource ID, and DFS endpoint URL

> 🧭 **Checkpoint:** show your coach the five containers, one FOCUS Parquet file, one Resource Graph
> Parquet file, the active Log Analytics export rule, and your recorded Fabric shortcut coordinates.

## Hints

<details>
<summary>Deploying the ingestion layer</summary>

```bash
cd resources/observability-ingestion
azd auth login
azd up      # use the same subscription and region from Challenge 0
```

After deployment, capture the outputs:

- `AZURE_STORAGE_ACCOUNT_NAME`
- `AZURE_STORAGE_ACCOUNT_ID`
- `AZURE_LOG_ANALYTICS_WORKSPACE_NAME`
- `AZURE_LOG_ANALYTICS_WORKSPACE_ID`

</details>

<details>
<summary>Previewing diagnostic settings before applying</summary>

The diagnostic setup script supports dry-run mode:

```bash
cd resources/observability-ingestion/src/scripts
pip install -r requirements.txt

python setup_diagnostic_settings.py \
  --subscription-id <SUBSCRIPTION_ID> \
  --workspace-id <WORKSPACE_RESOURCE_ID> \
  --storage-account-id <STORAGE_ACCOUNT_RESOURCE_ID> \
  --dry-run
```

When the preview looks right, run the same command without `--dry-run`.
</details>

<details>
<summary>Exporting Resource Graph metadata</summary>

```bash
cd resources/observability-ingestion/src/scripts

python resource_graph_export.py \
  --subscription-id <SUBSCRIPTION_ID> \
  --storage-account <STORAGE_ACCOUNT_NAME> \
  --container metadata
```

The script writes Parquet files under `metadata/resource-graph/year=*/month=*/day=*/`.
</details>

<details>
<summary>Validating the landing zone</summary>

```bash
cd resources/observability-ingestion/src/scripts

python validate_exports.py \
  --storage-account <STORAGE_ACCOUNT_NAME>
```

Empty containers are useful evidence too: they usually mean an export has not run yet, no traffic has
arrived, or a diagnostic setting has not emitted data.
</details>

<details>
<summary>Why FOCUS matters</summary>

FOCUS is the FinOps Open Cost and Usage Specification. It gives the Control Tower standardized fields
such as `BilledCost`, `EffectiveCost`, `ServiceName`, `ResourceId`, and `Tags`, so Challenge 4 can
join spend to resource metadata and Challenge 5 can show cost by service, team, and use case.
</details>

## Resources

- [`resources/observability-ingestion/README.md`](../resources/observability-ingestion/README.md) — landing zone deployment and scripts
- [`resources/observability-ingestion/src/scripts/`](../resources/observability-ingestion/src/scripts/) — Resource Graph, diagnostic settings, and validation scripts
- [`docs/architecture.md`](../docs/architecture.md) — the Ingest stage and data layout
- Previous: **[Challenge 1 — Light Up the Agents](challenge-01-agent-telemetry.md)**

---

➡️ Next: **[Challenge 3 — Connect Fabric to the Enterprise](challenge-03-onelake-foundation.md)**
