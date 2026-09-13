"""Machine-checkable playbook rules. These run on structured facts extracted from each clause (by the LLM or regex)
so a reviewer can see exactly which parameter tripped."""
from __future__ import annotations

import re

WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12,
            "fourteen": 14, "fifteen": 15, "eighteen": 18, "twenty": 20, "twenty-four": 24, "thirty": 30, "thirty-six": 36, "forty-five": 45,
            "forty-eight": 48, "sixty": 60, "seventy-two": 72, "ninety": 90, "one hundred twenty": 120, "one hundred eighty": 180}


def _num(s: str) -> float | None:
    s = s.lower().strip()
    if s in WORD_NUM:
        return WORD_NUM[s]
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _find(pattern: str, text: str) -> float | None:
    m = re.search(pattern, text, re.I)
    return _num(m.group(1)) if m else None


def extract_facts(clause_type: str, text: str) -> dict:
    """Regex fact extraction; the LLM path returns the same keys. Missing keys mean 'not stated'."""
    t = " ".join(text.split())
    f: dict = {"mutual": bool(re.search(r"\b(each party|either party|both parties|mutual)\b", t, re.I)),
               "one_sided_customer": bool(re.search(r"\b(customer|client|licensee) shall (indemnify|be liable)", t, re.I))}
    if clause_type == "limitation_of_liability":
        f["uncapped"] = bool(re.search(r"\b(unlimited|without limit|no (cap|limit)|not be limited)\b", t, re.I))
        f["cap_months"] = _find(r"(\w+(?:-\w+)?)\s*\(?\d*\)?\s*months?['’]? fees", t)
        if f["cap_months"] is None:
            f["cap_months"] = _find(r"fees paid[^.]{0,60}?(?:preceding|prior)\s+(\w+(?:-\w+)?)\s*\(?\d*\)?\s*months", t)
    elif clause_type == "payment_terms":
        f["net_days"] = _find(r"(?:net|within)\s+(\w+(?:-\w+)?)\s*\(?\d*\)?\s*days", t)
        f["late_interest_pct"] = _find(r"(\d+(?:\.\d+)?)\s*%[^.]{0,40}(?:per month|monthly)", t)
    elif clause_type == "termination":
        f["notice_days"] = _find(r"(\w+(?:-\w+)?)\s*\(?\d*\)?\s*days['’]?\s*(?:prior\s+)?(?:written\s+)?notice", t)
        f["for_convenience"] = bool(re.search(r"for convenience|without cause|for any reason", t, re.I))
    elif clause_type == "auto_renewal":
        f["auto_renews"] = bool(re.search(r"automatically renew", t, re.I))
        f["renewal_term_months"] = _find(r"renew[^.]{0,80}?(\w+(?:-\w+)?)\s*\(?\d*\)?\s*(?:months|month)", t)
        yrs = _find(r"renew[^.]{0,80}?(\w+(?:-\w+)?)\s*\(?\d*\)?\s*(?:years|year)", t)
        if f["renewal_term_months"] is None and yrs:
            f["renewal_term_months"] = yrs * 12
        f["optout_notice_days"] = _find(r"(\w+(?:-\w+)?)\s*\(?\d*\)?\s*days[^.]{0,40}(?:prior to|before)[^.]{0,40}(?:renewal|expir)", t)
    elif clause_type == "governing_law":
        m = re.search(r"laws of (?:the )?([A-Za-z ,]+?)(?:,|\.| and| without)", t, re.I)
        f["jurisdiction"] = m.group(1).strip().lower() if m else None
    elif clause_type == "confidentiality":
        f["survival_years"] = _find(r"(\w+(?:-\w+)?)\s*\(?\d*\)?\s*years", t)
    elif clause_type == "non_compete":
        f["present"] = bool(re.search(r"shall not[^.]{0,80}(compete|engage|solicit)|exclusiv", t, re.I))
    elif clause_type == "data_protection":
        h = _find(r"(\w+(?:-\w+)?)\s*\(?\d*\)?\s*hours", t)
        d = _find(r"(\w+(?:-\w+)?)\s*\(?\d*\)?\s*(?:business |calendar )?days", t)
        f["breach_notice_hours"] = h if h is not None else (d * 24 if d is not None else None)
    return f


def check(clause_type: str, facts: dict, pb: dict) -> tuple[str, list[str]]:
    """Returns (status, issues) where status in standard | fallback | deviation."""
    p = pb["params"]
    issues, level = [], 0  # 0 standard, 1 fallback, 2 deviation

    def dev(msg):
        nonlocal level
        issues.append(msg); level = 2

    def fb(msg):
        nonlocal level
        issues.append(msg); level = max(level, 1)

    if p.get("must_be_mutual") and not facts.get("mutual"):
        (dev if facts.get("one_sided_customer") else fb)("obligation is not expressed as mutual")
    if clause_type == "limitation_of_liability":
        if facts.get("uncapped") and not p["uncapped_allowed"]:
            dev("liability is uncapped")
        cm = facts.get("cap_months")
        if cm is None and not facts.get("uncapped"):
            fb("cap amount not clearly stated")
        elif cm is not None and cm > p["cap_months_max"]:
            dev(f"cap of {cm:g} months' fees exceeds maximum {p['cap_months_max']}")
        elif cm is not None and cm > p["cap_months_min"]:
            fb(f"cap of {cm:g} months' fees above standard {p['cap_months_min']}")
    elif clause_type == "payment_terms":
        nd = facts.get("net_days")
        if nd is not None and nd > p["net_days_max"]:
            dev(f"net {nd:g} days exceeds maximum {p['net_days_max']}")
        elif nd is not None and nd > 30:
            fb(f"net {nd:g} days above standard net 30")
        li = facts.get("late_interest_pct")
        if li is not None and li > p["late_interest_pct_max"]:
            dev(f"late interest {li:g}% per month exceeds {p['late_interest_pct_max']}%")
    elif clause_type == "termination":
        nd = facts.get("notice_days")
        if not facts.get("for_convenience"):
            dev("no termination for convenience")
        if nd is not None and nd > p["notice_days_max"]:
            dev(f"{nd:g} days' notice exceeds maximum {p['notice_days_max']}")
        elif nd is not None and nd > 30:
            fb(f"{nd:g} days' notice above standard 30")
    elif clause_type == "auto_renewal" and facts.get("auto_renews"):
        rt, on = facts.get("renewal_term_months"), facts.get("optout_notice_days")
        if rt is not None and rt > p["renewal_term_months_max"]:
            dev(f"auto-renewal term of {rt:g} months exceeds {p['renewal_term_months_max']}")
        if on is not None and on > p["optout_notice_days_max"]:
            dev(f"opt-out notice of {on:g} days exceeds {p['optout_notice_days_max']}")
        elif on is not None and on > 30:
            fb(f"opt-out notice of {on:g} days above standard 30")
    elif clause_type == "governing_law":
        j = facts.get("jurisdiction") or ""
        if not any(a in j for a in p["allowed_jurisdictions"]):
            dev(f"jurisdiction '{j or 'unstated'}' not in approved list")
        elif not any(a in j for a in ("england", "wales", "london", "difc", "dubai")):
            fb(f"jurisdiction '{j}' is a fallback position")
    elif clause_type == "confidentiality":
        sy = facts.get("survival_years")
        if sy is not None and sy > p["survival_years_max"]:
            dev(f"confidentiality survives {sy:g} years, exceeds {p['survival_years_max']}")
        elif sy is not None and sy > 3:
            fb(f"survival of {sy:g} years above standard 3")
    elif clause_type == "non_compete" and facts.get("present") and not p["allowed"]:
        dev("non-compete / exclusivity obligation present")
    elif clause_type == "data_protection":
        h = facts.get("breach_notice_hours")
        if h is None:
            fb("breach notification timeline not stated")
        elif h > p["breach_notice_hours_max"]:
            dev(f"breach notification in {h:g} hours exceeds {p['breach_notice_hours_max']}")
        elif h > 72:
            fb(f"breach notification in {h:g} hours above standard 72")
    return ["standard", "fallback", "deviation"][level], issues
