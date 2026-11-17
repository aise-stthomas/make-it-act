"""Check a payments server against the protocol and the refund rules. Given; do not edit.

  uv run check_server.py                     your server, in this process
  uv run check_server.py $API_URL/mcp/payments

It refunds a charge kept for this check (order 99001, customer C-9999), never one the suite uses.
"""
import json, os, sys, urllib.request

from dotenv import load_dotenv
load_dotenv()

from src.mcp import protocol as p

URL = sys.argv[1] if len(sys.argv) > 1 else None
CHECK_CUSTOMER = "C-9999"
ids = iter(range(1, 100))
passed, failed = 0, 0


def send(message):
    if URL:
        req = urllib.request.Request(URL, json.dumps(message).encode(), {
            "Content-Type": "application/json", "x-lab-token": os.environ.get("LAB_TOKEN", "")})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    from src.servers.payments import server
    return json.loads(server.http(json.dumps(message))[1])


def call(name, arguments, customer=CHECK_CUSTOMER):
    return send(p.request(next(ids), "tools/call", {"name": name, "arguments": arguments},
                          {p.CUSTOMER_KEY: customer}))


def check(label, ok, detail=""):
    global passed, failed
    passed, failed = passed + bool(ok), failed + (not ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + ("" if ok else f"\n        {detail}"))


print(f"checking {URL or 'src/servers/payments.py, in this process'}")

r = send(p.request(next(ids), "tools/list"))
tools = {t["name"]: t for t in r.get("result", {}).get("tools", [])}
check("tools/list names the four tools",
      {"get_charges", "get_refunds", "issue_refund", "issue_approved_refund"} <= set(tools), list(tools))
check("every tool has an inputSchema of type object",
      all(t.get("inputSchema", {}).get("type") == "object" for t in tools.values()), "")
check("every result says resultType", r.get("result", {}).get("resultType") == "complete", r)

r = call("get_charges", {"order_id": "99001"})
charges = r.get("result", {}).get("structuredContent", {}).get("charges", [])
check("get_charges returns the order's two charges", len(charges) == 2, r)

r = send(p.request(next(ids), "tools/call", {"name": "no_such_tool", "arguments": {}}))
check("an unknown tool is a protocol error (-32602)", r.get("error", {}).get("code") == -32602, r)

m = p.request(next(ids), "tools/list")
m["params"]["_meta"]["io.modelcontextprotocol/protocolVersion"] = "1900-01-01"
r = send(m)
check("an unsupported protocol version is refused (-32022)", r.get("error", {}).get("code") == -32022, r)

first = call("issue_refund", {"charge_id": "ch_9902", "amount_cents": 1000, "reason": "check"})
second = call("issue_refund", {"charge_id": "ch_9902", "amount_cents": 1000, "reason": "check"})
refunds = call("get_refunds", {"charge_id": "ch_9902"}).get("result", {}).get("structuredContent", {}).get("refunds", [])
check("the same refund twice: one refund, the second returned as a repeat",
      not first.get("result", {}).get("isError") and second.get("result", {}).get("structuredContent", {}).get("repeated") is True
      and len(refunds) == 1, json.dumps([first.get("result", {}).get("structuredContent"), second.get("result", {}).get("structuredContent"), refunds]))

# A server that refuses everything passes none of these: each needs the refund above to work.
works = not first.get("result", {}).get("isError")
r = call("issue_refund", {"charge_id": "ch_9902", "amount_cents": 6000, "reason": "check"})
check("more than the charge is refused as a result (isError), not an exception",
      works and r.get("result", {}).get("isError") is True, r)

r = call("issue_refund", {"charge_id": "ch_7731", "amount_cents": 100, "reason": "check"})
check("a charge on another customer's order is refused", works and r.get("result", {}).get("isError") is True, r)

r = send(p.request(next(ids), "tools/call", {"name": "issue_refund",
                                             "arguments": {"charge_id": "ch_9902", "amount_cents": 100, "reason": "check"}}))
check("a call with no customer in _meta is refused", works and r.get("result", {}).get("isError") is True, r)


print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
