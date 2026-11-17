"""The Lambda functions. Given. deploy.sh points four functions at the four handlers here:

    orders     POST /mcp/orders                    the orders server
    payments   POST /mcp/payments                  your payments server
    api        POST /tickets · GET /runs/{id} · POST /runs/{id}/resume
               GET /approvals · POST /approvals/{id}
    worker     invoked by api, never by a person: advances one run, and invokes itself again
               if the run is not finished when its time is nearly up
"""
import json, os, time

TOKEN = os.environ.get("LAB_TOKEN", "")


def reply(status, body):
    return {"statusCode": status, "headers": {"Content-Type": "application/json"},
            "body": body if isinstance(body, str) else json.dumps(body)}


def authorized(event):
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    return not TOKEN or headers.get("x-lab-token") == TOKEN


def mcp(server, event):
    if not authorized(event):
        return reply(401, {"error": "missing or wrong x-lab-token"})
    status, body = server.http(event.get("body"))
    return reply(status, body)


def orders(event, context):
    from src.servers.orders import server
    return mcp(server, event)


def payments(event, context):
    from src.servers.payments import server
    return mcp(server, event)


def start_worker(run_id):
    import boto3
    boto3.client("lambda").invoke(FunctionName=os.environ["WORKER_FUNCTION"], InvocationType="Event",
                                  Payload=json.dumps({"run_id": run_id}).encode())


def api(event, context):
    from src.agent import runs
    if not authorized(event):
        return reply(401, {"error": "missing or wrong x-lab-token"})
    method = event["requestContext"]["http"]["method"]
    parts = [p for p in event.get("rawPath", "").split("/") if p]
    body = json.loads(event.get("body") or "{}")
    if method == "POST" and parts == ["tickets"]:
        run_id = runs.start(body["text"], body["customer_id"])
        start_worker(run_id)
        return reply(202, {"run_id": run_id})
    if method == "GET" and len(parts) == 2 and parts[0] == "runs":
        row = runs.get(parts[1])
        if not row:
            return reply(404, {"error": f"no run {parts[1]}"})
        return reply(200, {k: v for k, v in row.items() if k != "contents"})
    if method == "POST" and len(parts) == 3 and parts[0] == "runs" and parts[2] == "resume":
        start_worker(parts[1])
        return reply(202, {"run_id": parts[1], "resumed": True})
    if method == "GET" and parts == ["approvals"]:
        return reply(200, {"waiting": runs.waiting()})
    if method == "POST" and len(parts) == 2 and parts[0] == "approvals":
        a = runs.decide(parts[1], body.get("decision"), body.get("by"))
        if "run_id" in a:
            start_worker(a["run_id"])
        return reply(200, a)
    return reply(404, {"error": f"no route {method} /{'/'.join(parts)}"})


def worker(event, context):
    from src.agent import runs
    deadline = time.time() + context.get_remaining_time_in_millis() / 1000
    status = runs.advance(event["run_id"], deadline)
    print(json.dumps({"run_id": event["run_id"], "status": status}))
    if status == "running":                     # not finished in this invocation: continue in the next
        start_worker(event["run_id"])
    return {"run_id": event["run_id"], "status": status}
