"""A person decides on a refund that is waiting.

  uv run approve.py                         list what is waiting
  uv run approve.py <approval_id>           approve it, and continue the run (on your laptop)
  uv run approve.py <approval_id> --decline --by "J. Howard"
  uv run approve.py ... --url $API_URL      the same, against your deployed API
"""
import argparse, json, os, time, urllib.request

from dotenv import load_dotenv
load_dotenv()

ap = argparse.ArgumentParser()
ap.add_argument("approval_id", nargs="?")
ap.add_argument("--decline", action="store_true")
ap.add_argument("--by", default="a reviewer")
ap.add_argument("--url")
args = ap.parse_args()
decision = "declined" if args.decline else "approved"


def call(method, path, body=None):
    req = urllib.request.Request(args.url.rstrip("/") + path, json.dumps(body).encode() if body else None,
                                 {"Content-Type": "application/json", "x-lab-token": os.environ.get("LAB_TOKEN", "")},
                                 method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


if args.url:
    out = call("POST", f"/approvals/{args.approval_id}", {"decision": decision, "by": args.by}) \
        if args.approval_id else call("GET", "/approvals")
    print(json.dumps(out, indent=1))
else:
    from src.agent import runs
    if not args.approval_id:
        print(json.dumps(runs.waiting(), indent=1))
    else:
        a = runs.decide(args.approval_id, decision, args.by)
        print(json.dumps(a, indent=1))
        if "run_id" in a:
            status = "running"
            while status in ("running", "waiting"):
                status = runs.advance(a["run_id"], deadline=time.time() + 900)
                if status == "waiting":
                    break
            row = runs.get(a["run_id"])
            print(f"run {a['run_id']}: {status}\nanswer: {row.get('answer')}")
