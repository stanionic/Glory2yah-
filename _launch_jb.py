import subprocess, sys, os, time

os.environ['REDIS_URL'] = ''
os.environ['FLASK_ENV'] = 'development'
os.environ['SECRET_KEY'] = 'test-secret-123'
os.environ['ADMIN_PASSWORD'] = 'admin'
os.environ['ADMIN_WHATSAPP'] = '+50942882076'

log_path = '_server_log.txt'
with open(log_path, 'w', encoding='utf-8') as f:
    p = subprocess.Popen(
        [sys.executable, '_run_server.py'],
        stdout=f, stderr=subprocess.STDOUT,
        cwd=os.getcwd()
    )
    pid = p.pid
    print(f'DÉMARRAGE PID={pid}')
    time.sleep(12)
    poll = p.poll()
    if poll is not None:
        print(f'PROCESS TERMINÉ AVEC RC={poll}')
        p.wait()
    else:
        print(f'PROCESS EN COURS (PID={pid})')
    with open(log_path, 'r', encoding='utf-8') as f2:
        lines = f2.readlines()
        print(f'LOG ({len(lines)} lignes):')
        for line in lines[-80:]:
            print(line.rstrip())