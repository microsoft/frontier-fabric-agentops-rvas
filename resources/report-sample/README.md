# Report Sample — AgentOps Analytics

A reusable **Direct Lake** semantic model and **Power BI report** over the
`analytics.*` star schema built by
[`resources/fabric-control-tower`](../fabric-control-tower). Ship them into any
freshly deployed workspace — the lakehouse source is resolved **at deploy time**,
so the model always reads from the new deployment's lakehouse.

## Contents

| Path | What it is |
| --- | --- |
| `semantic-model/` | `AgentOps Analytics` semantic model definition (TMDL). 9 tables, measures, relationships. |
| `report/` | `AgentOps Analytics Report` definition (PBIR). 6 pages: Overview, Cost, Governance, Reliability & Latency, Token Consumption, Conversation Steps. |
| `deploy.py` | Resolves the lakehouse SQL endpoint, substitutes the variables, and creates/updates both items. |
| `requirements.txt` | Python dependencies. |

## The lakehouse source is a variable

The model's source is a placeholder, filled in by `deploy.py`:

```
Source = Sql.Database("{{LAKEHOUSE_SQL_ENDPOINT}}", "{{LAKEHOUSE_NAME}}")
```

| Token | Filled with |
| --- | --- |
| `{{LAKEHOUSE_SQL_ENDPOINT}}` | SQL analytics endpoint FQDN, looked up from the target lakehouse |
| `{{LAKEHOUSE_NAME}}` | Lakehouse name (also the SQL database name), default `Observability` |
| `{{WORKSPACE_NAME}}` | Target workspace display name (report connection) |
| `{{SEMANTIC_MODEL_NAME}}` | `--semantic-model-name` (report connection catalog) |
| `{{SEMANTIC_MODEL_ID}}` | Id of the model created by `deploy.py` (report connection) |

The table partitions use `expressionSource: 'DirectLake - Analytics'`, so the
endpoint lives in exactly one place (`semantic-model/definition/expressions.tmdl`).

## Deploy

Prerequisites: the target workspace already has the `Observability` lakehouse with
its SQL endpoint provisioned and the `analytics.*` tables populated, and you are
signed in (`az login`).

```bash
pip install -r requirements.txt

python deploy.py --workspace-id <fabric-workspace-id>
```

Options: `--lakehouse-name` (default `Observability`), `--semantic-model-name`,
`--report-name`, `--skip-refresh`.

Re-running updates the existing items in place (idempotent).

> Direct Lake framing: `deploy.py` triggers a refresh best-effort. If it can't
> (e.g. data-source credentials aren't set for the calling identity), open the
> model in Fabric, set/confirm the SQL endpoint credentials, and refresh.
