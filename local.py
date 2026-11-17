"""Run one ticket on your laptop: both servers in this process, tables in data/state/.

  uv run local.py T01                          a ticket from the suite, by id
  uv run local.py "I was charged twice..." --customer C-1042
  CRASH_AFTER_EFFECT=issue_refund uv run local.py T01      then: uv run local.py --resume <run_id>
"""
import argparse, json, time

from dotenv import load_dotenv
load_dotenv()

from src.agent import runs
from src.store import table

ap = argparse.ArgumentParser()
ap.add_argument("ticket", nargs="?")
ap.add_argument("--customer")
ap.add_argument("--resume", metavar="RUN_ID")
args = ap.parse_args()

if args.resume:
    run_id = args.resume
else:
    text, customer = args.ticket, args.customer
    for line in open("data/suite/tickets.jsonl"):
        t = json.loads(line)
        if t["id"] == args.ticket:
            text, customer = t["text"], t["customer_id"]
    run_id = runs.start(text, customer)
print("run:", run_id)

status = "running"
while status == "running":
    status = runs.advance(run_id, deadline=time.time() + 900)
row = runs.get(run_id)
print(f"status: {status}   steps: {row['step']}   input tokens: {row['input_tokens']:,}")
print("answer:", row.get("answer"))
for r in table("refunds").scan():
    print("refund:", r["refund_id"], r["charge_id"], r["amount_cents"], "approved by", r["approved_by"])
for a in runs.waiting():
    if a["run_id"] == run_id:
        print(f"waiting for a person: {a['id']} {a['charge_id']} {a['amount_cents']} cents. "
              f"Decide with: uv run approve.py {a['id']}")
