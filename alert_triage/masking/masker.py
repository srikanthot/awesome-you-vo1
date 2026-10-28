"""PII masking before any AI call, and unmasking of the AI's comment before write-back.

How it works:
1. Fields named in config/pii_fields.yaml are replaced by tokens such as <PERSON_1> or <ACCOUNT_2>.
   The same value always gets the same token, so the model can still see that two transactions
   share a counterparty.
2. Any of those values that also appear inside free text (descriptions, comments) are replaced too.
3. Free text can also be sent to Azure AI Language PII detection (detector hook) once access is in place.

The token map (token -> real value) is sensitive: it stays inside the secure environment (Key Vault / restricted
storage) and is used only to unmask the final comment.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

DEFAULT_RULES = Path(__file__).resolve().parents[2] / "config" / "pii_fields.yaml"
TOKEN_RE = re.compile(r"<([A-Z]+)_(\d+)>")


@dataclass
class TokenMap:
    by_value: dict[tuple[str, str], str] = field(default_factory=dict)  # (category, value) -> token
    by_token: dict[str, str] = field(default_factory=dict)              # token -> value
    counters: dict[str, int] = field(default_factory=dict)

    def token_for(self, category: str, value: str) -> str:
        key = (category, value)
        if key not in self.by_value:
            n = self.counters.get(category, 0) + 1
            self.counters[category] = n
            tok = f"<{category}_{n}>"
            self.by_value[key] = tok
            self.by_token[tok] = value
        return self.by_value[key]

    def to_dict(self) -> dict:
        return dict(self.by_token)


class Masker:
    def __init__(self, rules_path: str | Path = DEFAULT_RULES,
                 detector: Optional[Callable[[str], list[tuple[str, str]]]] = None):
        """detector(text) -> [(category, value), ...] for free text, e.g. Azure AI Language. None = field rules only."""
        r = yaml.safe_load(Path(rules_path).read_text())
        self.categories = {c: [re.compile(p, re.I) for p in pats] for c, pats in r["categories"].items()}
        self.exclude = [re.compile(p, re.I) for p in r.get("exclude", [])]
        self.free_text = [re.compile(p, re.I) for p in r.get("free_text", [])]
        self.detector = detector

    def category_of(self, key: str) -> Optional[str]:
        k = key.replace("-", "_")
        if any(p.search(k) for p in self.exclude):
            return None
        for cat, pats in self.categories.items():
            if any(p.search(k) for p in pats):
                return cat
        return None

    def mask(self, obj: Any) -> tuple[Any, TokenMap]:
        tm = TokenMap()
        masked = self._walk(obj, tm)
        # values found in fields are also replaced wherever they appear inside other text
        values = sorted(((v, t) for (c, v), t in tm.by_value.items() if len(v) >= 4), key=lambda x: -len(x[0]))
        masked = self._replace_in_text(masked, values, tm)
        return masked, tm

    def _walk(self, o: Any, tm: TokenMap, key: str = "") -> Any:
        if isinstance(o, dict):
            return {k: self._walk(v, tm, k) for k, v in o.items()}
        if isinstance(o, list):
            if o and all(isinstance(x, dict) and set(x) >= {"Key", "Value"} for x in o):  # Alessa {Key, Value} records
                return [{**x, "Value": self._walk(x["Value"], tm, str(x["Key"]))} for x in o]
            return [self._walk(v, tm, key) for v in o]
        if o is None or isinstance(o, bool) or o == "":
            return o
        cat = self.category_of(key) if key else None
        if cat:
            return tm.token_for(cat, str(o).strip())
        return o

    def _replace_in_text(self, o: Any, values: list[tuple[str, str]], tm: TokenMap, key: str = "") -> Any:
        if isinstance(o, dict):
            return {k: self._replace_in_text(v, values, tm, k) for k, v in o.items()}
        if isinstance(o, list):
            return [self._replace_in_text(v, values, tm, key) for v in o]
        if isinstance(o, str) and not TOKEN_RE.fullmatch(o):
            for v, t in values:
                if v in o:
                    o = o.replace(v, t)
            if self.detector and any(p.search(key) for p in self.free_text):
                for cat, val in self.detector(o):
                    if val and val in o:
                        o = o.replace(val, tm.token_for(cat, val))
        return o


def unmask(text: str, token_map: dict[str, str]) -> str:
    """Put the real values back into the AI's comment (only for the analyst review / write-back)."""
    return TOKEN_RE.sub(lambda m: token_map.get(m.group(0), m.group(0)), text)
