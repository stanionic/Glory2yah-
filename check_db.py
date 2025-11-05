import sqlite3

conn = sqlite3.connect('instance/glory2yahpub.db')
cursor = conn.cursor()

# Get table info
cursor.execute('PRAGMA table_info(ads)')
columns = cursor.fetchall()
print('Columns in ads table:')
for col in columns:
    print(col)

# Get sample ads
cursor.execute('SELECT ad_id, title, description FROM ads LIMIT 5')
rows = cursor.fetchall()
print('\nSample ads:')
for row in rows:
    print(row)

conn.close()
