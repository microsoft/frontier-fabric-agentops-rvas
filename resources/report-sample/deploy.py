"""Deploy the sample **AgentOps Analytics** semantic model and Power BI report
into a Microsoft Fabric workspace, wiring the Direct Lake model to a lakehouse
that is resolved *at deploy time*.

The semantic model definition ships with a placeholder source:

    Source = Sql.Database("{{LAKEHOUSE_SQL_ENDPOINT}}", "{{LAKEHOUSE_NAME}}")

Because every deployment creates a brand-new lakehouse (with a brand-new SQL
analytics endpoint), the endpoint is looked up from the target workspace's
lakehouse when this script runs and substituted into the definition. The report
is likewise re-pointed at the freshly created semantic model.

Tokens substituted:
    {{LAKEHOUSE_SQL_ENDPOINT}}  -> lakehouse SQL analytics endpoint FQDN (resolved)
    {{LAKEHOUSE_NAME}}          -> lakehouse name (== the SQL database name)
    {{WORKSPACE_NAME}}          -> target workspace display name (resolved)
    {{SEMANTIC_MODEL_NAME}}     -> --semantic-model-name
    {{SEMANTIC_MODEL_ID}}       -> id of the model created/updated by this script

Usage:
    python deploy.py \
        --workspace-id <fabric-workspace-id> \
        [--lakehouse-name Observability] \
        [--semantic-model-name "AgentOps Analytics"] \
        [--report-name "AgentOps Analytics Report"] \
        [--skip-refresh]

Prereqs:
    - The workspace already contains the lakehouse (default name "Observability")
      with its SQL analytics endpoint provisioned and the `analytics.*` tables
      populated (see resources/fabric-control-tower).
    - `az login` (DefaultAzureCredential is used for both Fabric and Power BI).
"""

from __future__ import annotations

import base64
import pathlib
import sys
import time
from typing import Any

import click
import requests
from azure.identity import DefaultAzureCredential
from rich.console import Console

console = Console()

FABRIC_API_BASE = "https://api.fabric.microsoft.com/v1"
FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"
PBI_API_BASE = "https://api.powerbi.com/v1.0/myorg"
PBI_SCOPE = "https://analysis.windows.net/powerbi/api/.default"

HERE = pathlib.Path(__file__).resolve().parent
MODEL_DIR = HERE / "semantic-model"
REPORT_DIR = HERE / "report"

# Files that are only relevant to git/PBIP tooling, not the REST definition.
_EXCLUDE_NAMES = {".platform", ".pbi"}


class FabricClient:
    """Minimal Fabric + Power BI REST client backed by DefaultAzureCredential."""

    def __init__(self, credential: DefaultAzureCredential) -> None:
        self._credential = credential
        self._fabric_token: str | None = None
        self._pbi_token: str | None = None

    def _token(self, scope: str) -> str:
        return self._credential.get_token(scope).token

    def _fabric_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token(FABRIC_SCOPE)}",
            "Content-Type": "application/json",
        }

    def _pbi_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token(PBI_SCOPE)}",
            "Content-Type": "application/json",
        }

    # -- generic helpers ------------------------------------------------

    def get(self, path: str) -> dict[str, Any]:
        resp = requests.get(f"{FABRIC_API_BASE}{path}", headers=self._fabric_headers(), timeout=60)
        resp.raise_for_status()
        return resp.json()

    def list_all(self, path: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        while path:
            body = self.get(path)
            items.extend(body.get("value", []))
            nxt = body.get("continuationUri")
            path = nxt.replace(FABRIC_API_BASE, "") if nxt else ""
        return items

    def _wait_for_lro(self, response: requests.Response) -> None:
        """Block until a 202 long-running operation reaches a terminal state."""
        op_url = response.headers.get("Location") or response.headers.get("Operation-Location")
        if not op_url:
            return
        retry = int(response.headers.get("Retry-After", "2") or "2")
        while True:
            time.sleep(max(retry, 1))
            status = requests.get(op_url, headers=self._fabric_headers(), timeout=60).json()
            state = status.get("status")
            if state == "Succeeded":
                return
            if state in {"Failed", "Undetermined"}:
                raise RuntimeError(f"Operation {state}: {status}")

    # -- workspace / lakehouse resolution -------------------------------

    def workspace_name(self, workspace_id: str) -> str:
        return self.get(f"/workspaces/{workspace_id}")["displayName"]

    def resolve_lakehouse_endpoint(self, workspace_id: str, lakehouse_name: str) -> str:
        """Return the SQL analytics endpoint FQDN for the named lakehouse."""
        lakehouses = self.list_all(f"/workspaces/{workspace_id}/lakehouses")
        match = next((lh for lh in lakehouses if lh.get("displayName") == lakehouse_name), None)
        if match is None:
            names = ", ".join(lh.get("displayName", "?") for lh in lakehouses) or "(none)"
            raise RuntimeError(
                f"Lakehouse '{lakehouse_name}' not found in workspace. Available: {names}"
            )
        sqlep = (match.get("properties") or {}).get("sqlEndpointProperties") or {}
        endpoint = sqlep.get("connectionString")
        if not endpoint:
            raise RuntimeError(
                f"Lakehouse '{lakehouse_name}' has no SQL endpoint yet "
                f"(provisioningStatus={sqlep.get('provisioningStatus')!r}). Wait and retry."
            )
        return endpoint

    # -- item create / update -------------------------------------------

    def find_item_id(self, workspace_id: str, item_type_path: str, display_name: str) -> str | None:
        for item in self.list_all(f"/workspaces/{workspace_id}/{item_type_path}"):
            if item.get("displayName") == display_name:
                return item.get("id")
        return None

    def deploy_item(
        self,
        workspace_id: str,
        item_type_path: str,
        display_name: str,
        definition: dict[str, Any],
        description: str | None = None,
    ) -> str:
        """Create the item, or update its definition if it already exists. Returns the id."""
        existing_id = self.find_item_id(workspace_id, item_type_path, display_name)
        if existing_id:
            resp = requests.post(
                f"{FABRIC_API_BASE}/workspaces/{workspace_id}/{item_type_path}/{existing_id}/updateDefinition",
                headers=self._fabric_headers(),
                json={"definition": definition},
                timeout=120,
            )
            resp.raise_for_status()
            if resp.status_code == 202:
                self._wait_for_lro(resp)
            console.print(f"  [green]updated[/green] {item_type_path} '{display_name}'")
            return existing_id

        payload: dict[str, Any] = {"displayName": display_name, "definition": definition}
        if description:
            payload["description"] = description
        resp = requests.post(
            f"{FABRIC_API_BASE}/workspaces/{workspace_id}/{item_type_path}",
            headers=self._fabric_headers(),
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        if resp.status_code == 202:
            self._wait_for_lro(resp)
            new_id = self.find_item_id(workspace_id, item_type_path, display_name)
        else:
            new_id = resp.json().get("id") or self.find_item_id(workspace_id, item_type_path, display_name)
        if not new_id:
            raise RuntimeError(f"Created {item_type_path} '{display_name}' but could not resolve its id.")
        console.print(f"  [green]created[/green] {item_type_path} '{display_name}' ({new_id})")
        return new_id

    # -- Direct Lake framing --------------------------------------------

    def refresh_dataset(self, workspace_id: str, dataset_id: str) -> None:
        resp = requests.post(
            f"{PBI_API_BASE}/groups/{workspace_id}/datasets/{dataset_id}/refreshes",
            headers=self._pbi_headers(),
            json={"type": "full"},
            timeout=60,
        )
        resp.raise_for_status()


def _build_parts(root: pathlib.Path, substitutions: dict[str, str]) -> list[dict[str, str]]:
    """Base64-encode every definition file under `root`, applying token substitutions.

    The part path is the file path relative to `root`, using forward slashes.
    Tokens are replaced at the byte level so non-token files pass through untouched.
    """
    parts: list[dict[str, str]] = []
    for file in sorted(p for p in root.rglob("*") if p.is_file()):
        if file.name in _EXCLUDE_NAMES:
            continue
        data = file.read_bytes()
        for token, value in substitutions.items():
            data = data.replace(token.encode("utf-8"), value.encode("utf-8"))
        rel = file.relative_to(root).as_posix()
        parts.append(
            {
                "path": rel,
                "payload": base64.b64encode(data).decode("ascii"),
                "payloadType": "InlineBase64",
            }
        )
    return parts


@click.command()
@click.option("--workspace-id", required=True, help="Target Fabric workspace id.")
@click.option("--lakehouse-name", default="Observability", show_default=True,
              help="Lakehouse whose SQL endpoint the Direct Lake model reads from.")
@click.option("--semantic-model-name", default="AgentOps Analytics", show_default=True)
@click.option("--report-name", default="AgentOps Analytics Report", show_default=True)
@click.option("--skip-refresh", is_flag=True, default=False,
              help="Skip the post-deploy Direct Lake refresh (frame it later in Fabric).")
def main(
    workspace_id: str,
    lakehouse_name: str,
    semantic_model_name: str,
    report_name: str,
    skip_refresh: bool,
) -> None:
    console.rule("[bold blue]Report Sample Deploy[/bold blue]")
    try:
        client = FabricClient(DefaultAzureCredential())

        ws_name = client.workspace_name(workspace_id)
        endpoint = client.resolve_lakehouse_endpoint(workspace_id, lakehouse_name)
        console.print(f"Workspace : {ws_name}")
        console.print(f"Lakehouse : {lakehouse_name}")
        console.print(f"SQL endpoint (resolved variable): {endpoint}")

        # 1. Semantic model — inject the resolved lakehouse source.
        model_parts = _build_parts(
            MODEL_DIR,
            {
                "{{LAKEHOUSE_SQL_ENDPOINT}}": endpoint,
                "{{LAKEHOUSE_NAME}}": lakehouse_name,
            },
        )
        model_id = client.deploy_item(
            workspace_id,
            "semanticModels",
            semantic_model_name,
            {"parts": model_parts},
            description="Direct Lake star schema over analytics.* (cost, tokens, conversations, governance).",
        )

        # 2. Report — re-point the connection at the model just deployed.
        report_parts = _build_parts(
            REPORT_DIR,
            {
                "{{WORKSPACE_NAME}}": ws_name,
                "{{SEMANTIC_MODEL_NAME}}": semantic_model_name,
                "{{SEMANTIC_MODEL_ID}}": model_id,
            },
        )
        client.deploy_item(
            workspace_id,
            "reports",
            report_name,
            {"parts": report_parts},
            description="Cost, governance, reliability, token consumption & conversation steps.",
        )

        # 3. Frame the Direct Lake model (best-effort).
        if skip_refresh:
            console.print("[yellow]Skipping refresh (--skip-refresh).[/yellow]")
        else:
            try:
                client.refresh_dataset(workspace_id, model_id)
                console.print("[green]Triggered Direct Lake refresh.[/green]")
            except Exception as exc:  # noqa: BLE001 — refresh is best-effort
                console.print(
                    f"[yellow]Refresh not triggered ({exc}). Open the model in Fabric, set the data "
                    f"source credentials if prompted, and refresh to frame Direct Lake.[/yellow]"
                )

        console.print("\n[bold green]Report sample deployed.[/bold green]")
    except requests.HTTPError as exc:
        console.print(f"\n[bold red]Fabric/Power BI API error:[/bold red] {exc}")
        if exc.response is not None:
            console.print(exc.response.text)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        console.print(f"\n[bold red]Error:[/bold red] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
