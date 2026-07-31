"""Create (or refresh) the Foundry Prompt Agent at deployment time.

Run by azd as a `postprovision` hook so the agent exists in the Foundry project
before any traffic reaches the app. Idempotent and safe to re-run: it publishes a
new agent version and points 100% of the agent endpoint traffic at it.

Required environment variables (provided by azd from the Bicep outputs):
  AZURE_AI_PROJECT_ENDPOINT  Foundry project endpoint URL.
  AZURE_AI_AGENT_NAME        Name to give the agent.
  AZURE_AI_AGENT_MODEL       Model deployment name (falls back to AZURE_OPENAI_DEPLOYMENT).
"""

import os
import sys
import time

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    AgentEndpointConfig,
    FixedRatioVersionSelectionRule,
    PromptAgentDefinition,
    ProtocolConfiguration,
    ResponsesProtocolConfiguration,
    VersionSelector,
)
from azure.core.exceptions import HttpResponseError
from azure.identity import DefaultAzureCredential

PROJECT_ENDPOINT = os.environ.get("AZURE_AI_PROJECT_ENDPOINT", "")
AGENT_NAME = os.environ.get("AZURE_AI_AGENT_NAME", "observability-agent")
AGENT_MODEL = os.environ.get("AZURE_AI_AGENT_MODEL") or os.environ.get("AZURE_OPENAI_DEPLOYMENT", "")
INSTRUCTIONS = (
    "You are a helpful AI assistant powered by Azure AI Foundry. "
    "You provide clear, accurate, and concise responses."
)


def main() -> int:
    if not PROJECT_ENDPOINT:
        print("AZURE_AI_PROJECT_ENDPOINT not set; skipping agent creation.")
        return 0
    if not AGENT_MODEL:
        print("No model deployment name (AZURE_AI_AGENT_MODEL/AZURE_OPENAI_DEPLOYMENT); cannot create agent.")
        return 1

    credential = DefaultAzureCredential()
    last_error: Exception | None = None

    # RBAC on the freshly provisioned Foundry project may still be propagating.
    for attempt in range(1, 13):
        try:
            with AIProjectClient(
                endpoint=PROJECT_ENDPOINT, credential=credential, allow_preview=True
            ) as client:
                created = client.agents.create_version(
                    agent_name=AGENT_NAME,
                    definition=PromptAgentDefinition(model=AGENT_MODEL, instructions=INSTRUCTIONS),
                )
                endpoint_config = AgentEndpointConfig(
                    version_selector=VersionSelector(
                        version_selection_rules=[
                            FixedRatioVersionSelectionRule(
                                agent_version=created.version, traffic_percentage=100
                            ),
                        ]
                    ),
                    protocol_configuration=ProtocolConfiguration(
                        responses=ResponsesProtocolConfiguration()
                    ),
                )
                client.agents.update_details(agent_name=AGENT_NAME, agent_endpoint=endpoint_config)
                print(
                    f"Foundry agent '{AGENT_NAME}' ready "
                    f"(version {created.version}, model {AGENT_MODEL})."
                )
                return 0
        except HttpResponseError as e:
            last_error = e
            if e.status_code in (401, 403, 404):
                print(f"Attempt {attempt}: Foundry not ready ({e.status_code}); retrying in 15s...")
                time.sleep(15)
                continue
            raise

    print(f"Failed to create the Foundry agent after retries: {last_error}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
