class GkachError(Exception):
    pass

class GkachAdapter:
    def debit_for_subscription(self, *, wallet_user_id, institution_id, amount_gkach, idempotency_key):
        raise GkachError(
            "Connect this adapter to the existing Glory2YahPub Gkach wallet service."
        )
