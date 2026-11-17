# make-it-act

AI Systems Engineering, P3. A refund agent on its own tool servers: it refunds a duplicate
charge exactly once, waits for a person before a large refund, and survives being killed.

**The assignment is [PROJECT.md](PROJECT.md).**

```bash
uv sync
cp .env.example .env        # your Gemini key
uv run check_server.py      # your payments server
uv run local.py T01         # one ticket, on your laptop
./deploy.sh                 # to your Learner Lab account
```

Files marked YOURS at the top are the project: `src/servers/payments.py`,
`src/agent/loop.py`, `src/agent/prompt.py`, `src/agent/runs.py`, `score.py`.
Everything else is given.
