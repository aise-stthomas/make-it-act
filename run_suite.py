"""Run the ticket suite and record what each run left in the tables. Given.

  uv run run_suite.py                       on your laptop, live model
  uv run run_suite.py --url $API_URL        against your deployed API (reads your DynamoDB tables)
  uv run run_suite.py --replay              on your laptop, from data/fixtures/: no model, no key
  uv run run_suite.py --runs 3 --only T01,T04

Before each pass the refunds, runs and approvals tables are emptied, so every pass starts from
the seeded state. Each ticket's end state is read from the tables, never from the reply, and
written to data/results/<time>.json. Live runs save their model responses to data/fixtures/.
Then score.py scores the results file.
"""
import argparse, json, os, time, urllib.request

from dotenv import load_dotenv
load_dotenv()

ap = argparse.ArgumentParser()
ap.add_argument("--url")
ap.add_argument("--replay", action="store_true")
ap.add_argument("--runs", type=int, default=1)
ap.add_argument("--only")
ap.add_argument("--timeout", type=int, default=600, help="seconds to wait for one deployed run")
args = ap.parse_args()
if args.url:
    os.environ["STORE"] = "dynamodb"                   # read your deployed tables

from src.agent import model, runs
from src.servers.seed import CHARGES
from src.store import table

TICKETS = [json.loads(l) for l in open("data/suite/tickets.jsonl")]
if args.only:
    TICKETS = [t for t in TICKETS if t["id"] in args.only.split(",")]
FINAL = ("done", "waiting", "failed", "superseded")


def api(method, path, body=None):
    req = urllib.request.Request(args.url.rstrip("/") + path, json.dumps(body).encode() if body else None,
                                 {"Content-Type": "application/json", "x-lab-token": os.environ.get("LAB_TOKEN", "")},
                                 method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def run_ticket(t):
    if args.url:
        run_id = api("POST", "/tickets", {"text": t["text"], "customer_id": t["customer_id"]})["run_id"]
        started = time.time()
        while time.time() - started < args.timeout:
            time.sleep(3)
            row = api("GET", f"/runs/{run_id}")
            if row["status"] in FINAL or row["status"].startswith("stopped"):
                return run_id
        return run_id
    if args.replay:
        path = f"data/fixtures/{t['id']}.json"
        if not os.path.exists(path):
            raise SystemExit(f"no recording for {t['id']}: run the suite live once first")
        model.replay(json.load(open(path)))
    run_id = runs.start(t["text"], t["customer_id"])
    status = "running"
    while status == "running":
        status = runs.advance(run_id, deadline=time.time() + 900)
    model.replay(None)
    return run_id


def end_state(t, run_id):
    row = runs.get(run_id) or {}
    charges = [c for c in CHARGES.values() if c["order_id"] in t["orders"]]
    refunds = {}
    for c in charges:
        r = table("refunds").get(f"refund:{c['charge_id']}")
        if r:
            refunds[c["charge_id"]] = {"amount_cents": r["amount_cents"], "approved_by": r["approved_by"]}
    approvals = [{k: a[k] for k in ("id", "charge_id", "amount_cents", "decision")}
                 for a in table("approvals").scan() if a["run_id"] == run_id]
    return {"ticket": t["id"], "slice": t["slice"], "expect": t["expect"], "run_id": run_id,
            "status": row.get("status"), "steps": row.get("step"), "input_tokens": row.get("input_tokens"),
            "answer": row.get("answer"), "refunds": refunds, "approvals": approvals,
            "charge_amounts": {c["charge_id"]: c["amount_cents"] for c in charges}}


def save_recording(t, run_id):
    rec = sorted(table("recordings").scan(run_id + ":"), key=lambda r: int(r["id"].split(":")[1]))
    if rec:
        os.makedirs("data/fixtures", exist_ok=True)
        json.dump([r["response"] for r in rec], open(f"data/fixtures/{t['id']}.json", "w"))


results = []
for k in range(args.runs):
    for name in ("refunds", "runs", "approvals", "crashes"):
        table(name).clear()
    for t in TICKETS:
        run_id = run_ticket(t)
        state = end_state(t, run_id)
        state["pass"] = k + 1
        results.append(state)
        if not args.replay:
            save_recording(t, run_id)
        print(f"pass {k + 1}  {t['id']}  {t['slice']:<16} {state['status']:<14} steps {state['steps']:>2}  "
              f"tokens {state['input_tokens'] or 0:>6,}  refunds {list(state['refunds'])}  "
              f"approvals {[a['charge_id'] for a in state['approvals']]}")

os.makedirs("data/results", exist_ok=True)
out = f"data/results/{time.strftime('%Y%m%d-%H%M%S')}{'-replay' if args.replay else ''}.json"
json.dump(results, open(out, "w"), indent=1)
print("\nwrote", out, "\nscore it:  uv run score.py", out)
