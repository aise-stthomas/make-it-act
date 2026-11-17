"""A tool server. You write the tools as functions; this file answers the protocol for them.

Three methods: server/discover, tools/list, tools/call, one JSON-RPC message per POST.
A tool reads who is asking with caller(): the customer the agent's program put in _meta.
The model never chooses it."""
import contextvars, inspect, json
from typing import get_args, get_origin, get_type_hints

from src.mcp import protocol as p

JSON_TYPES = {int: "integer", float: "number", bool: "boolean", str: "string"}
PYTHON_TYPES = {"integer": int, "number": (int, float), "boolean": bool, "string": str, "array": list}
_caller = contextvars.ContextVar("caller", default=None)


def caller():
    """The customer this call is on behalf of, from the request's _meta; None if not sent."""
    return _caller.get()


class Server:
    def __init__(self, name, version="1.0.0"):
        self.info = {"name": name, "version": version}
        self.tools = {}         # name -> function: what this server runs
        self.declarations = []  # what tools/list returns

    def tool(self, description, read_only=False, destructive=False, idempotent=False):
        def register(fn):
            self.declarations.append({
                "name": fn.__name__,
                "description": description,
                "inputSchema": input_schema(fn),
                "annotations": {"readOnlyHint": read_only, "destructiveHint": destructive,
                                "idempotentHint": idempotent, "openWorldHint": False},
            })
            self.tools[fn.__name__] = fn
            return fn
        return register

    def handle(self, message):
        rid, method = message.get("id"), message.get("method")
        params = message.get("params", {})
        if rid is None:
            return None                                   # a notification: no reply
        version = params.get("_meta", {}).get("io.modelcontextprotocol/protocolVersion")
        if version not in p.SUPPORTED:
            return p.error(rid, p.UNSUPPORTED_VERSION, "Unsupported protocol version",
                           {"supported": p.SUPPORTED, "requested": version})
        if method == "server/discover":
            result = {"supportedVersions": p.SUPPORTED,
                      "capabilities": {"tools": {"listChanged": True}},
                      "ttlMs": 0, "cacheScope": "public"}
        elif method == "tools/list":
            result = {"tools": self.declarations}
        elif method == "tools/call":
            name, args = params.get("name"), params.get("arguments", {})
            if name not in self.tools:
                return p.error(rid, p.INVALID_PARAMS, f"Unknown tool: {name}")
            _caller.set(params.get("_meta", {}).get(p.CUSTOMER_KEY))
            result = self.call(name, args)
        else:
            return p.error(rid, p.METHOD_NOT_FOUND, f"Method not found: {method}")
        result = {"resultType": "complete", **result, "_meta": {p.SERVER_KEY: self.info}}
        return {"jsonrpc": "2.0", "id": rid, "result": result}

    def call(self, name, args):
        # A tool's failure is a result the next turn can read, not a protocol error.
        declaration = next(d for d in self.declarations if d["name"] == name)
        problem = validate(args, declaration["inputSchema"])
        if problem:
            out = {"error": f"Invalid call to {name}: {problem}"}
        else:
            try:
                out = self.tools[name](**args)
            except Exception as e:
                out = {"error": f"{name} failed: {type(e).__name__}: {e}"}
        failed = isinstance(out, dict) and "error" in out
        return {"content": [{"type": "text", "text": json.dumps(out)}],
                "structuredContent": out, "isError": failed}

    def http(self, body):
        """One HTTP POST: the body is one JSON-RPC message; the reply is the response body."""
        reply = self.handle(json.loads(body or "{}"))
        return (202, "") if reply is None else (200, json.dumps(reply))


def input_schema(fn):
    hints = get_type_hints(fn)
    properties, required = {}, []
    for name, param in inspect.signature(fn).parameters.items():
        properties[name] = json_type(hints.get(name, str))
        if param.default is inspect.Parameter.empty:
            required.append(name)
    return {"type": "object", "properties": properties, "required": required}


def json_type(t):
    if get_origin(t) is list:
        return {"type": "array", "items": json_type(get_args(t)[0])}
    return {"type": JSON_TYPES.get(t, "string")}


def validate(args, schema):
    missing = [a for a in schema["required"] if a not in args]
    unknown = [a for a in args if a not in schema["properties"]]
    if missing:
        return f"missing argument(s): {', '.join(missing)}"
    if unknown:
        return f"unknown argument(s): {', '.join(unknown)}"
    for name, value in args.items():
        expected = schema["properties"][name]["type"]
        if expected == "integer" and isinstance(value, float) and value.is_integer():
            continue                                      # JSON has one number type
        if not isinstance(value, PYTHON_TYPES[expected]):
            return f"{name} must be {expected}, got {type(value).__name__}"
