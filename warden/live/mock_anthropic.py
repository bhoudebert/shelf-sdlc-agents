"""A stand-in for the Anthropic Messages API for Warden's live check: the "model" asks to run one Bash command, then says it is done.

Usage: mock_anthropic.py PORT COMMAND LOGFILE. It never sees a real model or a real key."""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

COMMAND = sys.argv[2]
LOG = sys.argv[3]
state = {"calls": 0}

def sse(events):
    out = ""
    for name, data in events:
        out += f"event: {name}\ndata: {json.dumps(data)}\n\n"
    return out.encode()

def message(content_blocks, stop):
    start = {"type": "message_start", "message": {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-sonnet-4-5",
             "content": [], "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 1}}}
    ev = [("message_start", start)]
    for i, block in enumerate(content_blocks):
        if block["type"] == "tool_use":
            ev.append(("content_block_start", {"type": "content_block_start", "index": i, "content_block": {"type": "tool_use", "id": block["id"], "name": block["name"], "input": {}}}))
            ev.append(("content_block_delta", {"type": "content_block_delta", "index": i, "delta": {"type": "input_json_delta", "partial_json": json.dumps(block["input"])}}))
        else:
            ev.append(("content_block_start", {"type": "content_block_start", "index": i, "content_block": {"type": "text", "text": ""}}))
            ev.append(("content_block_delta", {"type": "content_block_delta", "index": i, "delta": {"type": "text_delta", "text": block["text"]}}))
        ev.append(("content_block_stop", {"type": "content_block_stop", "index": i}))
    ev.append(("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None}, "usage": {"output_tokens": 20}}))
    ev.append(("message_stop", {"type": "message_stop"}))
    return sse(ev)

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("content-length", 0)) or 0)
        try: req = json.loads(body or b"{}")
        except Exception: req = {}
        with open(LOG, "a") as f: f.write(json.dumps({"path": self.path, "req": req})[:200000] + "\n")
        if "/v1/messages" in self.path and "count_tokens" not in self.path and req.get("tools"):
            has_result = any(isinstance(m.get("content"), list) and any(b.get("type") == "tool_result" for b in m["content"]) for m in req.get("messages", []))
            state["calls"] += 1
            if has_result:
                payload = message([{"type": "text", "text": "I could not run that."}], "end_turn")
            else:
                payload = message([{"type": "tool_use", "id": "toolu_01", "name": "Bash", "input": {"command": COMMAND, "description": "test"}}], "tool_use")
            self.send_response(200); self.send_header("content-type", "text/event-stream"); self.send_header("content-length", str(len(payload))); self.end_headers(); self.wfile.write(payload); return
        if "/v1/messages" in self.path and req.get("stream"):
            payload = message([{"type": "text", "text": "ok"}], "end_turn")
            self.send_response(200); self.send_header("content-type", "text/event-stream"); self.send_header("content-length", str(len(payload))); self.end_headers(); self.wfile.write(payload); return
        payload = json.dumps({"input_tokens": 10}).encode()
        self.send_response(200); self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(payload))); self.end_headers(); self.wfile.write(payload)
    do_GET = do_PUT = do_HEAD = lambda self: (self.send_response(200), self.send_header("content-length","2"), self.end_headers(), self.wfile.write(b"{}"))

if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
