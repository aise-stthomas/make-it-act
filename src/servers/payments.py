"""The payments server. YOURS. The refund rules live here, in the payments team's code.

Write the four tools. check_server.py checks them; the agent declares the first three.

issue_refund refuses, each as a tool result with an "error" (never by raising):
  - a charge that does not exist, or is not "captured"
  - a charge on another customer's order (caller() is the customer the request is for)
  - more than the refundable balance (amount_cents less any refunded_before_cents)
  - more than LIMIT_CENTS: a person must approve those
  - a charge already refunded: return the first refund, marked "repeated": True
issue_approved_refund: the same rules without the limit, and approved_by must not be empty.
  The agent never declares it; your orchestrator calls it after a person approves.

A charge is refunded at most once, however many times it is asked: write the key
"refund:<charge_id>" together with the refund, in ONE conditional write. table("refunds")
has put_if_absent() for exactly that (see src/store.py).

Look at src/servers/orders.py for a finished server: how a tool is declared, how caller()
is used, how an error is returned.
"""
from src.mcp.server import Server, caller
from src.servers.seed import CHARGES, ORDERS
from src.store import table

server = Server("payments")
LIMIT_CENTS = 5000


@server.tool("TODO: what the model reads about this tool.", read_only=True)
def get_charges(order_id: str) -> dict:
    """The charges on one of this customer's orders."""
    return {"error": "get_charges is not written yet"}


@server.tool("TODO: what the model reads about this tool.", read_only=True)
def get_refunds(charge_id: str) -> dict:
    """The refunds already made on a charge: refunded_before_cents from the seed, and yours."""
    return {"error": "get_refunds is not written yet"}


@server.tool("TODO: what the model reads about this tool, including what it refuses.",
             destructive=True, idempotent=True)
def issue_refund(charge_id: str, amount_cents: int, reason: str) -> dict:
    return {"error": "issue_refund is not written yet"}


@server.tool("Refund a charge a person has approved. For the approval path only.",
             destructive=True, idempotent=True)
def issue_approved_refund(charge_id: str, amount_cents: int, approved_by: str) -> dict:
    return {"error": "issue_approved_refund is not written yet"}
