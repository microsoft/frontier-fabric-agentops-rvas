"""Setup script for configuring Cosmos DB mirroring into a Microsoft Fabric
workspace via the Fabric REST API.

Mirrors the *conversations* and *interactions* containers from a Cosmos DB
database into a Fabric MirroredDatabase item so the data is queryable via
Spark and SQL analytics endpoints.

Usage:
    python setup_cosmos_mirroring.py \
        --workspace-id <workspace-guid> \
        --cosmos-account <account-name> \
        --database observability
"""

from __future__ import annotations

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
        cosmos_account: str,
        database: str,
        containers: list[str],
    ) -> dict[str, Any]:
        """Create a MirroredDatabase item for Cosmos DB, or return the existing one.

        Args:
            workspace_id: Target Fabric workspace ID.
            display_name: Display name for the mirrored database item.
            cosmos_account: Cosmos DB account name.
            database: Source Cosmos DB database name.
            containers: List of Cosmos DB container names to mirror.

        Returns:
            The mirrored database item dict.
        """
        existing = self._find_mirrored_database(workspace_id, display_name)
        if existing:
            console.print(f"[yellow]⏭  MirroredDatabase '{display_name}' already exists — skipping creation.[/yellow]")
            return existing

        cosmos_endpoint = f"https://{cosmos_account}.documents.azure.com:443/"

        # Build the mirroring definition with the source connection and
        # the list of containers (tables) to mirror.
        mirroring_definition = {
            "source": {
                "type": "CosmosDb",
                "typeProperties": {
                    "connectionId": None,
                    "cosmosEndpoint": cosmos_endpoint,
                    "databaseName": database,
                },
            },
            "tables": [
                {"name": name, "sourceTableName": name} for name in containers
            ],
        }

        # connectionId is optional when workspace managed identity is used.
        if mirroring_definition["source"]["typeProperties"]["connectionId"] is None:
            del mirroring_definition["source"]["typeProperties"]["connectionId"]

        payload: dict[str, Any] = {
            "displayName": display_name,
            "definition": {
                "mirroringDefinition": json.dumps(mirroring_definition),
            },
        }

        resp = self._post(f"/workspaces/{workspace_id}/mirroredDatabases", payload)

        if resp.status_code == 202:
            console.print(f"[cyan]⏳ MirroredDatabase '{display_name}' creation accepted (async).[/cyan]")
            return {"displayName": display_name}

        item = resp.json()
        console.print(f"[green]✔  Created MirroredDatabase '{display_name}'.[/green]")
        return item

    def configure_mirroring(
        self,
        workspace_id: str,
        mirrored_db_id: str,
        containers: list[str],
    ) -> None:
        """Ensure the desired containers are configured for mirroring.

        Updates the mirroring configuration on an existing MirroredDatabase
        item to include the requested containers.

        Args:
            workspace_id: Fabric workspace ID.
            mirrored_db_id: ID of the MirroredDatabase item.
            containers: Container names to mirror.
        """
        path = f"/workspaces/{workspace_id}/mirroredDatabases/{mirrored_db_id}/mirroring"

        try:
            resp = self._get(path)
            current = resp.json()
            existing_tables = {t.get("sourceTableName") for t in current.get("tables", [])}
            missing = [c for c in containers if c not in existing_tables]
        except requests.HTTPError:
            missing = containers
            current = {}

        if not missing:
            console.print("[yellow]⏭  All containers already configured for mirroring.[/yellow]")
            return

        tables = current.get("tables", [])
        for name in missing:
            tables.append({"name": name, "sourceTableName": name})

        try:
            self._patch(path, {"tables": tables})
            console.print(f"[green]✔  Configured mirroring for containers: {', '.join(missing)}.[/green]")
        except requests.HTTPError as exc:
            console.print(f"[red]✖  Failed to configure mirroring: {exc}[/red]")
            raise

    def start_mirroring(self, workspace_id: str, mirrored_db_id: str) -> None:
        """Start (or confirm) the mirroring process.

        Args:
            workspace_id: Fabric workspace ID.
            mirrored_db_id: ID of the MirroredDatabase item.
        """
        path = f"/workspaces/{workspace_id}/mirroredDatabases/{mirrored_db_id}/mirroring/start"

        try:
            self._post(path)
            console.print("[green]✔  Mirroring started.[/green]")
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 409:
                console.print("[yellow]⏭  Mirroring is already running.[/yellow]")
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
        path = f"/workspaces/{workspace_id}/mirroredDatabases/{mirrored_db_id}/mirroring/status"
        resp = self._get(path)
        return resp.json()


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
    "--database",
    required=True,
    default="observability",
    show_default=True,
    help="Cosmos DB database name to mirror.",
)
def main(workspace_id: str, cosmos_account: str, database: str) -> None:
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
                cosmos_account=cosmos_account,
                database=database,
                containers=CONTAINERS_TO_MIRROR,
            )

        mirrored_db_id = mirrored_db.get("id")

        if not mirrored_db_id:
            console.print("[yellow]⚠  MirroredDatabase ID unavailable (async creation). "
                          "Re-run after the item is provisioned.[/yellow]")
            sys.exit(0)

        # 2. Configure which containers to mirror ------------------------
        with console.status("Configuring containers for mirroring…"):
            client.configure_mirroring(workspace_id, mirrored_db_id, CONTAINERS_TO_MIRROR)

        # 3. Start mirroring ---------------------------------------------
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
