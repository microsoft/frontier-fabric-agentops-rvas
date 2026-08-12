"""Setup script for provisioning a Microsoft Fabric workspace with Lakehouse,
ADLS Gen2 shortcuts, notebooks, and pipelines via the Fabric REST API.

Usage:
    python setup_fabric_workspace.py \
        --storage-account-url https://<account>.dfs.core.windows.net \
        --capacity-id <fabric-capacity-id>
"""

from __future__ import annotations

import base64
import json
import pathlib
import sys
from typing import Any

import click
import requests
from azure.identity import DefaultAzureCredential
from rich.console import Console
from rich.table import Table

FABRIC_API_BASE = "https://api.fabric.microsoft.com/v1"
FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"

# Shortcuts created directly under Files/ (name == container == subpath).
ROOT_SHORTCUT_CONTAINERS = [
    "costs",
    "metadata",
]

# App-telemetry families: each becomes a plain lakehouse folder under Files/ that
# holds a shortcut to its matching am-* storage container
# (e.g. Files/appdependencies/am-appdependencies). Keyed by folder -> container.
NESTED_SHORTCUT_CONTAINERS = {
    "appdependencies": "am-appdependencies",
    "apptraces": "am-apptraces",
    "appmetrics": "am-appmetrics",
    "apprequests": "am-apprequests",
}

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
NOTEBOOKS_DIR = REPO_ROOT / "fabric" / "notebooks"
PIPELINES_DIR = REPO_ROOT / "fabric" / "pipelines"

console = Console()


class FabricClient:
    """Thin wrapper around the Fabric REST API with idempotent helpers."""

    def __init__(self, credential: DefaultAzureCredential) -> None:
        self._credential = credential
        self._token: str | None = None

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _get_access_token(self) -> str:
        """Acquire (or refresh) an access token for the Fabric API."""
        token = self._credential.get_token(FABRIC_SCOPE)
        self._token = token.token
        return self._token

    @property
    def _headers(self) -> dict[str, str]:
        token = self._get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Low-level HTTP helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, **kwargs: Any) -> requests.Response:
        url = f"{FABRIC_API_BASE}{path}"
        resp = requests.get(url, headers=self._headers, timeout=60, **kwargs)
        resp.raise_for_status()
        return resp

    def _post(self, path: str, payload: dict[str, Any] | None = None, **kwargs: Any) -> requests.Response:
        url = f"{FABRIC_API_BASE}{path}"
        resp = requests.post(url, headers=self._headers, json=payload, timeout=120, **kwargs)
        resp.raise_for_status()
        return resp

    # ------------------------------------------------------------------
    # Idempotent item helpers
    # ------------------------------------------------------------------

    def _list_items(self, workspace_id: str, item_type: str | None = None) -> list[dict[str, Any]]:
        """Return all items in a workspace, optionally filtered by type."""
        items: list[dict[str, Any]] = []
        path = f"/workspaces/{workspace_id}/items"
        if item_type:
            path += f"?type={item_type}"

        while path:
            resp = self._get(path)
            body = resp.json()
            items.extend(body.get("value", []))
            continuation = body.get("continuationUri")
            if continuation:
                # continuationUri is an absolute URL; strip the base so _get works
                path = continuation.replace(FABRIC_API_BASE, "")
            else:
                path = ""
        return items

    def _find_item(self, workspace_id: str, display_name: str, item_type: str) -> dict[str, Any] | None:
        """Find an existing item by display name and type."""
        items = self._list_items(workspace_id, item_type=item_type)
        for item in items:
            if item.get("displayName") == display_name:
                return item
        return None

    def create_or_get_item(
        self,
        workspace_id: str,
        display_name: str,
        item_type: str,
        definition: dict[str, Any] | None = None,
        description: str | None = None,
        creation_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a workspace item if it does not already exist, otherwise return existing."""
        existing = self._find_item(workspace_id, display_name, item_type)
        if existing:
            console.print(f"  [yellow]⏭  {item_type} '{display_name}' already exists — skipping.[/yellow]")
            return existing

        payload: dict[str, Any] = {
            "displayName": display_name,
            "type": item_type,
        }
        if description:
            payload["description"] = description
        if definition:
            payload["definition"] = definition
        # creationPayload carries type-specific options (e.g. enableSchemas for a Lakehouse).
        if creation_payload:
            payload["creationPayload"] = creation_payload

        resp = self._post(f"/workspaces/{workspace_id}/items", payload)
        if resp.status_code == 202:
            # Long-running operation — the item is being created asynchronously.
            console.print(f"  [cyan]⏳ {item_type} '{display_name}' creation accepted (async).[/cyan]")
            return {"displayName": display_name, "type": item_type}

        item = resp.json()
        console.print(f"  [green]✔  Created {item_type} '{display_name}'.[/green]")
        return item

    def update_item_definition(self, workspace_id: str, item_id: str, definition: dict[str, Any]) -> None:
        """Overwrite an existing item's definition (e.g. push new notebook content)."""
        self._post(
            f"/workspaces/{workspace_id}/items/{item_id}/updateDefinition",
            {"definition": definition},
        )

    def create_or_update_notebook(
        self,
        workspace_id: str,
        display_name: str,
        definition: dict[str, Any],
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create a Notebook, or overwrite its definition if it already exists.

        Unlike `create_or_get_item` (which skips existing items), this pushes the
        latest notebook content — with the default-lakehouse metadata baked into the
        supplied definition — so re-running the setup refreshes notebooks in place.
        """
        existing = self._find_item(workspace_id, display_name, "Notebook")
        if existing:
            self.update_item_definition(workspace_id, existing["id"], definition)
            console.print(f"  [green]✔  Updated Notebook '{display_name}'.[/green]")
            return existing
        return self.create_or_get_item(
            workspace_id,
            display_name,
            "Notebook",
            definition=definition,
            description=description,
        )

    # ------------------------------------------------------------------
    # Workspace
    # ------------------------------------------------------------------

    def create_or_get_workspace(self, display_name: str, capacity_id: str) -> dict[str, Any]:
        """Create a workspace or return the existing one, then assign capacity."""
        # List workspaces the caller has access to and check for a match.
        resp = self._get("/workspaces")
        workspaces = resp.json().get("value", [])
        for ws in workspaces:
            if ws.get("displayName") == display_name:
                console.print(f"[yellow]⏭  Workspace '{display_name}' already exists.[/yellow]")
                return ws

        payload = {
            "displayName": display_name,
            "capacityId": capacity_id,
        }
        resp = self._post("/workspaces", payload)
        workspace = resp.json()
        console.print(f"[green]✔  Created workspace '{display_name}'.[/green]")
        return workspace

    # ------------------------------------------------------------------
    # Lakehouse
    # ------------------------------------------------------------------

    def create_or_get_lakehouse(self, workspace_id: str, display_name: str = "Observability") -> dict[str, Any]:
        """Create a schema-enabled Lakehouse item in the workspace.

        `enableSchemas=True` provisions the lakehouse with schema support, so Delta
        tables live under `Tables/<schema>/<table>` (the medallion notebooks write to
        the `bronze`, `silver` and `analytics` schemas).
        """
        return self.create_or_get_item(
            workspace_id,
            display_name,
            "Lakehouse",
            creation_payload={"enableSchemas": True},
        )

    # ------------------------------------------------------------------
    # Shortcuts
    # ------------------------------------------------------------------

    def create_shortcut(
        self,
        workspace_id: str,
        lakehouse_id: str,
        shortcut_name: str,
        storage_account_url: str,
        container_name: str,
        connection_id: str,
        sub_path: str = "/",
        parent_path: str = "Files",
    ) -> None:
        """Create an ADLS Gen2 shortcut under `parent_path` in the Lakehouse.

        `parent_path` may be nested (e.g. "Files/appdependencies"); OneLake creates
        the intermediate folder, so the shortcut lands inside a plain lakehouse folder.
        """
        path = f"/workspaces/{workspace_id}/items/{lakehouse_id}/shortcuts"

        # Check for an existing shortcut with the same name at the same parent path.
        try:
            resp = self._get(path)
            existing = resp.json().get("value", [])
            for sc in existing:
                if sc.get("name") == shortcut_name and sc.get("path") == parent_path:
                    console.print(f"  [yellow]⏭  Shortcut '{parent_path}/{shortcut_name}' already exists — skipping.[/yellow]")
                    return
        except requests.HTTPError:
            # 404 means no shortcuts yet — safe to proceed.
            pass

        # connectionId is mandatory for ADLS Gen2 shortcuts; it references a
        # Fabric cloud connection, even when the connection itself uses the
        # workspace managed identity for storage authentication.
        payload = {
            "path": parent_path,
            "name": shortcut_name,
            "target": {
                "adlsGen2": {
                    "location": storage_account_url,
                    "subpath": sub_path,
                    "connectionId": connection_id,
                },
            },
        }

        try:
            self._post(path, payload)
            console.print(f"  [green]✔  Created shortcut '{parent_path}/{shortcut_name}' → {container_name}.[/green]")
        except requests.HTTPError as exc:
            console.print(f"  [red]✖  Failed to create shortcut '{parent_path}/{shortcut_name}': {exc}[/red]")
            raise

    # ------------------------------------------------------------------
    # Notebooks
    # ------------------------------------------------------------------

    def import_notebooks(
        self,
        workspace_id: str,
        notebooks_dir: pathlib.Path,
        lakehouse_id: str | None = None,
        lakehouse_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Import all .ipynb notebooks from a directory.

        When a lakehouse is supplied, each notebook is bound to it as its default
        lakehouse so the medallion cells resolve relative `Tables/…` / `Files/…`
        paths against the freshly created lakehouse.
        """
        results: list[dict[str, Any]] = []
        if not notebooks_dir.is_dir():
            console.print(f"[yellow]⚠  Notebooks directory not found: {notebooks_dir}[/yellow]")
            return results

        notebook_files = sorted(notebooks_dir.glob("*.ipynb"))
        if not notebook_files:
            console.print("[yellow]⚠  No .ipynb files found.[/yellow]")
            return results

        for nb_path in notebook_files:
            display_name = nb_path.stem
            raw_content = nb_path.read_bytes()

            if lakehouse_id:
                nb_json = json.loads(raw_content)
                nb_meta = nb_json.setdefault("metadata", {})
                nb_meta.setdefault("dependencies", {})["lakehouse"] = {
                    "default_lakehouse": lakehouse_id,
                    "default_lakehouse_name": lakehouse_name,
                    "default_lakehouse_workspace_id": workspace_id,
                    "known_lakehouses": [{"id": lakehouse_id}],
                }
                raw_content = json.dumps(nb_json).encode("utf-8")

            encoded = base64.b64encode(raw_content).decode("utf-8")

            definition = {
                "format": "ipynb",
                "parts": [
                    {
                        "path": "artifact.content.ipynb",
                        "payload": encoded,
                        "payloadType": "InlineBase64",
                    }
                ],
            }

            item = self.create_or_update_notebook(
                workspace_id,
                display_name,
                definition=definition,
                description=f"Imported from {nb_path.name}",
            )
            results.append(item)

        return results

    # ------------------------------------------------------------------
    # Pipelines
    # ------------------------------------------------------------------

    @staticmethod
    def _pipeline_references(definition: dict[str, Any]) -> set[str]:
        """Return the names of pipelines referenced via invoke/execute activities."""
        refs: set[str] = set()
        activities = definition.get("properties", {}).get("activities", [])
        for act in activities:
            act_type = act.get("type")
            tp = act.get("typeProperties", {})
            if act_type == "ExecutePipeline":
                ref = tp.get("pipeline", {}).get("referenceName")
                if ref:
                    refs.add(ref)
            elif act_type == "InvokePipeline":
                # New Invoke pipeline activity references the target by pipelineId,
                # which the templates carry as the target pipeline's display name.
                ref = tp.get("pipelineId")
                if ref:
                    refs.add(ref)
        return refs

    def _resolve_item_id(self, workspace_id: str, display_name: str, item_type: str) -> str | None:
        """Return the ID of a workspace item by display name, or None if not found."""
        item = self._find_item(workspace_id, display_name, item_type)
        return item.get("id") if item else None

    def _resolve_pipeline_content(
        self,
        content: dict[str, Any],
        workspace_id: str,
        notebook_map: dict[str, str],
        pipeline_map: dict[str, str],
        pipeline_connection_id: str | None = None,
    ) -> dict[str, Any]:
        """Inject workspace/notebook/pipeline GUIDs into a pipeline definition.

        Fabric requires TridentNotebook activities to carry a real workspaceId and
        notebookId (GUID). The new InvokePipeline activity targets a pipeline by
        workspaceId + pipelineId (GUID) and needs a connection. Legacy
        ExecutePipeline references point at a pipeline GUID. The templates reference
        notebooks and pipelines by display name, so resolve those to the IDs
        assigned when the items were created.
        """
        activities = content.get("properties", {}).get("activities", [])
        for act in activities:
            act_type = act.get("type")
            tp = act.setdefault("typeProperties", {})

            if act_type == "TridentNotebook":
                tp["workspaceId"] = workspace_id
                nb_ref = tp.get("notebookId")
                nb_id = notebook_map.get(nb_ref) or self._resolve_item_id(
                    workspace_id, nb_ref, "Notebook"
                )
                if nb_id:
                    tp["notebookId"] = nb_id
                else:
                    console.print(f"  [red]✖  Notebook '{nb_ref}' not found in workspace.[/red]")

            elif act_type == "ExecutePipeline":
                ref = tp.get("pipeline", {})
                pl_ref = ref.get("referenceName")
                if pl_ref in pipeline_map:
                    ref["referenceName"] = pipeline_map[pl_ref]

            elif act_type == "InvokePipeline":
                tp["workspaceId"] = workspace_id
                pl_ref = tp.get("pipelineId")
                pl_id = pipeline_map.get(pl_ref) or self._resolve_item_id(
                    workspace_id, pl_ref, "DataPipeline"
                )
                if pl_id:
                    tp["pipelineId"] = pl_id
                else:
                    console.print(f"  [red]✖  Pipeline '{pl_ref}' not found in workspace.[/red]")
                if pipeline_connection_id:
                    act.setdefault("externalReferences", {})["connection"] = pipeline_connection_id
        return content

    def import_pipelines(
        self,
        workspace_id: str,
        pipelines_dir: pathlib.Path,
        pipeline_connection_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Import all pipeline JSON definitions from a directory.

        Pipelines are imported in dependency order so that a pipeline referenced
        by an invoke/execute activity is created before the pipeline that calls it.
        """
        results: list[dict[str, Any]] = []
        if not pipelines_dir.is_dir():
            console.print(f"[yellow]⚠  Pipelines directory not found: {pipelines_dir}[/yellow]")
            return results

        pipeline_files = sorted(pipelines_dir.glob("*.json"))
        if not pipeline_files:
            console.print("[yellow]⚠  No pipeline .json files found.[/yellow]")
            return results

        # Map notebook display names to the GUIDs assigned at import time.
        notebook_map = {
            nb.get("displayName"): nb.get("id")
            for nb in self._list_items(workspace_id, "Notebook")
            if nb.get("id")
        }
        # Pipeline GUIDs are resolved as each pipeline is created (dependency order).
        pipeline_map: dict[str, str] = {}

        # Parse each file: the item display name must match the internal pipeline
        # name so ExecutePipeline referenceName values resolve inside Fabric.
        parsed: dict[str, dict[str, Any]] = {}
        for pl_path in pipeline_files:
            content = json.loads(pl_path.read_bytes())
            name = content.get("name", pl_path.stem)
            parsed[name] = {
                "path": pl_path,
                "content": content,
                "refs": self._pipeline_references(content),
            }

        for name in self._topological_order(parsed):
            info = parsed[name]
            pl_path = info["path"]
            resolved = self._resolve_pipeline_content(
                info["content"], workspace_id, notebook_map, pipeline_map, pipeline_connection_id
            )
            encoded = base64.b64encode(json.dumps(resolved).encode("utf-8")).decode("utf-8")

            definition = {
                "parts": [
                    {
                        "path": "pipeline-content.json",
                        "payload": encoded,
                        "payloadType": "InlineBase64",
                    }
                ],
            }

            item = self.create_or_get_item(
                workspace_id,
                name,
                "DataPipeline",
                definition=definition,
                description=f"Imported from {pl_path.name}",
            )
            results.append(item)

            # Record this pipeline's GUID so pipelines that invoke it resolve correctly.
            pl_id = item.get("id") or self._resolve_item_id(workspace_id, name, "DataPipeline")
            if pl_id:
                pipeline_map[name] = pl_id

        return results

    @staticmethod
    def _topological_order(parsed: dict[str, dict[str, Any]]) -> list[str]:
        """Order pipeline names so dependencies (referenced pipelines) come first."""
        ordered: list[str] = []
        visited: set[str] = set()

        def visit(name: str, stack: set[str]) -> None:
            if name in visited or name not in parsed:
                return
            if name in stack:
                # Cyclic reference — break to avoid infinite recursion.
                return
            stack.add(name)
            for dep in parsed[name]["refs"]:
                visit(dep, stack)
            stack.discard(name)
            visited.add(name)
            ordered.append(name)

        for name in parsed:
            visit(name, set())
        return ordered


def _print_summary(workspace: dict[str, Any], lakehouse: dict[str, Any], notebooks: list, pipelines: list) -> None:
    """Print a summary table of provisioned resources."""
    table = Table(title="Provisioned Resources", show_lines=True)
    table.add_column("Resource", style="bold")
    table.add_column("Name")
    table.add_column("ID", style="dim")

    table.add_row("Workspace", workspace.get("displayName", "—"), workspace.get("id", "—"))
    table.add_row("Lakehouse", lakehouse.get("displayName", "—"), lakehouse.get("id", "—"))

    for nb in notebooks:
        table.add_row("Notebook", nb.get("displayName", "—"), nb.get("id", "—"))
    for pl in pipelines:
        table.add_row("Pipeline", pl.get("displayName", "—"), pl.get("id", "—"))

    console.print()
    console.print(table)


@click.command()
@click.option(
    "--workspace-name",
    default="Observability-Analytics",
    show_default=True,
    help="Display name for the Fabric workspace.",
)
@click.option(
    "--storage-account-url",
    required=True,
    help="ADLS Gen2 storage account URL (e.g. https://<account>.dfs.core.windows.net).",
)
@click.option(
    "--capacity-id",
    required=True,
    help="Fabric capacity ID to assign the workspace to.",
)
@click.option(
    "--connection-id",
    required=True,
    help="Fabric cloud connection ID (GUID) bound to the ADLS Gen2 account for shortcuts.",
)
@click.option(
    "--pipeline-connection-id",
    default=None,
    help="Fabric connection ID (GUID) for the new Invoke pipeline activity. If omitted, "
         "the activity keeps its placeholder connection and must be wired up in the portal.",
)
def main(
    workspace_name: str,
    storage_account_url: str,
    capacity_id: str,
    connection_id: str,
    pipeline_connection_id: str | None,
) -> None:
    """Provision a Microsoft Fabric workspace for observability analytics.

    Creates a workspace, Lakehouse, ADLS Gen2 shortcuts, and imports
    notebooks and pipelines from the repository.
    """
    console.rule("[bold blue]Fabric Workspace Setup[/bold blue]")

    try:
        credential = DefaultAzureCredential()
        client = FabricClient(credential)

        # 1. Workspace --------------------------------------------------
        with console.status("Creating workspace…"):
            workspace = client.create_or_get_workspace(workspace_name, capacity_id)
        workspace_id = workspace["id"]

        # 2. Lakehouse ---------------------------------------------------
        with console.status("Creating Lakehouse…"):
            lakehouse = client.create_or_get_lakehouse(workspace_id)
        lakehouse_id = lakehouse.get("id", "")

        # 3. ADLS Gen2 shortcuts -----------------------------------------
        if lakehouse_id:
            with console.status("Creating ADLS Gen2 shortcuts…"):
                # Root-level shortcuts (cost exports + resource metadata).
                for container in ROOT_SHORTCUT_CONTAINERS:
                    client.create_shortcut(
                        workspace_id=workspace_id,
                        lakehouse_id=lakehouse_id,
                        shortcut_name=container,
                        storage_account_url=storage_account_url,
                        container_name=container,
                        connection_id=connection_id,
                        sub_path=f"/{container}",
                    )
                # App telemetry: one plain folder per family, each holding its
                # am-* shortcut (Files/<folder>/am-<folder>).
                for folder, container in NESTED_SHORTCUT_CONTAINERS.items():
                    client.create_shortcut(
                        workspace_id=workspace_id,
                        lakehouse_id=lakehouse_id,
                        shortcut_name=container,
                        storage_account_url=storage_account_url,
                        container_name=container,
                        connection_id=connection_id,
                        sub_path=f"/{container}",
                        parent_path=f"Files/{folder}",
                    )
        else:
            console.print("[yellow]⚠  Lakehouse ID unavailable — skipping shortcuts.[/yellow]")

        # 4. Notebooks ---------------------------------------------------
        with console.status("Importing notebooks…"):
            notebooks = client.import_notebooks(
                workspace_id,
                NOTEBOOKS_DIR,
                lakehouse_id=lakehouse_id or None,
                lakehouse_name=lakehouse.get("displayName", "Observability"),
            )

        # 5. Pipelines ---------------------------------------------------
        with console.status("Importing pipelines…"):
            pipelines = client.import_pipelines(
                workspace_id,
                PIPELINES_DIR,
                pipeline_connection_id=pipeline_connection_id,
            )

        # Summary --------------------------------------------------------
        _print_summary(workspace, lakehouse, notebooks, pipelines)
        console.print("\n[bold green]✔ Workspace setup complete.[/bold green]")

    except requests.HTTPError as exc:
        console.print(f"\n[bold red]✖ Fabric API error:[/bold red] {exc}")
        if exc.response is not None:
            console.print(exc.response.text)
        sys.exit(1)
    except Exception as exc:
        console.print(f"\n[bold red]✖ Unexpected error:[/bold red] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
