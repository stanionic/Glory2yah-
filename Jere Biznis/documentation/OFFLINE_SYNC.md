# Offline Sync
Use IndexedDB for local operational state and a durable operation queue.
Operation fields: operation_id, institution_id, device_id, user_id, entity_type, entity_id,
operation_type, payload, timestamp, local_version, base_version, checksum, sync_status, retry_count.
Push/pull must be resumable, idempotent, checksum-verified and tenant-isolated.
