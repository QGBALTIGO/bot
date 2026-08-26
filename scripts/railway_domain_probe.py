from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ENDPOINT = "https://backboard.railway.com/graphql/v2"

SERVICES = [
    {
        "label": "LOGI - bot",
        "project_id": "12dff49a-52fe-4a06-8c0d-ed1a8a97d432",
        "service_id": "e7e04342-4321-44b8-93c1-c6958867facc",
        "environment_id": "3db4a248-8551-437a-8369-b38b902b430f",
    },
    {
        "label": "caring-fascination - bot",
        "project_id": "df195f12-f961-4bd8-afb6-6d28b4f3ee2c",
        "service_id": "996f2862-5af6-409e-94d6-6f0abcb08d6b",
        "environment_id": "0b73fa84-d40f-461b-9931-052cce1dbd85",
    },
]

QUERY = """
query Domains($projectId: String!, $environmentId: String!, $serviceId: String!) {
  domains(projectId: $projectId, environmentId: $environmentId, serviceId: $serviceId)
}
"""


def _token_and_header() -> tuple[str, str]:
    project_token = os.getenv("RAILWAY_TOKEN", "").strip()
    account_token = os.getenv("RAILWAY_API_TOKEN", "").strip()
    if project_token:
        return project_token, "Project-Access-Token"
    if account_token:
        return account_token, "Authorization"
    return "", ""


def _query(token: str, header_name: str, service: dict[str, str]) -> dict:
    payload = json.dumps(
        {
            "query": QUERY,
            "variables": {
                "projectId": service["project_id"],
                "environmentId": service["environment_id"],
                "serviceId": service["service_id"],
            },
        }
    ).encode("utf-8")
    header_value = token if header_name == "Project-Access-Token" else f"Bearer {token}"
    req = Request(
        ENDPOINT,
        data=payload,
        headers={
            header_name: header_value,
            "Content-Type": "application/json",
            "User-Agent": "Baltigo-Railway-Domain-Probe/1.0",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=15) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {"http_error": exc.code, "body": body[:1200]}
    except (URLError, TimeoutError, OSError) as exc:
        return {"network_error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    token, header_name = _token_and_header()
    if not token:
        print("RAILWAY_DOMAIN_PROBE=SKIPPED no RAILWAY_TOKEN/RAILWAY_API_TOKEN GitHub secret configured")
        return 0

    print(f"RAILWAY_DOMAIN_PROBE=AUTH header={header_name}")
    for service in SERVICES:
        result = _query(token, header_name, service)
        print(f"SERVICE={service['label']}")
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
