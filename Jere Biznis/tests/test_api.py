def make(client):
 r=client.post("/api/v1/institutions",json={"name":"École Test","institution_type":"school","owner_user_id":"u1"})
 assert r.status_code==201; return r.get_json()["institution_id"]
def test_trial_reminder(client):
 i=make(client); d=client.get(f"/api/v1/institutions/{i}/subscription").get_json()
 assert d["status"]=="TRIAL" and d["monthly_price_gkach"]==500 and d["reminder"]["required"]
def test_quote(client):
 i=make(client); d=client.post(f"/api/v1/institutions/{i}/subscription/quote",json={"months":12}).get_json()
 assert d["amount_gkach"]==6000
def test_idempotency(client):
 i=make(client); p={"months":3,"idempotency_key":"idem-1","wallet_transaction_id":"tx-1"}
 assert client.post(f"/api/v1/institutions/{i}/subscription/pay",json=p).status_code==201
 assert client.post(f"/api/v1/institutions/{i}/subscription/pay",json=p).get_json()["status"]=="already_processed"
