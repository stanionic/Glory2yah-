# Backup Recovery
Owner controls backups. Backup Admin/Data Custodian may retain encrypted copies but has no CRUD
or cleartext access. Recovery: authenticate -> verify ownership -> verify backup integrity ->
decrypt -> restore local DB -> register new master device -> revoke old device.
