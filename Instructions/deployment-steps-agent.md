# Deployment Steps

These guides shows steps and variables to be used to deploy the entire solution.

## Variables

- **subscription-name** = FoundryCentralSubscription
- **subscription-id** = XXXXXXXX-YYYY-ZZZZ-KKKK-QQQQQQQQQQQQ

- **location** = sweden central

- **env name for agent-workload** = fctv01
- **Resource Group for agent-workload** = RG-Foundry-01

- **env name for observability-ingestion** = fctv01-o
- **Resource Group for observability-ingestion** = RG-Foundry-01-o

- **Fabric workspace name** = ws_sc_fct_01
- **Fabric capacity to leverage** = fabricsc01

> **!!! Environment name must be not more than 8 character long !!!**

## Steps

1. **Deploy agent-workload**
   - a. Cd resources\agent-workload
   - b. azd up
     - i. if asked, enter env name for agent-workload
2. **Deploy observability-ingestion**
   - a. Cd resources\observability-ingestion
   - b. Azd up
     - i. if asked, enter env name for observability-ingestion
     - iv. If asked for agent-workload resource group and log analytics workspace:
       - resource group = resource group used to deploy agent-workload
       - log analytics workspace = env name for agent-workload + '-log' (example, if env name for agent-workload is 'agf', log analytics workspace will be 'agf-log')
   - c. Run python script:
     - i. Recover the subscription id and the storage account just created
     - ii. python resource_graph_export.py --subscription-id <SUBSCRIPTION_ID> --storage-account <STORAGE_ACCOUNT_NAME> --container metadata
3. **Deploy and configure fabric workspace**
   - a. Create a workspace in microsoft fabric, using fabricsc capacity
   - b. Create a workspace with correct name
   - c. Enable managed identity on the workspace
   - d. Give Storage Blob Data Contributor at workspace managed identity to storage account created during agent-observability deployment
4. **Create Fabric connections**
   - a. Create, in Fabric, a connection to the storage account created for observability-ingestion, using workspace identity. Called the connection name as the storage account name with env name for observability-ingestion as a suffix
   - b. Create, in Fabric, a connection to cosmosdb (connection type "azure cosmos db v2") created for agent-workload, using key as authentication method. Called the connection name as the cosmos name with env name for agent-workload as a suffix
   - C. a. Create, in Fabric, a Fabric Data Pipelines connection, using workspace identity, later used to import a pipeline that will use an invoke pipeline activity. Called the connection name as name of the workspace with env name for agent-workload as a suffix
5. **STOP any further action**, ask user to send a message to any model or agent deployed (using Foundry or frontend app created)
6. **Deploy fabric-control-tower**
   - a. Cd resources\fabric-control-tower
   - b. python src/setup/setup_fabric_workspace.py --workspace-name "<FABRIC_WORKSPACE_NAME>" --storage-account-url "https://<STORAGE_ACCOUNT_NAME>.dfs.core.windows.net" --capacity-id "<FABRIC_CAPACITY_ID>" --connection-id "<FABRIC_CONNECTION_ID_TO_STORAGE_ACCOUNT>" --pipeline_connection_id "<FABRIC_PIPELINE_CONNECTION_ID>"
   - c. python src/setup/setup_cosmos_mirroring.py --workspace-id "<FABRIC_WORKSPACE_ID>" --cosmos-account "<COSMOSDB_NAME>" --database "agentsdb" --connection-id "<FABRIC_CONNECTION_ID_TO_COSMOSDB>"
7. **STOP any further action**, ask user to run FOCUS Export and notebook Data_Model_Build
8. **Deploy report-sample**
   - a. cd resources\report-sample
   - b. upload semantic model and report, with the correct source (lahehouse in the fabric workspace created)

## Rules

- in case there is ANY error during deployment, STOP so user can take action. DO NOT PERFORM ANY ADDITIONAL STEP
- in case scripts ask for environment name, subscriptions, or additional informations, used ONLY the one provided or inferred by previous deployment
- DO NOT generate additional variables
- if you are not sure about a step, or an action, STOP with a brief description of the issue, so user can take action
- if any environment name is longer than 8 characters, stop and ask user to change it
