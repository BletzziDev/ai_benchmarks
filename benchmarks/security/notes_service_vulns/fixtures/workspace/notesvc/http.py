"""A minimal request/response abstraction so the service can be exercised in-process."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Request:
    method: str
    path: str
    query: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    body: dict[str, Any] | None = None


@dataclass
class Response:
    status: int
    body: Any = None
    headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def json(cls, status: int, payload: Any) -> "Response":
        return cls(status, payload, {"Content-Type": "application/json"})

    @classmethod
    def html(cls, status: int, markup: str) -> "Response":
        return cls(status, markup, {"Content-Type": "text/html; charset=utf-8"})

    @classmethod
    def error(cls, status: int, message: str) -> "Response":
        return cls.json(status, {"error": message})

    def text(self) -> str:
        if isinstance(self.body, bytes):
            return self.body.decode("utf-8", "replace")
        if isinstance(self.body, str):
            return self.body
        return json.dumps(self.body)
