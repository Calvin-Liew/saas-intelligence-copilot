from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Any

import requests


DEFAULT_SITE_URL = "https://saas-intelligence-copilot-calvi.netlify.app"


@dataclass
class RemoteCheck:
    layer: str
    name: str
    passed: bool
    detail: str


def main() -> None:
    parser = argparse.ArgumentParser(description="Check SaaSScout production reliability through the Netlify path.")
    parser.add_argument("--site-url", default=DEFAULT_SITE_URL, help="Primary Netlify site URL.")
    parser.add_argument("--deploy-url", default="", help="Optional unique Netlify deploy URL.")
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout in seconds.")
    args = parser.parse_args()

    site_url = args.site_url.rstrip("/")
    checks = [
        check_health(site_url, args.timeout),
        check_status(site_url, args.timeout),
        check_analyze(site_url, args.timeout),
    ]
    if args.deploy_url:
        checks.append(check_status(args.deploy_url.rstrip("/"), args.timeout, name="unique deploy status"))

    print("\nSaaSScout Production Monitor")
    print("=" * 34)
    print(f"site={site_url}")
    if args.deploy_url:
        print(f"deploy={args.deploy_url.rstrip('/')}")
    for check in checks:
        status = "PASS" if check.passed else "FAIL"
        print(f"[{status}] {check.layer} / {check.name}: {check.detail}")

    failed = [check for check in checks if not check.passed]
    if failed:
        print("\nResult: FAIL. First failing layer:", failed[0].layer)
        raise SystemExit(1)

    print("\nResult: PASS. Netlify, Render, Chroma, and template analyze path are reachable.")


def check_health(base_url: str, timeout: float) -> RemoteCheck:
    response = _request("GET", f"{base_url}/health", timeout=timeout)
    if isinstance(response, RemoteCheck):
        return response
    passed = response.status_code == 200 and _json(response).get("status") == "ok"
    return RemoteCheck(
        "Netlify/Render",
        "health",
        passed,
        f"status={response.status_code}, body={_short_body(response)}",
    )


def check_status(base_url: str, timeout: float, name: str = "status") -> RemoteCheck:
    response = _request("GET", f"{base_url}/api/status", timeout=timeout)
    if isinstance(response, RemoteCheck):
        return response
    if response.status_code in {502, 503, 504}:
        return RemoteCheck("Netlify/Render", name, False, f"status={response.status_code}, body={_short_body(response)}")
    if response.status_code != 200:
        return RemoteCheck("Render", name, False, f"status={response.status_code}, body={_short_body(response)}")

    data = _json(response)
    products = int(data.get("product_count") or 0)
    reviews = int(data.get("review_count") or 0)
    chroma = data.get("chroma") or {}
    enrichment = data.get("enrichment") or {}
    llm = data.get("llm") or {}
    if products < 300 or reviews < 4000:
        return RemoteCheck("Render/data", name, False, f"products={products}, reviews={reviews}")
    if not chroma.get("ready"):
        return RemoteCheck("Chroma", name, False, f"status={chroma.get('status', 'missing')}")
    if int(enrichment.get("factgrid_matches") or 0) < 20 or int(enrichment.get("wikidata_matches") or 0) < 80:
        return RemoteCheck("Render/enrichment", name, False, f"enrichment={enrichment}")

    llm_detail = f"{llm.get('provider', 'unknown')} {llm.get('model', '')} {llm.get('status', '')}".strip()
    return RemoteCheck(
        "Netlify/Render",
        name,
        True,
        (
            f"products={products}, reviews={reviews}, chroma={chroma.get('status')}, "
            f"FactGrid={enrichment.get('factgrid_matches')}, Wikidata={enrichment.get('wikidata_matches')}, "
            f"OSS={enrichment.get('open_source_alternatives')}, llm={llm_detail}"
        ),
    )


def check_analyze(base_url: str, timeout: float) -> RemoteCheck:
    payload = {
        "query": "Compare Zendesk, Zoho Desk, and Freshdesk for support ticketing pain points.",
        "category": "Customer Support",
        "max_monthly_price": None,
        "required_features": ["ticket_creation_and_assignment"],
        "additional_required_features": "",
        "compare_tools": ["Zendesk", "Zoho Desk", "Freshdesk"],
        "additional_tool_names": "",
        "top_k": 3,
        "use_llm": False,
    }
    response = _request("POST", f"{base_url}/api/analyze", json=payload, timeout=timeout)
    if isinstance(response, RemoteCheck):
        return response
    if response.status_code in {502, 503, 504}:
        return RemoteCheck("Netlify/Render", "template analyze", False, f"status={response.status_code}, body={_short_body(response)}")
    if response.status_code != 200:
        return RemoteCheck("analyze", "template analyze", False, f"status={response.status_code}, body={_short_body(response)}")

    data = _json(response)
    evidence_count = len(data.get("evidence_snippets") or [])
    tools_count = len(data.get("recommended_tools") or data.get("comparison_table") or [])
    if not data.get("answer"):
        return RemoteCheck("analyze", "template analyze", False, "missing answer")
    if evidence_count == 0:
        return RemoteCheck("Chroma/analyze", "template analyze", False, "missing review evidence snippets")
    return RemoteCheck(
        "analyze",
        "template analyze",
        True,
        f"confidence={data.get('confidence')}, tools={tools_count}, evidence={evidence_count}, llm={data.get('llm', {}).get('status')}",
    )


def _request(method: str, url: str, **kwargs) -> requests.Response | RemoteCheck:
    try:
        return requests.request(method, url, **kwargs)
    except requests.Timeout as exc:
        return RemoteCheck("Netlify/Render", url, False, f"timeout: {exc}")
    except requests.RequestException as exc:
        return RemoteCheck("Netlify", url, False, f"{type(exc).__name__}: {exc}")


def _json(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
        return payload if isinstance(payload, dict) else {}
    except ValueError:
        return {}


def _short_body(response: requests.Response) -> str:
    text = response.text.strip().replace("\n", " ")
    return text[:220] if text else "<empty>"


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
