import os, signal, subprocess, sys, time
import urllib.request

# Kill any python currently listening on 5000
out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True).stdout
pids = set()
for line in out.splitlines():
    if ":5000" in line and "LISTENING" in line:
        pids.add(line.split()[-1])
for pid in pids:
    if pid.isdigit() and int(pid) != os.getpid():
        try:
            os.kill(int(pid), signal.SIGTERM)
            print("killed old pid", pid)
        except Exception as e:
            print("kill fail", pid, e)
time.sleep(2)

env = dict(os.environ, PYTHONIOENCODING="utf-8")
log = open("_bp_srv.log", "w", encoding="utf-8")
proc = subprocess.Popen(
    [sys.executable, "-X", "utf8", "_bp_server_runner.py"],
    stdout=log, stderr=subprocess.STDOUT, env=env, cwd=os.getcwd(),
    creationflags=subprocess.DETACHED_PROCESS)
print("server pid", proc.pid)

for _ in range(60):
    time.sleep(2)
    try:
        code = urllib.request.urlopen("http://127.0.0.1:5000/health", timeout=3).status
        if code == 200:
            print("SERVER UP")
            sys.exit(0)
    except Exception:
        if proc.poll() is not None:
            print("SERVER DIED, log tail:")
            log.close()
            print(open("_bp_srv.log", encoding="utf-8", errors="replace").read()[-2000:])
            sys.exit(1)
print("TIMEOUT waiting for server")
sys.exit(1)
