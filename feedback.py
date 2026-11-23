"""Active-learning memory, persisted to a local JSON file.

  accepted (global)       strings the user added as missed PII -> proposed everywhere they occur.
                          Global is safe: the worst case is a little extra redaction for the reviewer to reject.
  rejected (per document) strings the user said are NOT personal data. Scoped to ONE document (its content
                          hash), so a reject in one file can never silently hide real PII in another file.
"""
from __future__ import annotations
import hashlib, json, os


def doc_key(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


class Feedback:
    def __init__(self, path: str | None = None):
        self.path = path
        self.doc = ""                                   # current document key
        self.rejected: dict[str, set[str]] = {}
        self.accepted: dict[str, str] = {}
        if path and os.path.exists(path):
            with open(path) as f:
                d = json.load(f)
            self.accepted = dict(d.get("accepted", {}))
            rej = d.get("rejected", {})
            if isinstance(rej, dict):                   # old global-list files are dropped on purpose
                self.rejected = {k: set(v) for k, v in rej.items()}

    def set_doc(self, key: str):
        self.doc = key

    def reject(self, text: str):
        self.rejected.setdefault(self.doc, set()).add(text.casefold().strip())
        self.accepted.pop(text.strip(), None)
        self.save()

    def accept(self, text: str, label: str):
        self.accepted[text.strip()] = label
        self.rejected.get(self.doc, set()).discard(text.casefold().strip())
        self.save()

    def is_rejected(self, text: str) -> bool:
        return text.casefold().strip() in self.rejected.get(self.doc, set())

    def clear(self):
        self.rejected.clear(); self.accepted.clear(); self.save()

    def save(self):
        if self.path:
            with open(self.path, "w") as f:
                json.dump({"accepted": self.accepted,
                           "rejected": {k: sorted(v) for k, v in self.rejected.items()}}, f, indent=2)
