import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from aibench.adapters import create_adapter
from aibench.adapters.anthropic_adapter import AnthropicAdapter
from aibench.adapters.base import Message, ToolCall, ToolSpec, Usage
from aibench.core.config import ModelConfig, Pricing


class FakeServer:
    """Minimal HTTP server replying with queued JSON bodies and recording requests."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append({"path": self.path, "body": body, "headers": dict(self.headers)})
                status, reply = outer.replies.pop(0)
                data = json.dumps(reply).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()


TOOLS = [ToolSpec("read_file", "read", {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]})]


def conversation():
    return [
        Message("system", "sys"), Message("user", "task"),
        Message("assistant", "looking", tool_calls=[ToolCall("t1", "read_file", {"path": "a"}),
                                                    ToolCall("t2", "read_file", {"path": "b"})]),
        Message("tool", "A", tool_call_id="t1"), Message("tool", "B", tool_call_id="t2", is_error=True),
    ]


def test_anthropic_wire_groups_tool_results():
    system, wire = AnthropicAdapter.to_wire(conversation())
    assert system == "sys"
    assert [m["role"] for m in wire] == ["user", "assistant", "user"]
    assert [b["type"] for b in wire[1]["content"]] == ["text", "tool_use", "tool_use"]
    assert [b["tool_use_id"] for b in wire[2]["content"]] == ["t1", "t2"] and wire[2]["content"][1]["is_error"]


def test_anthropic_adapter_against_fake_server(monkeypatch):
    pytest.importorskip("anthropic")
    srv = FakeServer([(200, {
        "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-test",
        "content": [{"type": "text", "text": "ok"}, {"type": "tool_use", "id": "toolu_1", "name": "read_file", "input": {"path": "x"}}],
        "stop_reason": "tool_use", "stop_sequence": None,
        "usage": {"input_tokens": 100, "output_tokens": 20, "cache_read_input_tokens": 50},
    })])
    monkeypatch.setenv("FAKE_KEY", "k")
    cfg = ModelConfig(adapter="anthropic", model="claude-test", api_key_env="FAKE_KEY", base_url=srv.url,
                      params={"temperature": 0, "max_output_tokens": 1000}, unsupported_params=["temperature"],
                      provider_options={"output_config": {"effort": "high"}},
                      pricing=Pricing(input_per_mtok=1, output_per_mtok=10, cache_read_per_mtok=0.1, source="t", as_of="t"))
    a = create_adapter("anthropic/test", cfg)
    assert a.dropped_params == {"temperature": "declared unsupported for this model in models.yaml"}
    r = a.complete(conversation(), TOOLS, 500)
    srv.close()
    body = srv.requests[0]["body"]
    assert srv.requests[0]["path"] == "/v1/messages" and "temperature" not in body
    assert body["max_tokens"] == 1000 and body["output_config"] == {"effort": "high"}
    assert body["tools"][0]["input_schema"]["required"] == ["path"]
    assert r.tool_calls[0].name == "read_file" and r.usage.cache_read_tokens == 50
    assert r.provider_raw[1]["type"] == "tool_use"
    assert abs(a.cost_usd(r.usage) - (100 * 1 + 20 * 10 + 50 * 0.1) / 1e6) < 1e-12


def test_openai_compatible_against_fake_server(monkeypatch):
    srv = FakeServer([
        (503, {"error": "busy"}),
        (200, {"id": "c1", "model": "m-1", "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
            "role": "assistant", "content": None, "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "read_file", "arguments": "{\"path\": \"a\"}"}},
                {"id": "call_2", "type": "function", "function": {"name": "read_file", "arguments": "{not json"}}]}}],
               "usage": {"prompt_tokens": 30, "completion_tokens": 7}}),
    ])
    monkeypatch.setattr("aibench.adapters.base.time.sleep", lambda s: None)
    cfg = ModelConfig(adapter="openai_compatible", model="m-1", base_url=srv.url, params={"temperature": 0, "seed": 7},
                      max_retries=2)
    a = create_adapter("oa/test", cfg)
    retries = []
    r = a.complete_with_retries(conversation(), TOOLS, 256, on_retry=lambda *x: retries.append(x))
    srv.close()
    assert len(retries) == 1
    body = srv.requests[1]["body"]
    assert body["seed"] == 7 and body["max_tokens"] == 256
    assert body["messages"][2]["tool_calls"][0]["function"]["arguments"] == "{\"path\": \"a\"}"
    assert [m["role"] for m in body["messages"]] == ["system", "user", "assistant", "tool", "tool"]
    assert r.tool_calls[0].arguments == {"path": "a"} and r.tool_calls[1].raw_arguments == "{not json"
    assert r.usage.input_tokens == 30 and r.usage.reported
    assert a.cost_usd(r.usage) is None  # no pricing declared -> unavailable, never estimated


def test_missing_api_key_is_reported(monkeypatch):
    monkeypatch.delenv("NOPE_KEY", raising=False)
    a = create_adapter("oa", ModelConfig(adapter="openai_compatible", model="m", api_key_env="NOPE_KEY",
                                         base_url="http://127.0.0.1:9"))
    with pytest.raises(Exception, match="NOPE_KEY"):
        a.complete([Message("user", "hi")], None, 10)


def test_usage_accumulation():
    u = Usage(1, 2, reported=True).add(Usage(None, None))
    assert (u.input_tokens, u.output_tokens, u.reported) == (1, 2, True)
    assert Usage().total is None


def test_anthropic_agent_episode_end_to_end(tmp_suite, monkeypatch):
    """Full runner episode through the real Anthropic adapter against a fake Messages API."""
    pytest.importorskip("anthropic")
    from aibench.core.config import load_config
    from aibench.core.registry import Registry
    from aibench.core.runner import Runner
    from aibench.core.util import read_json
    from conftest import make_agent_benchmark

    make_agent_benchmark(tmp_suite)
    fix = "def add(a, b):\n    return a + b\n"
    srv = FakeServer([
        (200, {"id": "m1", "type": "message", "role": "assistant", "model": "claude-test", "stop_reason": "tool_use",
               "stop_sequence": None, "usage": {"input_tokens": 500, "output_tokens": 40},
               "content": [{"type": "thinking", "thinking": "", "signature": "sig-1"},
                           {"type": "tool_use", "id": "toolu_a", "name": "write_file", "input": {"path": "calc.py", "content": fix}}]}),
        (200, {"id": "m2", "type": "message", "role": "assistant", "model": "claude-test", "stop_reason": "tool_use",
               "stop_sequence": None, "usage": {"input_tokens": 600, "output_tokens": 30},
               "content": [{"type": "tool_use", "id": "toolu_b", "name": "run_command", "input": {"command": "python -m pytest -q"}}]}),
        (200, {"id": "m3", "type": "message", "role": "assistant", "model": "claude-test", "stop_reason": "end_turn",
               "stop_sequence": None, "usage": {"input_tokens": 700, "output_tokens": 20},
               "content": [{"type": "text", "text": "Fixed add()."}]}),
    ])
    monkeypatch.setenv("FAKE_KEY", "k")
    cfg = load_config(tmp_suite)
    cfg.models.models["anthropic/fake"] = ModelConfig(
        adapter="anthropic", model="claude-test", api_key_env="FAKE_KEY", base_url=srv.url,
        pricing=Pricing(input_per_mtok=2, output_per_mtok=10, source="test", as_of="2026-01-01"))
    reg = Registry.discover(cfg.benchmarks_dir, set(cfg.suite.categories))
    runner = Runner(cfg, reg, echo=False)
    store = runner.create_run([reg.get("tiny")], "anthropic/fake", attempts=1)
    outs = runner.execute(store)
    srv.close()
    assert outs[0].passed is True
    second = srv.requests[1]["body"]["messages"]
    assert second[1]["content"][0] == {"type": "thinking", "thinking": "", "signature": "sig-1"}  # replayed verbatim
    assert second[2]["content"][0]["type"] == "tool_result" and second[2]["content"][0]["tool_use_id"] == "toolu_a"
    assert srv.requests[0]["body"]["system"].startswith("You are an AI software engineer")
    ev = read_json(store.attempt_dir("bug_fixing/tiny", 1) / "evaluation.json")
    u = ev["usage"]
    assert (u["input_tokens"], u["output_tokens"], u["usage_status"]) == (1800, 90, "reported")
    assert u["cost_usd"] == pytest.approx((1800 * 2 + 90 * 10) / 1e6)
