"""Renderer class hierarchy and factory."""

from __future__ import annotations

from typing import Any

from ledgerly.interfaces import IRenderer


class TextLineFormatter:
    """Formats a single labelled amount for the text format."""

    def __init__(self, width: int = 22) -> None:
        self.width = width

    def format(self, label: str, value: float) -> str:
        return f"{label}: {value:,.2f}"


class TextRenderer(IRenderer):
    """Renders a report model as text."""

    def __init__(self, formatter: TextLineFormatter | None = None) -> None:
        self.formatter = formatter or TextLineFormatter()

    def render_header(self, model: dict[str, Any]) -> str:
        return str(model.get("title", ""))

    def render_rows(self, model: dict[str, Any]) -> list[str]:
        return [self.formatter.format(k, v) for k, v in model.get("rows", [])]

    def render_footer(self, model: dict[str, Any]) -> str:
        return ""

    def render(self, model: dict[str, Any]) -> str:
        parts = [self.render_header(model), *self.render_rows(model), self.render_footer(model)]
        return "\n".join(p for p in parts if p)

class MarkdownLineFormatter:
    """Formats a single labelled amount for the markdown format."""

    def __init__(self, width: int = 22) -> None:
        self.width = width

    def format(self, label: str, value: float) -> str:
        return f"{label}: {value:,.2f}"


class MarkdownRenderer(IRenderer):
    """Renders a report model as markdown."""

    def __init__(self, formatter: MarkdownLineFormatter | None = None) -> None:
        self.formatter = formatter or MarkdownLineFormatter()

    def render_header(self, model: dict[str, Any]) -> str:
        return str(model.get("title", ""))

    def render_rows(self, model: dict[str, Any]) -> list[str]:
        return [self.formatter.format(k, v) for k, v in model.get("rows", [])]

    def render_footer(self, model: dict[str, Any]) -> str:
        return ""

    def render(self, model: dict[str, Any]) -> str:
        parts = [self.render_header(model), *self.render_rows(model), self.render_footer(model)]
        return "\n".join(p for p in parts if p)

class CsvLineFormatter:
    """Formats a single labelled amount for the csv format."""

    def __init__(self, width: int = 22) -> None:
        self.width = width

    def format(self, label: str, value: float) -> str:
        return f"{label}: {value:,.2f}"


class CsvRenderer(IRenderer):
    """Renders a report model as csv."""

    def __init__(self, formatter: CsvLineFormatter | None = None) -> None:
        self.formatter = formatter or CsvLineFormatter()

    def render_header(self, model: dict[str, Any]) -> str:
        return str(model.get("title", ""))

    def render_rows(self, model: dict[str, Any]) -> list[str]:
        return [self.formatter.format(k, v) for k, v in model.get("rows", [])]

    def render_footer(self, model: dict[str, Any]) -> str:
        return ""

    def render(self, model: dict[str, Any]) -> str:
        parts = [self.render_header(model), *self.render_rows(model), self.render_footer(model)]
        return "\n".join(p for p in parts if p)

class HtmlLineFormatter:
    """Formats a single labelled amount for the html format."""

    def __init__(self, width: int = 22) -> None:
        self.width = width

    def format(self, label: str, value: float) -> str:
        return f"{label}: {value:,.2f}"


class HtmlRenderer(IRenderer):
    """Renders a report model as html."""

    def __init__(self, formatter: HtmlLineFormatter | None = None) -> None:
        self.formatter = formatter or HtmlLineFormatter()

    def render_header(self, model: dict[str, Any]) -> str:
        return str(model.get("title", ""))

    def render_rows(self, model: dict[str, Any]) -> list[str]:
        return [self.formatter.format(k, v) for k, v in model.get("rows", [])]

    def render_footer(self, model: dict[str, Any]) -> str:
        return ""

    def render(self, model: dict[str, Any]) -> str:
        parts = [self.render_header(model), *self.render_rows(model), self.render_footer(model)]
        return "\n".join(p for p in parts if p)

class JsonLineFormatter:
    """Formats a single labelled amount for the json format."""

    def __init__(self, width: int = 22) -> None:
        self.width = width

    def format(self, label: str, value: float) -> str:
        return f"{label}: {value:,.2f}"


class JsonRenderer(IRenderer):
    """Renders a report model as json."""

    def __init__(self, formatter: JsonLineFormatter | None = None) -> None:
        self.formatter = formatter or JsonLineFormatter()

    def render_header(self, model: dict[str, Any]) -> str:
        return str(model.get("title", ""))

    def render_rows(self, model: dict[str, Any]) -> list[str]:
        return [self.formatter.format(k, v) for k, v in model.get("rows", [])]

    def render_footer(self, model: dict[str, Any]) -> str:
        return ""

    def render(self, model: dict[str, Any]) -> str:
        parts = [self.render_header(model), *self.render_rows(model), self.render_footer(model)]
        return "\n".join(p for p in parts if p)


class RendererFactory:
    _renderers = {"text": TextRenderer, "markdown": MarkdownRenderer, "csv": CsvRenderer, "html": HtmlRenderer,
                  "json": JsonRenderer}

    @classmethod
    def create(cls, fmt: str) -> IRenderer:
        if fmt not in cls._renderers:
            raise ValueError("bad format")
        return cls._renderers[fmt]()
