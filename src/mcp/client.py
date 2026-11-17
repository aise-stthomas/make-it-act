"""A client: one connection to one tool server.

Deployed, a client POSTs each message to the server's URL. On your laptop it hands the same
message straight to the server object in this process. Either way the bytes are JSON-RPC.

    orders = Client("orders", url=os.environ["ORDERS_URL"])     # deployed
    orders = Client("orders", server=orders_server)              # local
    orders.call_tool("find_order", {"order_id": "88213"}, customer="C-1042")
"""
import itertools, json, os, threading, urllib.request

from src import crash
from src.mcp import protocol as p


class Client:
    def __init__(self, name, url=None, server=None):
        self.name, self.url, self.server = name, url, server
        self.ids = itertools.count(1)
        self.lock = threading.Lock()

    def send(self, method, params=None, meta=None):
        with self.lock:
            message = p.request(next(self.ids), method, params, meta)
        if self.url:
            req = urllib.request.Request(self.url, json.dumps(message).encode(), {
                "Content-Type": "application/json", "MCP-Protocol-Version": p.VERSION,
                "x-lab-token": os.environ.get("LAB_TOKEN", "")})
            with urllib.request.urlopen(req, timeout=60) as r:
                reply = json.load(r)
        else:
            reply = json.loads(self.server.http(json.dumps(message))[1])
        if "error" in reply:
            raise RuntimeError(f"{self.name}: {reply['error']['message']}")
        return reply["result"]

    def list_tools(self):
        return self.send("tools/list")["tools"]

    def call_tool(self, name, arguments, customer=None):
        meta = {p.CUSTOMER_KEY: customer} if customer else None
        result = self.send("tools/call", {"name": name, "arguments": arguments}, meta)
        out = result.get("structuredContent")
        if out is None:
            out = {"text": "".join(c.get("text", "") for c in result.get("content", []))}
        crash.after_effect(name)          # CRASH_AFTER_EFFECT: exit here, once per run
        return out
