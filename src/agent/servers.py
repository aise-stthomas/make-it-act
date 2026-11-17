"""Connect to the two tool servers. Given.

Deployed (ORDERS_URL and PAYMENTS_URL set by deploy.sh): over HTTP.
On your laptop: the same messages, handed to the server objects in this process."""
import os

from src.mcp.client import Client


def connect():
    if os.environ.get("ORDERS_URL") and os.environ.get("PAYMENTS_URL"):
        return {"orders": Client("orders", url=os.environ["ORDERS_URL"]),
                "payments": Client("payments", url=os.environ["PAYMENTS_URL"])}
    from src.servers import orders, payments
    return {"orders": Client("orders", server=orders.server),
            "payments": Client("payments", server=payments.server)}
