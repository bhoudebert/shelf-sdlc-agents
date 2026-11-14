"""A stand-in for the OpenAI Responses API for Warden's live check of Codex: the "model" asks to run one shell command, then says it is done.

Usage: mock_openai.py PORT COMMAND LOGFILE. The tool is the one Codex declares for the shell (`exec_command`, argument `cmd`; the
older `shell` with a `command` list is handled too). It never sees a real model or a real key."""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

COMMAND = sys.argv[2]
LOG = sys.argv[3]


def sse(events):
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


def reply(items):
    ev = [{"type": "response.created", "response": {"id": "resp_1"}}]
    for i, item in enumerate(items):
        ev.append({"type": "response.output_item.added", "output_index": i, "item": item})
        ev.append({"type": "response.output_item.done", "output_index": i, "item": item})
    usage = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
    ev.append({"type": "response.completed", "response": {"id": "resp_1", "usage": usage}})
    return sse(ev)


def call(tools):
    """The item that asks for COMMAND: a patch goes to the `apply_patch` custom tool, anything else to the shell tool."""
    if COMMAND.startswith("*** Begin Patch") and any(t.get("name") == "apply_patch" for t in tools):
        return {"type": "custom_tool_call", "id": "ctc_1", "call_id": "call_1", "name": "apply_patch", "input": COMMAND}
    name, args = shell_call(tools)
    return {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": name, "arguments": json.dumps(args)}


def shell_call(tools):
    names = {t.get("name"): t for t in tools if t.get("type") == "function"}
    if "exec_command" in names:
        return "exec_command", {"cmd": COMMAND}
    return "shell", {"command": ["bash", "-lc", COMMAND]}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("content-length", 0)) or 0)
        try: req = json.loads(body or b"{}")
        except Exception: req = {}
        with open(LOG, "a") as f: f.write(json.dumps({"path": self.path, "req": req})[:400000] + "\n")
        if self.path.rstrip("/").endswith("/responses"):
            has_result = any(i.get("type") in ("function_call_output", "custom_tool_call_output") for i in req.get("input", []) if isinstance(i, dict))
            if has_result:
                items = [{"type": "message", "role": "assistant", "id": "msg_2", "content": [{"type": "output_text", "text": "Done."}]}]
            else:
                items = [call(req.get("tools", []))]
            payload = reply(items)
            self.send_response(200); self.send_header("content-type", "text/event-stream"); self.send_header("content-length", str(len(payload))); self.end_headers(); self.wfile.write(payload); return
        payload = b"{}"
        self.send_response(200); self.send_header("content-type", "application/json"); self.send_header("content-length", "2"); self.end_headers(); self.wfile.write(payload)
    do_GET = do_PUT = do_HEAD = lambda self: (self.send_response(200), self.send_header("content-length", "2"), self.end_headers(), self.wfile.write(b"{}"))


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
