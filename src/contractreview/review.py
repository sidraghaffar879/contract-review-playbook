"""Orchestration: segment -> classify -> extract facts -> check against playbook -> redline -> score -> report."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from .fake import responder
from .llm import LLM, get_llm, parse_json
from .rules import check, extract_facts
from .segment import Clause, load_text, segment

CLASSIFY_SYSTEM = ("[task:classify] Identify every playbook topic this contract clause addresses, from: {types}. A clause may cover more than one "
                   "(e.g. termination and auto-renewal). Return JSON {\"clause_types\": [str], \"confidence\": 0-1}; use [\"other\"] if none apply.")
REDLINE_SYSTEM = ("[task:redline] You are commercial counsel. Given a clause, the playbook standard and fallback positions and the issues found, "
                  "propose replacement wording and a one-sentence negotiation note. Return JSON {\"redline\": str, \"negotiation_note\": str}.")


@dataclass
class Finding:
    number: str
    heading: str
    clause_type: str
    status: str            # standard | fallback | deviation | missing
    issues: list[str]
    facts: dict
    risk: int              # weight * severity
    redline: str = ""
    negotiation_note: str = ""
    excerpt: str = ""


@dataclass
class Review:
    document: str
    findings: list[Finding]
    risk_score: int
    max_score: int
    summary: dict = field(default_factory=dict)


class ContractReviewer:
    def __init__(self, playbook: str | Path | None = None, llm: LLM | None = None):
        pb_path = Path(playbook) if playbook else Path(__file__).with_name("playbook.yaml")
        self.playbook = yaml.safe_load(pb_path.read_text())["clauses"]
        self.llm = llm or get_llm(responder)

    def classify(self, c: Clause) -> list[str]:
        out = parse_json(self.llm.complete(CLASSIFY_SYSTEM.replace("{types}", ", ".join(self.playbook)), f"Heading: {c.heading}\n\n{c.text[:1500]}"), {})
        types = out.get("clause_types") or [out.get("clause_type", "other")]
        return [t for t in types if t in self.playbook]

    def redline(self, c: Clause, ctype: str, issues: list[str]) -> tuple[str, str]:
        pb = self.playbook[ctype]
        user = (f"Clause:\n{c.text[:2000]}\n\nStandard position: {pb['standard']}\nFallback: {pb['fallback']}\nIssues:\n" + "\n".join(f"- {i}" for i in issues))
        out = parse_json(self.llm.complete(REDLINE_SYSTEM, user), {})
        return out.get("redline", ""), out.get("negotiation_note", "")

    def review(self, path: str | Path) -> Review:
        text = load_text(path)
        findings: list[Finding] = []
        seen: set[str] = set()
        for c in segment(text):
            for ctype in self.classify(c):
                seen.add(ctype)
                facts = extract_facts(ctype, c.text)
                status, issues = check(ctype, facts, self.playbook[ctype])
                w = self.playbook[ctype]["weight"]
                risk = w * {"standard": 0, "fallback": 1, "deviation": 3}[status]
                f = Finding(c.number, c.heading, ctype, status, issues, facts, risk, excerpt=c.text[:220])
                if status != "standard":
                    f.redline, f.negotiation_note = self.redline(c, ctype, issues)
                findings.append(f)
        for ctype, pb in self.playbook.items():
            if pb.get("required") and ctype not in seen:
                findings.append(Finding("-", ctype.replace("_", " ").title(), ctype, "missing", ["required clause not found"], {}, pb["weight"] * 3,
                                        redline=f"Insert: {pb['standard']}", negotiation_note="Missing clause - insert our standard wording."))
        score = sum(f.risk for f in findings)
        max_score = sum(pb["weight"] * 3 for pb in self.playbook.values())
        summary = {s: sum(1 for f in findings if f.status == s) for s in ("standard", "fallback", "deviation", "missing")}
        return Review(Path(path).name, sorted(findings, key=lambda f: -f.risk), score, max_score, summary)


def to_markdown(r: Review) -> str:
    pct = round(100 * r.risk_score / r.max_score)
    verdict = "LOW" if pct < 20 else "MEDIUM" if pct < 45 else "HIGH"
    lines = [f"# Contract review: {r.document}", "", f"**Risk score: {r.risk_score}/{r.max_score} ({pct}%) – {verdict}**  ",
             f"standard: {r.summary['standard']} · fallback: {r.summary['fallback']} · deviation: {r.summary['deviation']} · missing: {r.summary['missing']}", ""]
    for f in r.findings:
        if f.status == "standard":
            continue
        lines += [f"## {f.number} {f.heading} — {f.clause_type} — **{f.status.upper()}** (risk {f.risk})"]
        lines += [f"- {i}" for i in f.issues]
        if f.redline:
            lines += ["", f"**Proposed redline:** {f.redline}", f"*Negotiation note:* {f.negotiation_note}"]
        lines += [""]
    ok = [f for f in r.findings if f.status == "standard"]
    if ok:
        lines += ["## Clauses at standard position", ", ".join(f"{f.number} {f.heading}" for f in ok)]
    return "\n".join(lines)


def to_json(r: Review) -> str:
    return json.dumps(asdict(r), indent=2, default=str)
