"""Discover Azure resources and create diagnostic settings.

Iterates through all resources in a subscription, identifies those that
support diagnostic settings, and configures them to send logs and metrics
to both a Log Analytics Workspace and a Storage Account.
"""

import argparse
import logging
import sys
from typing import Optional

from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
from azure.identity import DefaultAzureCredential
from azure.mgmt.monitor import MonitorManagementClient
from azure.mgmt.monitor.models import (
    DiagnosticSettingsResource,
    LogSettings,
    MetricSettings,
    RetentionPolicy,
)
from azure.mgmt.resource import ResourceManagementClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
)
logger = logging.getLogger("setup_diagnostic_settings")

DIAGNOSTIC_SETTING_NAME = "observability-platform-diag"

SKIP_RESOURCE_TYPES = frozenset(
    {
        "microsoft.alertsmanagement/smartdetectoralertrules",
        "microsoft.authorization/roleassignments",
        "microsoft.authorization/roledefinitions",
        "microsoft.compute/disks",
        "microsoft.compute/images",
        "microsoft.compute/snapshots",
        "microsoft.managedidentity/userassignedidentities",
        "microsoft.network/networkinterfaces",
        "microsoft.network/networksecuritygroups/securityrules",
        "microsoft.network/publicipaddresses",
        "microsoft.network/virtualnetworks/subnets",
        "microsoft.portal/dashboards",
        "microsoft.resources/templatespecs",
        "microsoft.resources/templatespecs/versions",
        "microsoft.security/autoProvisioningSettings",
    }
)


def get_diagnostic_categories(
    monitor_client: MonitorManagementClient,
    resource_id: str,
) -> tuple[list[str], list[str]]:
    """Retrieve supported log and metric categories for a resource."""
    log_categories: list[str] = []
    metric_categories: list[str] = []

    try:
        result = monitor_client.diagnostic_settings_category.list(resource_id)
        for category in result.value or []:
            if category.category_type == "Logs":
                log_categories.append(category.name)
            elif category.category_type == "Metrics":
                metric_categories.append(category.name)
    except (HttpResponseError, ResourceNotFoundError):
        pass

    return log_categories, metric_categories


def create_diagnostic_setting(
    monitor_client: MonitorManagementClient,
    resource_id: str,
    workspace_id: str,
    storage_account_id: str,
    log_categories: list[str],
    metric_categories: list[str],
    dry_run: bool = False,
) -> Optional[str]:
    """Create a diagnostic setting on a resource."""
    retention = RetentionPolicy(enabled=True, days=90)

    log_settings = [
        LogSettings(
            category=cat,
            enabled=True,
            retention_policy=retention,
        )
        for cat in log_categories
    ]

    metric_settings = [
        MetricSettings(
            category=cat,
            enabled=True,
            retention_policy=retention,
        )
        for cat in metric_categories
    ]

    if not log_settings and not metric_settings:
        return None

    parameters = DiagnosticSettingsResource(
        workspace_id=workspace_id,
        storage_account_id=storage_account_id,
        logs=log_settings,
        metrics=metric_settings,
    )

    if dry_run:
        log_count = len(log_settings)
        metric_count = len(metric_settings)
        logger.info(
            "[DRY RUN] Would create diagnostic setting on %s "
            "(%d log categories, %d metric categories)",
            resource_id,
            log_count,
            metric_count,
        )
        return DIAGNOSTIC_SETTING_NAME

    result = monitor_client.diagnostic_settings.create_or_update(
        resource_uri=resource_id,
        name=DIAGNOSTIC_SETTING_NAME,
        parameters=parameters,
    )
    return result.name


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create diagnostic settings for all supported resources."
    )
    parser.add_argument(
        "--subscription-id",
        required=True,
        help="Azure subscription ID.",
    )
    parser.add_argument(
        "--workspace-id",
        required=True,
        help="Full resource ID of the Log Analytics workspace.",
    )
    parser.add_argument(
        "--storage-account-id",
        required=True,
        help="Full resource ID of the destination storage account.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview changes without applying them.",
    )
    args = parser.parse_args()

    credential = DefaultAzureCredential()
    resource_client = ResourceManagementClient(credential, args.subscription_id)
    monitor_client = MonitorManagementClient(credential, args.subscription_id)

    created = 0
    skipped = 0
    failed = 0

    logger.info(
        "Discovering resources in subscription %s ...", args.subscription_id
    )

    for resource in resource_client.resources.list():
        resource_type = (resource.type or "").lower()

        if resource_type in SKIP_RESOURCE_TYPES:
            skipped += 1
            continue

        log_cats, metric_cats = get_diagnostic_categories(
            monitor_client, resource.id
        )

        if not log_cats and not metric_cats:
            logger.debug(
                "No diagnostic categories for %s (%s)", resource.name, resource_type
            )
            skipped += 1
            continue

        try:
            result = create_diagnostic_setting(
                monitor_client,
                resource.id,
                args.workspace_id,
                args.storage_account_id,
                log_cats,
                metric_cats,
                dry_run=args.dry_run,
            )
            if result:
                logger.info(
                    "Configured diagnostics for %s (%s)", resource.name, resource_type
                )
                created += 1
            else:
                skipped += 1
        except HttpResponseError as exc:
            logger.warning(
                "Failed to configure diagnostics for %s (%s): %s",
                resource.name,
                resource_type,
                exc.message,
            )
            failed += 1
        except Exception:
            logger.exception(
                "Unexpected error configuring diagnostics for %s (%s)",
                resource.name,
                resource_type,
            )
            failed += 1

    mode = "[DRY RUN] " if args.dry_run else ""
    logger.info(
        "%sDiagnostic settings complete. Created: %d, Skipped: %d, Failed: %d",
        mode,
        created,
        skipped,
        failed,
    )


if __name__ == "__main__":
    sys.exit(main() or 0)
