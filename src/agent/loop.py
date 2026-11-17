"""The loop. YOURS. No agent frameworks.

What it needs to do (src/agent/runs.py calls it):
  - Discover each server's tools with tools/list (client.list_tools()), and declare to the
    model only the ones on your allow list. issue_approved_refund is never declared.
  - Turn a declaration into what the model's provider wants:
        {"name": ..., "description": ..., "parameters": <the inputSchema>}
  - Sample with model.generate(system, contents, declarations); read the named calls with
    calls_in(turn_of(response)); a turn that names no call is the answer: text_in(...).
  - Check every call against its declaration before it is sent: a tool that is not
    declared, a missing or unknown argument, the wrong type. A failed check is a result
    the next turn reads, not an exception.
  - Send each call to the server that has the tool, with the customer from the ticket:
        client.call_tool(name, args, customer=customer_id)
    The customer never comes from the model.
  - Append the model's turn, then the results, to contents:
        {"role": "user", "parts": [{"functionResponse": {"name": ..., "response": {"result": ...}}}]}
"""
from src.agent.model import calls_in, text_in, turn_of
