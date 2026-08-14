# Solution Deployment Guide

This guide walks you through deploying the entire solution end to end. Follow each step in order. Before you begin, fill in the **Variables** table below with your own values and reuse those values wherever they are referenced.

> [!IMPORTANT]
> If you hit **any** error during deployment, stop and resolve it before continuing. Do not skip steps or improvise additional ones.

---

## Before you start

### Prerequisites

- Access to the target Azure subscription with permission to create resource groups and resources.
- [Azure Developer CLI (`azd`)](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd) installed and signed in (`azd auth login`).
- [Azure CLI (`az`)](https://learn.microsoft.com/cli/azure/install-azure-cli) installed and signed in (`az login`).
- Python installed (the repo includes a virtual environment under `fct/` you can activate).
- Access to a Microsoft Fabric tenant with a capacity you can use.

### Rules to keep in mind

- **Environment names must be 8 characters or fewer.** If any environment name is longer, change it before proceeding.
- Only use the values you defined in the **Variables** table (or values produced by a previous step).

---

## Variables

Fill in this table first, then reuse these values throughout the guide. The sample values shown are examples — replace them with your own.

| Variable | Description | Example value |
| --- | --- | --- |
| Subscription name | Azure subscription to deploy into | `FoundryCentralSubscription` |
| Subscription ID | ID of that subscription | `XXXXXXXX-YYYY-ZZZZ-KKKK-QQQQQQQQQQQQ` |
| Location | Azure region for all resources | `sweden central` |
| Agent-workload env name | `azd` environment name for the agent workload (**max 8 chars**) | `fctv01` |
| Agent-workload resource group | Resource group for the agent workload | `RG-Foundry-01` |
| Observability-ingestion env name | `azd` environment name for observability ingestion (**max 8 chars**) | `fctv01-o` |
| Observability-ingestion resource group | Resource group for observability ingestion | `RG-Foundry-01-o` |
| Fabric workspace name | Name of the Microsoft Fabric workspace to create | `ws-sc-fct-01` |
| Fabric capacity | Fabric capacity to attach the workspace to | `fabricsc01` |

> [!NOTE]
> Some values are only known **after** a deployment completes (for example, the exact storage account name, Cosmos DB name, workspace ID, capacity ID, and connection IDs). Note them down as you go — later steps depend on them.

---

## Step 1 — Deploy the agent workload

1. Open a terminal and change into the agent-workload folder:

   ```powershell
   cd resources\agent-workload
   ```

2. Run the deployment:

   ```powershell
   azd up
   ```

3. If prompted for an environment name, enter your **Agent-workload env name** (e.g. `fctv10`).

When this completes, note the **resource group** and the **Cosmos DB account name** that were created — you'll need them later.

---

## Step 2 — Deploy observability ingestion

1. Change into the observability-ingestion folder:

   ```powershell
   cd resources\observability-ingestion
   ```

2. Run the deployment:

   ```powershell
   azd up
   ```

3. If prompted:
   - **Environment name** → enter your **Observability-ingestion env name** (e.g. `fctv01-o`).
   - **Agent-workload resource group** → enter the resource group used in Step 1.
   - **Log Analytics workspace** → enter the **Agent-workload env name** followed by `-log`.
     - Example: if the agent-workload env name is `agf`, the Log Analytics workspace is `agf-log`.

4. After the deployment finishes, note the **storage account name** that was created.

5. Run the resource graph export script. Replace the placeholders with your subscription ID and the storage account name you just noted:

   ```powershell
   python resource_graph_export.py --subscription-id <SUBSCRIPTION_ID> --storage-account <STORAGE_ACCOUNT_NAME> --container metadata
   ```

---

## Step 3 — Create and configure the Fabric workspace

Do this in the Microsoft Fabric portal.

1. Create a new workspace and assign it to the **`fabricsc`** capacity.
2. Name the workspace using your **Fabric workspace name** (e.g. `ws_sc_fct_01`).
3. Enable the **workspace managed identity** for the workspace.
4. Grant the workspace managed identity the **Storage Blob Data Contributor** role on the **storage account created in Step 2** (observability ingestion).

---

## Step 4 — Create Fabric connections

Create the following three connections in Microsoft Fabric.

1. **Storage account connection**
   - Connects to the storage account created for observability ingestion (Step 2).
   - Authentication: **workspace identity**.
   - Connection name: the storage account name with the **observability-ingestion env name** as a suffix.

2. **Cosmos DB connection**
   - Connection type: **Azure Cosmos DB v2**.
   - Connects to the Cosmos DB created for the agent workload (Step 1).
   - Authentication: **key**.
   - Connection name: the Cosmos DB name with the **agent-workload env name** as a suffix.

3. **Fabric Data Pipelines connection**
   - A Fabric Data Pipelines connection (later used to import a pipeline that uses an *Invoke pipeline* activity).
   - Authentication: **workspace identity**.
   - Connection name: the workspace name with the **agent-workload env name** as a suffix.

---

## Step 5 - Create telemetry

1. Interact with an agent or a model deployed, using Foundry portal or the frontend application created

---

## Step 6 — Deploy the Fabric control tower

1. Change into the control-tower folder:

   ```powershell
   cd resources\fabric-control-tower
   ```

2. Set up the Fabric workspace. Replace each placeholder with the values gathered in earlier steps:

   ```powershell
   python src/setup/setup_fabric_workspace.py --workspace-name "<FABRIC_WORKSPACE_NAME>" --storage-account-url "https://<STORAGE_ACCOUNT_NAME>.dfs.core.windows.net" --capacity-id "<FABRIC_CAPACITY_ID>" --connection-id "<FABRIC_CONNECTION_ID_TO_STORAGE_ACCOUNT>" --pipeline_connection_id "<FABRIC_PIPELINE_CONNECTION_ID>"
   ```

   | Placeholder | Where it comes from |
   | --- | --- |
   | `<FABRIC_WORKSPACE_NAME>` | Your Fabric workspace name (Step 3) |
   | `<STORAGE_ACCOUNT_NAME>` | Storage account created in Step 2 |
   | `<FABRIC_CAPACITY_ID>` | ID of the `fabricsc` capacity |
   | `<FABRIC_CONNECTION_ID_TO_STORAGE_ACCOUNT>` | Storage account connection created in Step 4.1 |
   | `<FABRIC_PIPELINE_CONNECTION_ID>` | Data Pipelines connection created in Step 4.3 |

3. Set up Cosmos DB mirroring. Replace each placeholder:

   ```powershell
   python src/setup/setup_cosmos_mirroring.py --workspace-id "<FABRIC_WORKSPACE_ID>" --cosmos-account "<COSMOSDB_NAME>" --database "agentsdb" --connection-id "<FABRIC_CONNECTION_ID_TO_COSMOSDB>"
   ```

   | Placeholder | Where it comes from |
   | --- | --- |
   | `<FABRIC_WORKSPACE_ID>` | ID of the Fabric workspace (Step 3) |
   | `<COSMOSDB_NAME>` | Cosmos DB account created in Step 1 |
   | `<FABRIC_CONNECTION_ID_TO_COSMOSDB>` | Cosmos DB connection created in Step 4.2 |

---

## Step 7 — Manual actions (pause here)

> [!IMPORTANT]
> Stop and complete these manual actions before continuing:
> 1. Run the **FOCUS Export**.
> 2. Run the notebook **`Data_Model_Build`**.
>
> Only continue to Step 7 once both have finished successfully.

---

## Step 8 — Deploy the report sample

1. Change into the report-sample folder:

   ```powershell
   cd resources\report-sample
   ```

2. Upload the **semantic model** and the **report**, making sure the source points to the **lakehouse in the Fabric workspace** you created (Step 3).

---

## If something goes wrong

- Stop at the failing step and do not run any further steps.
- Review the error message and resolve the root cause.
- Re-run only the step that failed once the issue is fixed.

# Next Steps

## Adding existing resources for Foundry or Log Analytics Workspaces

If Foundry resources already exists, already connected to Log Analytics Worksapces or generally any Log Analytics Workspace resource, those can be easily connected to this solution.

Once deployed, you can:
1. Enable, in Log Analytics Workspace, Data Export rule. You can configure the rule to export data in the same Storage Account created in this solution or in any other Storage Account. Remember that Data Export Rule can export data in a Storage Account within the same region of the Log Analytics Workspace you're configuring. 
Tables to be exported:
   - AppDependencies
   - AppTraces
   - AppRequests
   - AppMetrics
2. Create a Fabric connection to the Storage Account if new, or reuse the already created one.
3. Add a folder shortcut in each folder of the Observability Lakehouse. In 'appdependencies' folder add a shortcut to 'am-appdependencies' in your Storage Account. Tips: name the shortcut so to recognise easily which Storage Account it is connected to.

Data_Model_Build notebook is already configured to span all subfolders, so every new folder shortcut added in this way will be recognised and read by the notebook.

## Adding additional resources

To add any database or storage of interest for your data analysis, leverage shortcuts in Observability Lakehouse and update the Data_Model_Build notebook so to read from it. Remember also to update your semantic model definition.