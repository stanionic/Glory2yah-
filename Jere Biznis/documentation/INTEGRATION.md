# Integration
This module is standalone because the real Glory2YahPub source was not attached.
For production: reuse the existing Flask app factory, auth, database/migrations, Gkach wallet,
permissions, PWA and notifications. Replace the Gkach adapter/payment boundary with the real
atomic debit service. The server must calculate the amount, verify the wallet transaction,
enforce idempotency/replay protection, and only then activate the subscription.
