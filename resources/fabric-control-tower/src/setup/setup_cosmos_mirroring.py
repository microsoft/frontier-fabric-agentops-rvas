"""Setup script for configuring Cosmos DB mirroring into a Microsoft Fabric
workspace via the Fabric REST API.

Mirrors the *conversations* and *interactions* containers from a Cosmos DB
database into a Fabric MirroredDatabase item so the data is queryable via
Spark and SQL analytics endpoints.

Usage:
    python setup_cosmos_mirroring.py \
        --workspace-id <workspace-guid> \
        --cosmos-account <account-name> \
        --connection-id <fabric-connection-guid> \
        --database observability
"""

from __future__ import annotations

import base64
import json
import sys
import time
from typing import Any

import click
import requests
from azure.identity import DefaultAzureCredential
from rich.console import Console
from rich.table import Table

FABRIC_API_BASE = "https://api.fabric.microsoft.com/v1"
FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"

CONTAINERS_TO_MIRROR = ["conversations", "interactions"]

console = Console()


class FabricMirroringClient:
    """Client for the Fabric Mirroring REST API."""

    def __init__(self, credential: DefaultAzureCredential) -> None:
        self._credential = credential
        self._token: str | None = None

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _get_access_token(self) -> str:
        """Acquire an access token for the Fabric API."""
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

    def _get(self, path: str) -> requests.Response:
        url = f"{FABRIC_API_BASE}{path}"
        resp = requests.get(url, headers=self._headers, timeout=60)
        resp.raise_for_status()
        return resp

    def _post(self, path: str, payload: dict[str, Any] | None = None) -> requests.Response:
        url = f"{FABRIC_API_BASE}{path}"
        resp = requests.post(url, headers=self._headers, json=payload, timeout=120)
        resp.raise_for_status()
        return resp

    def _patch(self, path: str, payload: dict[str, Any]) -> requests.Response:
        url = f"{FABRIC_API_BASE}{path}"
        resp = requests.patch(url, headers=self._headers, json=payload, timeout=120)
        resp.raise_for_status()
        return resp

    # ------------------------------------------------------------------
    # Idempotent helpers
    # ------------------------------------------------------------------

    def _find_mirrored_database(self, workspace_id: str, display_name: str) -> dict[str, Any] | None:
        """Find an existing MirroredDatabase item in the workspace by name."""
        path = f"/workspaces/{workspace_id}/mirroredDatabases"
        try:
            resp = self._get(path)
            items = resp.json().get("value", [])
            for item in items:
                if item.get("displayName") == display_name:
                    return item
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return None
            raise
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_or_get_mirrored_database(
        self,
        workspace_id: str,
        display_name: str,
        connection_id: str,
        database: str,
        containers: list[str],
    ) -> dict[str, Any]:
        """Create a MirroredDatabase item for Cosmos DB, or return the existing one.

        Args:
            workspace_id: Target Fabric workspace ID.
            display_name: Display name for the mirrored database item.
            connection_id: Fabric cloud connection ID (GUID) bound to the
                Cosmos DB account.
            database: Source Cosmos DB database name.
            containers: List of Cosmos DB container names to mirror.

        Returns:
            The mirrored database item dict.
        """
        existing = self._find_mirrored_database(workspace_id, display_name)
        if existing:
            console.print(f"[yellow]⏭  MirroredDatabase '{display_name}' already exists — skipping creation.[/yellow]")
            return existing

        # Build the mirroring.json definition: a Cosmos DB source bound to a
        # Fabric connection, a Delta target, and the containers to mirror.
        mirroring_json = {
            "properties": {
                "source": {
                    "type": "CosmosDb",
                    "typeProperties": {
                        "connection": connection_id,
                        "database": database,
                    },
                },
                "target": {
                    "type": "MountedRelationalDatabase",
                    "typeProperties": {
                        "defaultSchema": "dbo",
                        "format": "Delta",
                    },
                },
                "mountedTables": [
                    {
                        "source": {
                            "typeProperties": {
                                "schemaName": "dbo",
                                "tableName": name,
                            }
                        }
                    }
                    for name in containers
                ],
            }
        }

        payload_b64 = base64.b64encode(
            json.dumps(mirroring_json).encode("utf-8")
        ).decode("ascii")

        payload: dict[str, Any] = {
            "displayName": display_name,
            "definition": {
                "parts": [
                    {
                        "path": "mirroring.json",
                        "payload": payload_b64,
                        "payloadType": "InlineBase64",
                    }
                ],
            },
        }

        resp = self._post(f"/workspaces/{workspace_id}/mirroredDatabases", payload)

        if resp.status_code == 202:
            console.print(f"[cyan]⏳ MirroredDatabase '{display_name}' creation accepted (async) — polling…[/cyan]")
            return self._wait_for_item_created(workspace_id, display_name)

        item = resp.json()
        console.print(f"[green]✔  Created MirroredDatabase '{display_name}'.[/green]")
        return item

    def _wait_for_item_created(
        self,
        workspace_id: str,
        display_name: str,
        timeout: int = 120,
        poll_interval: int = 5,
    ) -> dict[str, Any]:
        """Poll the workspace until the MirroredDatabase item is provisioned."""
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            existing = self._find_mirrored_database(workspace_id, display_name)
            if existing and existing.get("id"):
                console.print(f"[green]✔  Created MirroredDatabase '{display_name}'.[/green]")
                return existing
            time.sleep(poll_interval)
        console.print("[yellow]⚠  Timed out waiting for MirroredDatabase provisioning.[/yellow]")
        return {"displayName": display_name}

    def start_mirroring(self, workspace_id: str, mirrored_db_id: str) -> None:
        """Start (or confirm) the mirroring process.

        Args:
            workspace_id: Fabric workspace ID.
            mirrored_db_id: ID of the MirroredDatabase item.
        """
        path = f"/workspaces/{workspace_id}/mirroredDatabases/{mirrored_db_id}/startMirroring"

        try:
            self._post(path)
            console.print("[green]✔  Mirroring started.[/green]")
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            body = exc.response.text if exc.response is not None else ""
            if status_code == 409 or "already" in body.lower():
                console.print("[yellow]⏭  Mirroring is already running.[/yellow]")
            elif status_code == 400 and "OperationNotAllowedInCurrentStatus" in body:
                console.print("[yellow]⚠  Mirroring not startable yet (still initializing) — "
                              "re-run the script shortly.[/yellow]")
            else:
                console.print(f"[red]✖  Failed to start mirroring: {exc}[/red]")
                raise

    def get_mirroring_status(self, workspace_id: str, mirrored_db_id: str) -> dict[str, Any]:
        """Return the current mirroring status.

        Args:
            workspace_id: Fabric workspace ID.
            mirrored_db_id: ID of the MirroredDatabase item.

        Returns:
            Status response dict from the Fabric API.
        """
        path = f"/workspaces/{workspace_id}/mirroredDatabases/{mirrored_db_id}/getMirroringStatus"
        resp = self._post(path)
        return resp.json()

    # ------------------------------------------------------------------
    # Notebook connectivity
    # ------------------------------------------------------------------

    def _find_notebook(self, workspace_id: str, display_name: str) -> dict[str, Any] | None:
        """Find a Notebook item in the workspace by display name."""
        resp = self._get(f"/workspaces/{workspace_id}/items?type=Notebook")
        for item in resp.json().get("value", []):
            if item.get("displayName") == display_name:
                return item
        return None

    def _poll_lro(self, operation_url: str, want_result: bool = False) -> dict[str, Any] | None:
        """Poll a Fabric long-running operation until it completes."""
        while True:
            resp = requests.get(operation_url, headers=self._headers, timeout=60)
            resp.raise_for_status()
            status = (resp.json().get("status") or "").lower()
            if status in ("succeeded", "completed"):
                break
            if status == "failed":
                raise RuntimeError(f"Fabric operation failed: {operation_url}")
            time.sleep(3)
        if want_result:
            result = requests.get(operation_url.rstrip("/") + "/result", headers=self._headers, timeout=60)
            result.raise_for_status()
            return result.json()
        return None

    def _get_notebook_definition(self, workspace_id: str, notebook_id: str) -> tuple[str, dict[str, Any]]:
        """Return the (part path, ipynb JSON) of a notebook's definition."""
        resp = self._post(f"/workspaces/{workspace_id}/items/{notebook_id}/getDefinition?format=ipynb")
        if resp.status_code == 202:
            body = self._poll_lro(resp.headers.get("Location"), want_result=True) or {}
        else:
            body = resp.json()
        for part in body.get("definition", {}).get("parts", []):
            if part.get("path", "").endswith(".ipynb"):
                content = base64.b64decode(part["payload"]).decode("utf-8")
                return part["path"], json.loads(content)
        raise RuntimeError("Notebook definition contains no .ipynb part.")

    def _update_notebook_definition(
        self, workspace_id: str, notebook_id: str, part_path: str, notebook_json: dict[str, Any]
    ) -> None:
        """Overwrite a notebook's definition with the given ipynb JSON."""
        encoded = base64.b64encode(json.dumps(notebook_json).encode("utf-8")).decode("ascii")
        payload = {
            "definition": {
                "format": "ipynb",
                "parts": [
                    {"path": part_path, "payload": encoded, "payloadType": "InlineBase64"}
                ],
            }
        }
        resp = self._post(f"/workspaces/{workspace_id}/items/{notebook_id}/updateDefinition", payload)
        if resp.status_code == 202:
            self._poll_lro(resp.headers.get("Location"))

    def attach_mirrored_db_to_notebook(
        self,
        workspace_id: str,
        notebook_name: str,
        mirrored_db_id: str,
        mirrored_db_name: str,
    ) -> None:
        """Give a notebook connectivity to the mirrored database artifact.

        Adds the MirroredDatabase item itself to the notebook's known mirrored
        databases (`dependencies.mirrored_db.known_mirrored_dbs`) — not as a
        lakehouse — while preserving any existing default lakehouse binding.
        """
        notebook = self._find_notebook(workspace_id, notebook_name)
        if not notebook or not notebook.get("id"):
            console.print(f"[yellow]⚠  Notebook '{notebook_name}' not found — skipping mirrored DB attachment.[/yellow]")
            return

        notebook_id = notebook["id"]
        part_path, notebook_json = self._get_notebook_definition(workspace_id, notebook_id)

        dependencies = notebook_json.setdefault("metadata", {}).setdefault("dependencies", {})
        mirrored_dep = dependencies.get("mirrored_db")
        if not isinstance(mirrored_dep, dict):
            mirrored_dep = {}
            dependencies["mirrored_db"] = mirrored_dep
        known = mirrored_dep.setdefault("known_mirrored_dbs", [])
        if not any(k.get("id") == mirrored_db_id for k in known):
            known.append({"id": mirrored_db_id})

        self._update_notebook_definition(workspace_id, notebook_id, part_path, notebook_json)
        console.print(
            f"[green]✔  Attached MirroredDatabase '{mirrored_db_name}' to notebook '{notebook_name}'.[/green]"
        )


def _wait_until_startable(
    client: FabricMirroringClient,
    workspace_id: str,
    mirrored_db_id: str,
    timeout: int = 300,
    poll_interval: int = 10,
) -> str:
    """Poll mirroring status until the item can be started (out of Initializing).

    Returns:
        The last observed status (lowercased). Startable states are
        'initialized'/'stopped'; 'running'/'starting' mean already started.
    """
    ready = {"initialized", "stopped", "running", "starting"}
    start = time.monotonic()
    last = ""
    while time.monotonic() - start < timeout:
        try:
            state = (client.get_mirroring_status(workspace_id, mirrored_db_id).get("status") or "").lower()
        except requests.HTTPError:
            state = ""
        if state and state != last:
            console.print(f"[dim]   Mirroring status: {state}…[/dim]")
            last = state
        if state in ready or state == "failed":
            return state
        time.sleep(poll_interval)
    console.print("[yellow]⚠  Timed out waiting for the mirrored database to initialize.[/yellow]")
    return last


def _wait_for_mirroring_healthy(
    client: FabricMirroringClient,
    workspace_id: str,
    mirrored_db_id: str,
    timeout: int = 120,
    poll_interval: int = 10,
) -> bool:
    """Poll mirroring status until it becomes healthy or timeout is reached.

    Args:
        client: Fabric mirroring client.
        workspace_id: Fabric workspace ID.
        mirrored_db_id: MirroredDatabase item ID.
        timeout: Maximum seconds to wait.
        poll_interval: Seconds between polls.

    Returns:
        True if mirroring reached a healthy state, False on timeout.
    """
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        try:
            status = client.get_mirroring_status(workspace_id, mirrored_db_id)
            state = status.get("status", "").lower()
            if state in ("running", "healthy", "active"):
                console.print(f"[green]✔  Mirroring status: {state}.[/green]")
                return True
            console.print(f"[dim]   Mirroring status: {state} — waiting…[/dim]")
        except requests.HTTPError:
            console.print("[dim]   Status endpoint not ready — waiting…[/dim]")
        time.sleep(poll_interval)
    console.print("[yellow]⚠  Timed out waiting for mirroring to become healthy.[/yellow]")
    return False


def _print_summary(mirrored_db: dict[str, Any], containers: list[str]) -> None:
    """Print a summary table."""
    table = Table(title="Cosmos DB Mirroring Summary", show_lines=True)
    table.add_column("Property", style="bold")
    table.add_column("Value")

    table.add_row("Mirrored Database", mirrored_db.get("displayName", "—"))
    table.add_row("Item ID", mirrored_db.get("id", "—"))
    table.add_row("Mirrored Containers", ", ".join(containers))

    console.print()
    console.print(table)


@click.command()
@click.option(
    "--workspace-id",
    required=True,
    help="Fabric workspace ID (GUID).",
)
@click.option(
    "--cosmos-account",
    required=True,
    help="Cosmos DB account name (without .documents.azure.com).",
)
@click.option(
    "--connection-id",
    required=True,
    help="Fabric cloud connection ID (GUID) bound to the Cosmos DB account.",
)
@click.option(
    "--database",
    required=True,
    default="observability",
    show_default=True,
    help="Cosmos DB database name to mirror.",
)
@click.option(
    "--notebook-name",
    default="04_cosmos_mirroring_transform",
    show_default=True,
    help="Notebook to grant connectivity to the mirrored database.",
)
def main(workspace_id: str, cosmos_account: str, connection_id: str, database: str, notebook_name: str) -> None:
    """Configure Cosmos DB mirroring into a Fabric workspace.

    Creates a MirroredDatabase item, configures mirroring for the
    'conversations' and 'interactions' containers, and starts the
    mirroring process.
    """
    console.rule("[bold blue]Cosmos DB Mirroring Setup[/bold blue]")

    display_name = f"CosmosDB-{database}"

    try:
        credential = DefaultAzureCredential()
        client = FabricMirroringClient(credential)

        # 1. Create or retrieve the MirroredDatabase item ----------------
        with console.status("Creating MirroredDatabase item…"):
            mirrored_db = client.create_or_get_mirrored_database(
                workspace_id=workspace_id,
                display_name=display_name,
                connection_id=connection_id,
                database=database,
                containers=CONTAINERS_TO_MIRROR,
            )

        mirrored_db_id = mirrored_db.get("id")

        if not mirrored_db_id:
            console.print("[yellow]⚠  MirroredDatabase ID unavailable (async creation). "
                          "Re-run after the item is provisioned.[/yellow]")
            sys.exit(0)

        # 1b. Give the transform notebook connectivity to the mirrored DB
        with console.status("Attaching mirrored database to notebook…"):
            client.attach_mirrored_db_to_notebook(
                workspace_id=workspace_id,
                notebook_name=notebook_name,
                mirrored_db_id=mirrored_db_id,
                mirrored_db_name=display_name,
            )

        # 2. Wait until the item finishes initializing ------------------
        with console.status("Waiting for mirrored database to initialize…"):
            state = _wait_until_startable(client, workspace_id, mirrored_db_id)

        # 3. Start mirroring ---------------------------------------------
        if state in ("running", "starting"):
            console.print("[yellow]⏭  Mirroring already running.[/yellow]")
        elif state == "failed":
            console.print("[red]✖  Mirrored database is in a Failed state — check the Fabric portal.[/red]")
            sys.exit(1)
        else:
            with console.status("Starting mirroring…"):
                client.start_mirroring(workspace_id, mirrored_db_id)

        # 4. Wait for healthy status -------------------------------------
        with console.status("Waiting for mirroring to become healthy…"):
            _wait_for_mirroring_healthy(client, workspace_id, mirrored_db_id)

        # Summary --------------------------------------------------------
        _print_summary(mirrored_db, CONTAINERS_TO_MIRROR)
        console.print("\n[bold green]✔ Cosmos DB mirroring setup complete.[/bold green]")

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
