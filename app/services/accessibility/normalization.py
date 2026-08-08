from typing import Any

from app.services.accessibility.grouping import component_signature
from app.services.accessibility.rule_catalog import (
    AXE_CORE_VERSION,
    MAX_NODES_PER_RULE,
    PILOT_RULE_BY_ID,
)
from app.services.technical_checks import IssueSignal

IMPACT_SEVERITY = {
    "critical": "high",
    "serious": "high",
    "moderate": "medium",
    "minor": "low",
}


def normalize_axe_result(result: object) -> dict[str, object]:
    """Keep bounded, versioned axe evidence and separate uncertain findings."""
    payload = result if isinstance(result, dict) else {}
    return {
        "engine": "axe-core",
        "engine_version": str(payload.get("testEngine", {}).get("version", AXE_CORE_VERSION))
        if isinstance(payload.get("testEngine"), dict)
        else AXE_CORE_VERSION,
        "violations": _normalize_findings(payload.get("violations")),
        "incomplete": _normalize_findings(payload.get("incomplete")),
    }


def accessibility_issue_signals(evidence: dict[str, object]) -> list[IssueSignal]:
    signals: list[IssueSignal] = []
    violations = evidence.get("violations")
    if not isinstance(violations, list):
        return signals
    for finding in violations:
        if not isinstance(finding, dict):
            continue
        rule_id = finding.get("rule_id")
        if not isinstance(rule_id, str) or rule_id not in PILOT_RULE_BY_ID:
            continue
        rule = PILOT_RULE_BY_ID[rule_id]
        node_count = int(finding.get("node_count", 0))
        nodes = finding.get("nodes")
        first_node = nodes[0] if isinstance(nodes, list) and nodes else None
        target = first_node.get("target") if isinstance(first_node, dict) else None
        signals.append(
            IssueSignal(
                issue_type=f"accessibility_{rule_id.replace('-', '_')}",
                category="accessibility",
                severity=IMPACT_SEVERITY.get(str(finding.get("impact")), rule.severity),
                confidence="high",
                title=rule.title,
                description=(
                    f"De automatische browsercontrole vond dit op {node_count} element(en)."
                ),
                recommended_action=rule.action,
                evidence={
                    "accessibility": {
                        "engine": evidence.get("engine"),
                        "engine_version": evidence.get("engine_version"),
                        "component_signature": component_signature(rule_id, target),
                        **finding,
                    }
                },
            )
        )
    return signals


def _normalize_findings(value: Any) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    findings: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict) or item.get("id") not in PILOT_RULE_BY_ID:
            continue
        raw_nodes = item.get("nodes") if isinstance(item.get("nodes"), list) else []
        nodes = []
        for node in raw_nodes[:MAX_NODES_PER_RULE]:
            if not isinstance(node, dict):
                continue
            target = node.get("target")
            nodes.append(
                {
                    "target": [str(part)[:500] for part in target[:3]]
                    if isinstance(target, list)
                    else [],
                    "html": str(node.get("html", ""))[:1_000],
                    "failure_summary": str(node.get("failureSummary", ""))[:1_000],
                }
            )
        findings.append(
            {
                "rule_id": str(item["id"]),
                "impact": str(item.get("impact") or "unknown"),
                "help": str(item.get("help") or "")[:500],
                "help_url": str(item.get("helpUrl") or "")[:1_000],
                "tags": [str(tag)[:100] for tag in item.get("tags", [])[:20]]
                if isinstance(item.get("tags"), list)
                else [],
                "node_count": len(raw_nodes),
                "nodes": nodes,
            }
        )
    return findings
