import os, sqlite3, glob
# Find the dev sqlite db
candidates = ['instance/glory2yahpub_dev.db', 'glory2yahpub_dev.db', 'instance/app.db']
dbfile = None
for c in candidates:
    if os.path.exists(c):
        dbfile = c
        break
if not dbfile:
    # search
    for pat in ['instance/*.db', '*.db']:
        found = glob.glob(pat)
        if found:
            dbfile = found[0]
            break
print("DB file:", dbfile)
if not dbfile:
    import sys; sys.exit("no db found")
conn = sqlite3.connect(dbfile)
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ads'")
if c.fetchone():
    c.execute("SELECT count(*) FROM ads")
    print("ads total:", c.fetchone()[0])
    try:
        c.execute("SELECT ad_id,title,ad_type,admin_status FROM ads WHERE ad_id LIKE 'DEMO%'")
        for r in c.fetchall():
            print(r)
    except Exception as e:
        print("err:", e)
else:
    print("no ads table in", dbfile)
conn.close()
