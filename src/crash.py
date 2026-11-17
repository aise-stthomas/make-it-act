"""The kill switch for deliverable 3.

With CRASH_AFTER_EFFECT=issue_refund set, the process exits the moment an issue_refund call
returns, before your loop can checkpoint. It happens once per run (a row in the crashes
table remembers it), so the resumed run can finish. The orchestrator tells this module which
run is being advanced with crash.current_run.set(run_id).
"""
import contextvars, os, sys

current_run = contextvars.ContextVar("current_run", default=None)


def after_effect(tool_name):
    if os.environ.get("CRASH_AFTER_EFFECT") != tool_name or current_run.get() is None:
        return
    from src.store import table
    if table("crashes").put_if_absent({"id": f"{current_run.get()}:{tool_name}"}):
        print(f"CRASH_AFTER_EFFECT: exiting after {tool_name} in run {current_run.get()}", flush=True)
        sys.stdout.flush()
        os._exit(1)
