import subprocess
import sys
import os

HERE = r"c:\Users\Ops\OneDrive\Desktop\dev\Glory2YahPub - Copy"
os.chdir(HERE)
env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"}
env.pop("DATABASE_URL", None)
env.pop("FLASK_ENV", None)

r = subprocess.run(
    [sys.executable, "test_loggedin_ads_visible.py"],
    capture_output=True,
    text=True,
    env=env,
    timeout=300,
)

with open("_loggedin_tests_stdout.txt", "w", encoding="utf-8") as f:
    f.write(r.stdout or "")
with open("_loggedin_tests_stderr.txt", "w", encoding="utf-8") as f:
    f.write(r.stderr or "")

print("EXIT=", r.returncode)
print("STDOUT_LAST80:")
print("\n".join((r.stdout or "").splitlines()[-80:]))
print("STDERR_LAST80:")
print("\n".join((r.stderr or "").splitlines()[-80:]))
