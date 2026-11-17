"""The seeded data the servers read. Do not edit data/seed/seed.json."""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SEED = json.load(open(os.path.join(ROOT, "data", "seed", "seed.json")))
ORDERS = {o["order_id"]: o for o in SEED["orders"]}
CHARGES = {c["charge_id"]: c for c in SEED["charges"]}
