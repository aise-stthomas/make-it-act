"""The orchestrator. YOURS. No durable-execution products: this is the part you are building.

A run is a row in table("runs"), rewritten after every step, so any invocation can continue
it. A refund over the limit is a row in table("approvals"): the run waits as data.

The given code calls these five functions; keep their names and what they return.
    start(ticket, customer_id) -> run_id
    advance(run_id, deadline)  -> status
    decide(approval_id, decision, by) -> the approval row
    waiting() -> approvals still waiting for a person
    get(run_id) -> the run row

The run row must hold at least: status, step, input_tokens, answer, ticket, customer_id,
and the contents. Status is one of: running, waiting, done, stopped:steps, stopped:tokens,
stopped:time (and, for the bonus, superseded).

Before each turn: crash.current_run.set(run_id). The kill switch and the model's recordings
both use it.
"""
from src import crash
from src.agent.model import Model, input_tokens
from src.agent.servers import connect
from src.store import table

MAX_STEPS, MAX_TOKENS, MAX_ACTIVE_SECONDS = 14, 60000, 120

# A tool your program runs, declared to the model like any other.
REQUEST_APPROVAL = {
    "name": "request_approval",
    "description": "Ask a person to approve a refund over 5000 cents. The run waits for the decision.",
    "parameters": {"type": "object", "properties": {
        "charge_id": {"type": "string"}, "amount_cents": {"type": "integer"}, "note": {"type": "string"}},
        "required": ["charge_id", "amount_cents", "note"]},
}


def start(ticket, customer_id):
    """Create the run's row: status running, step 0, contents = [the ticket as a user turn]."""
    raise NotImplementedError("runs.start")


def get(run_id):
    return table("runs").get(run_id)


def advance(run_id, deadline):
    """Run steps until the run is done, waiting for a person, out of a budget, or the deadline
    (time.time() seconds) is close; checkpoint after every step. If the run is waiting and a
    person has decided, carry out the decision first (on an approval: issue_approved_refund,
    under the approver's name, with the run's customer) and tell the run the outcome.
    Return the run's status, or "running" if the deadline came first."""
    raise NotImplementedError("runs.advance")


def decide(approval_id, decision, by):
    """Record "approved" or "declined" and who decided. A second decision changes nothing."""
    raise NotImplementedError("runs.decide")


def waiting():
    raise NotImplementedError("runs.waiting")
