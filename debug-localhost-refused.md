# Debug Session: localhost-refused

Status: OPEN

Symptom:
- `http://localhost:8080` returns connection refused.

Expected:
- Flask app listens on port `8080` and serves the home page.

Hypotheses:
- H1: The startup script exits before the server bind call is reached.
- H2: An import-time side effect or environment mismatch aborts the process without a visible traceback.
- H3: The app blocks during initialization and never reaches the socket bind step.
- H4: The chosen runner (`run.py` or `simple_start.py`) is incompatible with the current environment.
- H5: A dependency/runtime mismatch inside the repaired virtualenv causes silent termination during launch.

Evidence Log:
- Pending.

Next Step:
- Collect runtime evidence with minimal instrumentation only.
