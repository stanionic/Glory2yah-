import os, subprocess, sys, time, socket

ROOT = r'c:\Users\Ops\OneDrive\Desktop\dev\Glory2YahPub - Copy'
env = dict(os.environ, PYTHONIOENCODING='utf-8')
out = open(os.path.join(ROOT, '_srv_konf_out.log'), 'w')
err = open(os.path.join(ROOT, '_srv_konf_err.log'), 'w')
p = subprocess.Popen(
    [os.path.join(ROOT, '.venv', 'Scripts', 'python.exe'), '-X', 'utf8', '_run_local.py'],
    cwd=ROOT, env=env, stdout=out, stderr=err,
    creationflags=0x00000200 | 0x00000008,  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
)
for _ in range(60):
    time.sleep(1)
    try:
        s = socket.create_connection(('127.0.0.1', 5000), timeout=1)
        s.close()
        print('SERVER_UP pid=%s' % p.pid)
        sys.exit(0)
    except OSError:
        continue
print('SERVER_DOWN pid=%s' % p.pid)
print(open(os.path.join(ROOT, '_srv_konf_err.log')).read()[-2000:])
sys.exit(1)
