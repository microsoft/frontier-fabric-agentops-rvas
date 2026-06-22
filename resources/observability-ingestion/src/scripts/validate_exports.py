"""Validate export data in ADLS Gen2 storage containers.

Connects to an ADLS Gen2 storage account and reports on the files
present in each observability container (costs, metrics, logs, metadata,
diagnostics). Shows file count, total size, latest timestamp, and a
sample Parquet schema when available.
"""

import argparse
import io
import sys
from datetime import datetime, timezone

import pyarrow.parquet as pq
from azure.identity import DefaultAzureCredential
from azure.storage.filedatalake import DataLakeServiceClient
from rich.console import Console
from rich.table import Table

CONTAINERS = ["costs", "metrics", "logs", "metadata", "diagnostics"]

console = Console()


def sizeof_fmt(num_bytes: float) -> str:
    """Format byte count as human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:,.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:,.1f} PB"


def list_files_recursive(
    service_client: DataLakeServiceClient,
    container: str,
) -> list[dict]:
    """List all files in a container recursively."""
    files = []
    try:
        fs_client = service_client.get_file_system_client(container)
        paths = fs_client.get_paths(recursive=True)
        for path in paths:
            if not path.is_directory:
                files.append(
                    {
                        "name": path.name,
                        "size": path.content_length or 0,
                        "last_modified": path.last_modified,
                    }
                )
    except Exception as exc:
        console.print(f"[yellow]Warning:[/] Could not list {container}: {exc}")
    return files


def read_parquet_schema(
    service_client: DataLakeServiceClient,
    container: str,
    file_path: str,
) -> str:
    """Read and return the schema of a Parquet file."""
    try:
        fs_client = service_client.get_file_system_client(container)
        file_client = fs_client.get_file_client(file_path)
        download = file_client.download_file()
        data = download.readall()
        pf = pq.ParquetFile(io.BytesIO(data))
        schema = pf.schema_arrow
        fields = [f"{f.name} ({f.type})" for f in schema]
        return ", ".join(fields[:10]) + ("..." if len(fields) > 10 else "")
    except Exception:
        return "N/A"


def validate_container(
    service_client: DataLakeServiceClient,
    container: str,
) -> dict:
    """Validate a single container and return summary statistics."""
    files = list_files_recursive(service_client, container)

    if not files:
        return {
            "container": container,
            "file_count": 0,
            "total_size": "0 B",
            "latest_file": "N/A",
            "latest_modified": "N/A",
            "sample_schema": "N/A",
        }

    total_size = sum(f["size"] for f in files)
    latest = max(files, key=lambda f: f["last_modified"] or datetime.min.replace(tzinfo=timezone.utc))

    latest_modified = (
        latest["last_modified"].strftime("%Y-%m-%d %H:%M:%S UTC")
        if latest["last_modified"]
        else "N/A"
    )

    parquet_files = [f for f in files if f["name"].endswith(".parquet")]
    schema = "N/A"
    if parquet_files:
        schema = read_parquet_schema(
            service_client, container, parquet_files[0]["name"]
        )

    return {
        "container": container,
        "file_count": len(files),
        "total_size": sizeof_fmt(total_size),
        "latest_file": latest["name"].rsplit("/", 1)[-1],
        "latest_modified": latest_modified,
        "sample_schema": schema,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate export data in ADLS Gen2 storage containers."
    )
    parser.add_argument(
        "--storage-account",
        required=True,
        help="ADLS Gen2 storage account name.",
    )
    parser.add_argument(
        "--containers",
        nargs="*",
        default=CONTAINERS,
        help="Containers to validate (default: all).",
    )
    args = parser.parse_args()

    credential = DefaultAzureCredential()
    account_url = f"https://{args.storage_account}.dfs.core.windows.net"
    service_client = DataLakeServiceClient(
        account_url=account_url,
        credential=credential,
    )

    console.print()
    console.rule("[bold blue]ADLS Gen2 Export Validation Report")
    console.print(f"Storage Account: [bold]{args.storage_account}[/]")
    console.print(
        f"Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
    )
    console.print()

    table = Table(title="Container Summary", show_lines=True)
    table.add_column("Container", style="cyan", no_wrap=True)
    table.add_column("Files", justify="right", style="green")
    table.add_column("Total Size", justify="right", style="green")
    table.add_column("Latest File", style="white", max_width=40)
    table.add_column("Last Modified", style="yellow")
    table.add_column("Sample Schema", style="dim", max_width=60)

    for container in args.containers:
        result = validate_container(service_client, container)
        table.add_row(
            result["container"],
            str(result["file_count"]),
            result["total_size"],
            result["latest_file"],
            result["latest_modified"],
            result["sample_schema"],
        )

    console.print(table)
    console.print()

    total_files = 0
    for container in args.containers:
        files = list_files_recursive(service_client, container)
        total_files += len(files)

    if total_files > 0:
        console.print(
            f"[bold green]✓[/] Data landing zone is active with "
            f"{total_files} total files across {len(args.containers)} containers."
        )
    else:
        console.print(
            "[bold yellow]⚠[/] No files found. Run exports or wait for "
            "scheduled pipelines to populate data."
        )
    console.print()


if __name__ == "__main__":
    sys.exit(main() or 0)
