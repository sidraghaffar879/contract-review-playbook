"""Offline responder: keyword clause classification and template redlines."""
from __future__ import annotations

import json
import re

TYPES = [
    ("limitation_of_liability", r"limitation of liability|liability of (each|either) party|aggregate liability|liable for"),
    ("indemnification", r"indemnif"),
    ("payment_terms", r"payment|invoice|fees are due|net \w+ days"),
    ("termination", r"terminat"),
    ("auto_renewal", r"automatically renew|renewal"),
    ("governing_law", r"governing law|governed by the laws"),
    ("confidentiality", r"confidential"),
    ("non_compete", r"non-compete|shall not[^.]{0,80}compete|exclusiv"),
    ("data_protection", r"personal data|data protection|gdpr|pdpl"),
]


def responder(system: str, user: str) -> str:
    if "[task:classify]" in system:
        heading = (re.search(r"Heading: (.*)", user) or re.search(r"$", "")).group(0).lower()
        body = user.lower()
        types = [t for t, pat in TYPES if re.search(pat, heading)]
        if types:  # secondary topics inside the same clause (e.g. auto-renewal inside "Term and Termination")
            types += [t for t, pat in TYPES if t not in types and t in {"auto_renewal", "data_protection"} and re.search(pat, body)]
        else:
            types = [t for t, pat in TYPES if re.search(pat, body)][:1]
        return json.dumps({"clause_types": types or ["other"], "confidence": 0.95 if types else 0.5})
    if "[task:redline]" in system:
        issues = re.findall(r"- (.*)", user.split("Issues:", 1)[1]) if "Issues:" in user else []
        std = (re.search(r"Standard position: (.*)", user) or re.search(r"$", "")).group(0).replace("Standard position: ", "")
        return json.dumps({"redline": f"Replace with our standard position: {std}",
                           "negotiation_note": "Open with the standard position; " + (f"concede to the fallback only if the counterparty pushes back on: {issues[0]}." if issues else "no concession needed.")})
    return "{}"
