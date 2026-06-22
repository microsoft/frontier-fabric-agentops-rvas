# Resources — Reference Implementation Toolbox

This directory is your **toolbox** for the hackathon. It contains a complete, working reference
implementation of the AgentOps Control Tower — infrastructure-as-code, application code, Fabric setup
automation, PySpark notebooks, pipelines, and a semantic model.

> 🧰 **How to use it:** Teams are encouraged to deploy the Azure foundation (agent workload + landing
> zone) from here so they can spend their creative energy on the **Fabric Control Tower**. Coaches
> hold the keys to the reference solution for each challenge and reveal it as needed — see the
> [Coach Handbook](../coach/README.md).

## What's here

| Component | Directory | Used in | What it provides |
|---|---|---|---|
| **Agent Workload** | [`agent-workload/`](agent-workload/) | Challenge 1 | Full-stack Azure AI Foundry agent app — frontend (Next.js), backend & agent (FastAPI), behind API Management, backed by Cosmos DB, instrumented with Application Insights. Bicep IaC + `azd` manifest. |
| **Observability Ingestion** | [`observability-ingestion/`](observability-ingestion/) | Challenge 2 | The ADLS Gen2 landing zone — Cost Management FOCUS exports, Resource Graph metadata, Log Analytics data export, and diagnostic settings. Bicep modules + Python export/validation scripts. |
| **Fabric Control Tower** | [`fabric-control-tower/`](fabric-control-tower/) | Challenges 3–6 | The Fabric layer — workspace/Lakehouse setup, OneLake shortcuts, Cosmos DB Mirroring, the Bronze/Silver/Gold notebooks, orchestration pipelines, and the Direct Lake semantic model. |
| **Observability SDK** | [`observability-sdk/`](observability-sdk/) | Challenge 1 (reference) | Shared Python library defining the agent telemetry contract — event schema, metrics, Azure Monitor wiring, and alert thresholds. |

## How it maps to the challenges

```
Challenge 1  ──▶  agent-workload/          (the telemetry SOURCE)
Challenge 2  ──▶  observability-ingestion/ (the landing ZONE)
Challenge 3  ──▶  fabric-control-tower/src/setup/   (shortcuts + Mirroring)
Challenge 4  ──▶  fabric-control-tower/fabric/      (medallion notebooks + pipelines)
Challenge 5  ──▶  fabric-control-tower/src/setup/semantic_model.json  (Direct Lake model)
Challenge 6  ──▶  fabric-control-tower/  +  Power BI / Data Activator  (operationalize)
```

## Important notes

- **This is reference material, not a turnkey product.** Names, regions, and IDs must be set for your
  environment. Read each component's README before deploying.
- **Deploy in order where there are dependencies:** the agent workload and landing zone are
  independent of each other, but the Fabric Control Tower consumes both.
- **Cost & cleanup:** everything is sized for a low-cost hackathon. Tear down with `azd down --purge`
  in each workload directory when you're finished (see [prerequisites](../docs/prerequisites.md)).
- **Same tenant:** keep the Azure subscription and Fabric capacity in the **same Entra tenant** to
  avoid managed-identity and Mirroring friction.

## Architecture

For how these components fit together end-to-end, see
[`docs/architecture.md`](../docs/architecture.md).
