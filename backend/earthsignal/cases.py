"""Response Intelligence, step 3: analyst cases with a status workflow and an audit trail (DECISIONS D-025).

Cases are stored in ONE local JSON file (default data/cases/cases.json; not committed). Writes are atomic: a
temporary file is written, then renamed over the old one. There is no external database, no user accounts and
no public alerting. This is a local analyst workflow.

Status workflow (a decision needs a written reason):
    open -> investigating -> confirmed | dismissed | needs_data | escalated
    needs_data -> investigating        escalated -> investigating | confirmed | dismissed
    confirmed | dismissed -> investigating   (reopen; also needs a reason)
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATUSES = ("open", "investigating", "confirmed", "dismissed", "needs_data", "escalated")
TRANSITIONS = {
    "open": {"investigating"},
    "investigating": {"confirmed", "dismissed", "needs_data", "escalated"},
    "needs_data": {"investigating"},
    "escalated": {"investigating", "confirmed", "dismissed"},
    "confirmed": {"investigating"},
    "dismissed": {"investigating"},
}
NEEDS_REASON = {"confirmed", "dismissed", "needs_data", "escalated", "investigating_from_closed"}
STATUS_HELP = {
    "open": "Detected and logged; nobody has looked yet.",
    "investigating": "An analyst is reviewing the evidence.",
    "confirmed": "The analyst judged the event real and noteworthy, based on the evidence.",
    "dismissed": "The analyst judged it not noteworthy, or a data artifact.",
    "needs_data": "More evidence is needed (for example, missing station or gauge data).",
    "escalated": "Flagged for review by a domain expert. Not a public alert.",
}
_lock = threading.Lock()


class CaseError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class CaseStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    def _read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise CaseError("case file is not a list")
        return data

    def _write(self, cases: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".cases-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(cases, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)

    def list(self) -> list[dict[str, Any]]:
        return sorted(self._read(), key=lambda c: c["updated_at"], reverse=True)

    def get(self, case_id: str) -> dict[str, Any]:
        for c in self._read():
            if c["id"] == case_id:
                return c
        raise KeyError(case_id)

    def create(self, event: dict[str, Any], evidence: dict[str, Any], title: str | None = None) -> dict[str, Any]:
        with _lock:
            cases = self._read()
            existing = [c for c in cases if c["event"]["id"] == event["id"]]
            if existing:
                return existing[0]  # one case per event: opening twice returns the same case
            n = 1 + max([int(c["id"].split("-")[1]) for c in cases] or [0])
            now = _now()
            case = {
                "id": f"CASE-{n:04d}",
                "title": (title or f"{'Heat episode' if event['kind'] == 'heat' else 'Extreme rainfall'} {event['start']}")[:120],
                "status": "open",
                "event": event,
                "evidence_snapshot": evidence,
                "notes": [],
                "audit": [{"at": now, "action": "created", "status": "open", "note": "Opened from a detected event."}],
                "created_at": now,
                "updated_at": now,
            }
            cases.append(case)
            self._write(cases)
            return case

    def transition(self, case_id: str, to: str, note: str) -> dict[str, Any]:
        if to not in STATUSES:
            raise CaseError(f"unknown status {to!r}")
        note = (note or "").strip()
        with _lock:
            cases = self._read()
            case = next((c for c in cases if c["id"] == case_id), None)
            if case is None:
                raise KeyError(case_id)
            frm = case["status"]
            if to not in TRANSITIONS[frm]:
                raise CaseError(f"cannot move a case from {frm!r} to {to!r}; allowed: {sorted(TRANSITIONS[frm])}")
            needs = to in NEEDS_REASON or (to == "investigating" and frm in ("confirmed", "dismissed"))
            if needs and len(note) < 5:
                raise CaseError("this decision needs a written reason (at least 5 characters)")
            now = _now()
            case["status"] = to
            case["updated_at"] = now
            case["audit"].append({"at": now, "action": "status", "from": frm, "status": to, "note": note})
            self._write(cases)
            return case

    def add_note(self, case_id: str, text: str) -> dict[str, Any]:
        text = (text or "").strip()
        if not 1 <= len(text) <= 2000:
            raise CaseError("note must be 1-2000 characters")
        with _lock:
            cases = self._read()
            case = next((c for c in cases if c["id"] == case_id), None)
            if case is None:
                raise KeyError(case_id)
            now = _now()
            case["notes"].append({"at": now, "text": text})
            case["audit"].append({"at": now, "action": "note", "status": case["status"], "note": text})
            case["updated_at"] = now
            self._write(cases)
            return case


def brief_markdown(case: dict[str, Any]) -> str:
    """Evidence brief for sharing with a reviewer. Plain text (Markdown), built only from stored fields."""
    e, ev = case["event"], case["evidence_snapshot"]
    lines = [
        f"# {case['id']}: {case['title']}",
        "",
        f"**Status:** {case['status']} ({STATUS_HELP[case['status']]})",
        "",
        "> EarthSignal evidence brief. This is an analyst record built from historical reanalysis data. It is NOT a "
        "forecast, warning or impact assessment, and must not be used as a public alert.",
        "",
        "## Summary",
        ev.get("summary", ""),
        "",
        "## Event",
        f"- Type: {e['kind']} · Grid cell: {e['area']} · Dates: {e['start']} to {e['end']} ({e['days']} day(s))",
        f"- Peak: {e['peak_value']} on {e['peak_date']} · Severity: {e['severity']} {e['severity_unit']} · Rank {e['rank']} of {e['n_events']}",
        f"- Provisional data: {'yes' if e['provisional'] else 'no'}",
        "",
        "## Cross-checks",
    ]
    for c in ev.get("checks", []):
        lines.append(f"- **{c.get('label', c.get('source', 'check'))}**: {c.get('verdict')}. {c.get('detail', '')}")
    lines += ["", "## Method", *[f"- {m}" for m in ev.get("method", [])], "", "## Data", *[f"- {d}" for d in ev.get("data", [])], "", "## Notes"]
    lines += [f"- {n['at']}: {n['text']}" for n in case["notes"]] or ["- (none)"]
    lines += ["", "## Audit trail"]
    for a in case["audit"]:
        frm = f"{a['from']} → " if a.get("from") else ""
        lines.append(f"- {a['at']} · {a['action']} · {frm}{a['status']}" + (f" · {a['note']}" if a.get("note") else ""))
    return "\n".join(lines) + "\n"
