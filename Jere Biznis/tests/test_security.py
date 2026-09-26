import os
from app.security import encrypt_backup,decrypt_backup,canonical_checksum
def test_encryption():
 k=os.urandom(32); data=b"secret"; n,c=encrypt_backup(data,k); assert decrypt_backup(n,c,k)==data and c!=data
def test_checksum():
 assert canonical_checksum({"b":2,"a":1})==canonical_checksum({"a":1,"b":2})
