"""The model: one HTTP POST to the Gemini API. Given.

Every live response made during a run is recorded in the recordings table, keyed by the run,
so run_suite.py can save it and replay the run later with no model and no key.

    model = Model()
    response = model.generate(system, contents, declarations)

Replay: replay(responses) makes the next generate() calls return those responses, in order.
"""
import json, os, time, urllib.error, urllib.request

from src import crash
from src.store import table

BASE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
_replay = None


def replay(responses):
    global _replay
    _replay = list(responses) if responses is not None else None


class Model:
    def generate(self, system, contents, declarations=None):
        if _replay is not None:
            if not _replay:
                raise RuntimeError("replay: no recorded response left for this call")
            return _replay.pop(0)
        request = {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents}
        if declarations:
            request["tools"] = [{"functionDeclarations": declarations}]
        response = self.post(request)
        run_id = crash.current_run.get()
        if run_id:
            table("recordings").put({"id": f"{run_id}:{time.time_ns()}", "response": response})
        return response

    def post(self, request, attempts=6):
        body = json.dumps(request).encode()
        headers = {"Content-Type": "application/json", "x-goog-api-key": os.environ["GEMINI_API_KEY"]}
        started = time.monotonic()
        for attempt in range(attempts):
            try:
                req = urllib.request.Request(BASE.format(model=MODEL), body, headers)
                with urllib.request.urlopen(req, timeout=60) as r:
                    response = json.load(r)
                response["latency_ms"] = int((time.monotonic() - started) * 1000)   # ours, not the API's
                return response
            except urllib.error.HTTPError as e:
                if e.code not in (429, 500, 503) or attempt == attempts - 1:
                    raise RuntimeError(f"{e.code}: {e.read().decode()[:400]}")
            except (urllib.error.URLError, TimeoutError):
                if attempt == attempts - 1:
                    raise
            time.sleep(min(2 ** attempt, 30))


def turn_of(response):
    candidates = response.get("candidates") or [{}]
    return candidates[0].get("content", {"role": "model", "parts": []})


def calls_in(turn):
    return [{"name": p["functionCall"]["name"], "args": p["functionCall"].get("args", {})}
            for p in turn.get("parts", []) if "functionCall" in p]


def text_in(turn):
    return "".join(p.get("text", "") for p in turn.get("parts", []) if not p.get("thought")).strip()


def input_tokens(response):
    return response.get("usageMetadata", {}).get("promptTokenCount", 0)
