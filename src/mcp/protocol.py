"""The Model Context Protocol, version 2026-07-28: the few pieces this lab uses.

Every request stands alone. There is no handshake and no session: each request carries the
protocol version and the client's capabilities in params._meta, and the server accepts or
rejects each one on its own."""

VERSION = "2026-07-28"
SUPPORTED = [VERSION]
CLIENT_INFO = {"name": "make-it-act", "version": "0.1.0"}
CUSTOMER_KEY = "desk.example/customer_id"   # who the call is on behalf of; set by the program
SERVER_KEY = "io.modelcontextprotocol/serverInfo"

# JSON-RPC error codes used here.
INVALID_PARAMS = -32602          # also: an unknown tool
METHOD_NOT_FOUND = -32601
UNSUPPORTED_VERSION = -32022


def request(request_id, method, params=None, meta=None):
    params = dict(params or {})
    params["_meta"] = {**(meta or {}),
        "io.modelcontextprotocol/protocolVersion": VERSION,
        "io.modelcontextprotocol/clientCapabilities": {},
        "io.modelcontextprotocol/clientInfo": CLIENT_INFO,
    }
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}


def error(request_id, code, message, data=None):
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": err}
