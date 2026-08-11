"""Discover Azure resources and create diagnostic settings.

Iterates through all resources in a subscription, identifies those that
support diagnostic settings, and configures them to send logs and metrics
to both a Log Analytics Workspace and a Storage Account.
"""

import argparse
import json
import logging
import sys
import time
import urllib.error
import urllib.request
from typing import Optional

from azure.core.credentials import AccessToken
from azure.identity import DefaultAzureCredential
from azure.mgmt.resource.resources import ResourceManagementClient

# Diagnostic settings management was removed from azure-mgmt-monitor 7.x, so call ARM REST directly.
ARM_ENDPOINT = "https://management.azure.com"
ARM_SCOPE = "https://management.azure.com/.default"
DIAGNOSTICS_API_VERSION = "2021-05-01-preview"

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


class TokenProvider:
    """Supplies a valid ARM bearer token, refreshing shortly before expiry."""

    def __init__(self, credential: DefaultAzureCredential) -> None:
        self._credential = credential
        self._token: Optional[AccessToken] = None

    def bearer(self) -> str:
        if self._token is None or self._token.expires_on - time.time() < 300:
            self._token = self._credential.get_token(ARM_SCOPE)
        return self._token.token


def _arm_request(
    method: str,
    url: str,
    token: str,
    body: Optional[dict] = None,
) -> dict:
    """Issue an Azure Resource Manager REST request and return the JSON body."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Content-Type", "application/json")

    with urllib.request.urlopen(request) as response:
        raw = response.read()

    return json.loads(raw) if raw else {}


def get_diagnostic_categories(
    token_provider: TokenProvider,
    resource_id: str,
) -> tuple[list[str], list[str]]:
    """Retrieve supported log and metric categories for a resource."""
    log_categories: list[str] = []
    metric_categories: list[str] = []

    url = (
        f"{ARM_ENDPOINT}{resource_id}/providers/Microsoft.Insights"
        f"/diagnosticSettingsCategories?api-version={DIAGNOSTICS_API_VERSION}"
    )

    try:
        result = _arm_request("GET", url, token_provider.bearer())
    except urllib.error.HTTPError:
        return log_categories, metric_categories

    for category in result.get("value", []):
        name = category.get("name")
        category_type = (category.get("properties") or {}).get("categoryType")
        if category_type == "Logs":
            log_categories.append(name)
        elif category_type == "Metrics":
            metric_categories.append(name)

    return log_categories, metric_categories


def create_diagnostic_setting(
    token_provider: TokenProvider,
    resource_id: str,
    workspace_id: str,
    storage_account_id: str,
    log_categories: list[str],
    metric_categories: list[str],
    dry_run: bool = False,
) -> Optional[str]:
    """Create a diagnostic setting on a resource."""
    # Retention is no longer accepted on new diagnostic settings; use destination retention instead.
    log_settings = [{"category": cat, "enabled": True} for cat in log_categories]
    metric_settings = [{"category": cat, "enabled": True} for cat in metric_categories]

    if not log_settings and not metric_settings:
        return None

    if dry_run:
        logger.info(
            "[DRY RUN] Would create diagnostic setting on %s "
            "(%d log categories, %d metric categories)",
            resource_id,
            len(log_settings),
            len(metric_settings),
        )
        return DIAGNOSTIC_SETTING_NAME

    body = {
        "properties": {
            "workspaceId": workspace_id,
            "storageAccountId": storage_account_id,
            "logs": log_settings,
            "metrics": metric_settings,
        }
    }
    url = (
        f"{ARM_ENDPOINT}{resource_id}/providers/Microsoft.Insights"
        f"/diagnosticSettings/{DIAGNOSTIC_SETTING_NAME}"
        f"?api-version={DIAGNOSTICS_API_VERSION}"
    )
    _arm_request("PUT", url, token_provider.bearer(), body)
    return DIAGNOSTIC_SETTING_NAME


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
    token_provider = TokenProvider(credential)

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
            token_provider, resource.id
        )

        if not log_cats and not metric_cats:
            logger.debug(
                "No diagnostic categories for %s (%s)", resource.name, resource_type
            )
            skipped += 1
            continue

        try:
            result = create_diagnostic_setting(
                token_provider,
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
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            logger.warning(
                "Failed to configure diagnostics for %s (%s): %s",
                resource.name,
                resource_type,
                detail,
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
