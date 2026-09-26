import sqlite3

c = sqlite3.connect('instance/glory2yahpub_dev.db')
c.row_factory = sqlite3.Row
cols = [r[1] for r in c.execute("PRAGMA table_info(konferans_rooms)")]
print('columns:', cols)
print('---')
for r in c.execute("SELECT * FROM konferans_rooms WHERE room_code='4307MI'"):
    for k in r.keys():
        v = r[k]
        if k == 'password':
            v = '<set>' if v else None
        print(f'  {k:22} = {v!r}')
print('--- all rooms ---')
for r in c.execute("SELECT room_id, room_code, room_name, is_active, user_id, creator_name, (password IS NOT NULL AND password!='') AS has_pw FROM konferans_rooms"):
    print(dict(r))
c.close()
