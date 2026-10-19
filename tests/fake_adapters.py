"""Test doubles loaded through the ``module:Class`` adapter hook."""

from aibench.adapters.base import AdapterError, Capabilities, ModelAdapter, ModelResponse, Usage


class AlwaysFails(ModelAdapter):
    @property
    def capabilities(self):
        return Capabilities()

    def complete(self, messages, tools, max_output_tokens):
        raise AdapterError("503 upstream overloaded", retryable=True, status=503)


class FakeJudge(ModelAdapter):
    """Returns level 4 with evidence for every criterion it is asked about."""

    @property
    def capabilities(self):
        return Capabilities(vision=True)

    def complete(self, messages, tools, max_output_tokens):
        import json
        import re

        ids = re.findall(r"^- (\w+) \(levels", messages[-1].content, re.M)
        body = {i: {"level": 4, "evidence": f"observed {i}"} for i in ids}
        return ModelResponse(json.dumps(body), [], Usage(10, 10, reported=True), "end_turn", 0.0)
