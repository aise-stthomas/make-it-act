"""The orders server: read-only tools over the seeded orders. Given, and finished.

Every tool answers only for the customer the request is on behalf of: caller() reads it from
the request's _meta, where the agent's program put it. The model cannot choose it."""
from src.mcp.server import Server, caller
from src.servers.seed import ORDERS, SEED

server = Server("orders")


def visible(order_id):
    order = ORDERS.get(order_id)
    if order is None:
        return None, {"error": f"no order {order_id}"}
    if order["customer_id"] != caller():
        return None, {"error": f"order {order_id} does not belong to this customer"}
    return order, None


@server.tool("Find one order by its number: items, total in cents, status, time.", read_only=True)
def find_order(order_id: str) -> dict:
    order, err = visible(order_id)
    return err or order


@server.tool("This customer's orders, newest first. Optionally only one status.", read_only=True)
def search_orders(status: str = "") -> dict:
    found = [o for o in ORDERS.values() if o["customer_id"] == caller() and (not status or o["status"] == status)]
    found.sort(key=lambda o: o["created_at"], reverse=True)
    return {"orders": [{k: o[k] for k in ("order_id", "created_at", "status", "total_cents")} for o in found]}


@server.tool("What happened to an order, oldest first: created, payments, retries, refunds, shipping.", read_only=True)
def get_order_history(order_id: str) -> dict:
    order, err = visible(order_id)
    if err:
        return err
    return {"order_id": order_id, "history": [{"at": a, "event": e} for a, e in SEED["order_history"].get(order_id, [])]}
