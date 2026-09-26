# Architecture
Primary Admin device: local operational DB + IndexedDB/PWA + offline queue.
Online: delta synchronization with server.
Server: institution metadata, subscription authority, payment records, sync ledger and audit.
Gkach: existing wallet/transaction engine via adapter.
Backup Admin: encrypted replica only.
