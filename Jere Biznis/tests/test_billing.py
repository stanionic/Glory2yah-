from datetime import datetime,timedelta,timezone
from app.services.billing import amount_for_months,current_status,next_expiration
def test_prices():
 assert amount_for_months(1,500)==500 and amount_for_months(3,500)==1500
 assert amount_for_months(6,500)==3000 and amount_for_months(12,500)==6000
def test_trial():
 n=datetime(2026,9,8,tzinfo=timezone.utc); assert current_status(n,n+timedelta(days=30),None)=="TRIAL"
def test_extend():
 n=datetime(2026,9,8,tzinfo=timezone.utc); old=datetime(2026,12,31,tzinfo=timezone.utc)
 assert next_expiration(n,n+timedelta(days=30),old,3).date().isoformat()=="2027-03-31"
