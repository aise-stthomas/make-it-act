"""Send one ticket to your deployed API and wait for the run to finish. Given.

  uv run ticket.py T01                                  a ticket from the suite, by id
  uv run ticket.py "I was charged twice..." --customer C-1042
  uv run ticket.py T04 --url https://...                another API (default: API_URL in .env)

It prints the run's status, steps, input tokens and reply, and any approval waiting for a person.
"""
import argparse, json, os, time, urllib.error, urllib.request

from dotenv import load_dotenv
load_dotenv()

ap = argparse.ArgumentParser()
ap.add_argument("ticket")
ap.add_argument("--customer")
ap.add_argument("--url", default=os.environ.get("API_URL"))
ap.add_argument("--timeout", type=int, default=600)
args = ap.parse_args()
if not args.url:
    raise SystemExit("no API URL: run ./deploy.sh, or pass --url")

text, customer = args.ticket, args.customer
for line in open("data/suite/tickets.jsonl"):
    t = json.loads(line)
    if t["id"] == args.ticket:
        text, customer = t["text"], t["customer_id"]
if not customer:
    raise SystemExit("give --customer for a ticket that is not in the suite")


def call(method, path, body=None):
    req = urllib.request.Request(args.url.rstrip("/") + path, json.dumps(body).encode() if body else None,
                                 {"Content-Type": "application/json", "x-lab-token": os.environ.get("LAB_TOKEN", "")},
                                 method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise SystemExit("the API refused the token (401): check LAB_TOKEN in .env against deploy.sh's")
        raise SystemExit(f"the API answered {e.code}: {e.read().decode()[:300]}")


run_id = call("POST", "/tickets", {"text": text, "customer_id": customer})["run_id"]
print("run:", run_id)
started, status = time.time(), "running"
while time.time() - started < args.timeout:
    time.sleep(3)
    row = call("GET", f"/runs/{run_id}")
    if row["status"] != status:
        status = row["status"]
        print(f"  {status}   step {row.get('step')}")
    if status != "running":
        break
print(f"status: {row['status']}   steps: {row.get('step')}   input tokens: {row.get('input_tokens', 0):,}")
print("answer:", row.get("answer"))
for a in call("GET", "/approvals")["waiting"]:
    if a["run_id"] == run_id:
        print(f"waiting for a person: {a['id']} {a['charge_id']} {a['amount_cents']} cents. "
              f"Decide with: uv run approve.py {a['id']} --url $API_URL")
