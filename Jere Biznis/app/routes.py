import json
from datetime import datetime, timezone
from flask import Blueprint,current_app,jsonify,render_template,request
from .extensions import db
from .models import Institution,Membership,Subscription,Payment,AuditLog,SyncOperation
from .services.subscriptions import create_trial,apply_payment
from .services.billing import amount_for_months,current_status,login_reminder
from .security import canonical_checksum

api=Blueprint("jere_biznis_api",__name__)
web=Blueprint("jere_biznis_web",__name__, template_folder="../templates", static_folder="../static")

@web.get("/")
def home(): return render_template("dashboard.html")

@api.post("/institutions")
def create_institution():
    d=request.get_json(force=True)
    if any(not d.get(k) for k in ("name","institution_type","owner_user_id")):
        return jsonify(error="name, institution_type and owner_user_id are required"),400
    inst=Institution(name=d["name"],institution_type=d["institution_type"],owner_user_id=str(d["owner_user_id"]))
    db.session.add(inst); db.session.flush()
    db.session.add(Membership(institution_id=inst.id,user_id=inst.owner_user_id,role="INSTITUTION_OWNER"))
    db.session.add(create_trial(inst.id,current_app.config["INSTITUTION_MONTHLY_PRICE_GKACH"],
                                current_app.config["TRIAL_DURATION_DAYS"]))
    db.session.add(AuditLog(institution_id=inst.id,event_type="INSTITUTION_CREATED",
        actor_user_id=inst.owner_user_id,metadata_json=json.dumps({"trial_days":30})))
    db.session.commit()
    sub=Subscription.query.filter_by(institution_id=inst.id).first()
    return jsonify(institution_id=inst.id,status=sub.status,trial_end=sub.trial_end.isoformat(),
                   monthly_price_gkach=sub.monthly_price_gkach,login_reminder_required=True),201

@api.get("/institutions/<int:iid>/subscription")
def get_subscription(iid):
    Institution.query.get_or_404(iid)
    sub=Subscription.query.filter_by(institution_id=iid).first_or_404()
    now=datetime.now(timezone.utc)
    sub.status=current_status(now,sub.trial_end,sub.expiration)
    sub.last_verified_at=now
    db.session.commit()
    return jsonify(status=sub.status,monthly_price_gkach=sub.monthly_price_gkach,
        trial_end=sub.trial_end.isoformat(),expiration=sub.expiration.isoformat() if sub.expiration else None,
        reminder=login_reminder(now,sub.trial_end,sub.expiration),
        payment_required=sub.status=="EXPIRED")

@api.post("/institutions/<int:iid>/subscription/quote")
def quote(iid):
    sub=Subscription.query.filter_by(institution_id=iid).first_or_404()
    try: months=int(request.get_json(force=True)["months"]); amount=amount_for_months(months,sub.monthly_price_gkach)
    except Exception as e: return jsonify(error=str(e)),400
    return jsonify(months=months,monthly_price_gkach=sub.monthly_price_gkach,amount_gkach=amount)

@api.post("/institutions/<int:iid>/subscription/pay")
def pay(iid):
    inst=Institution.query.get_or_404(iid)
    d=request.get_json(force=True)
    try:
        months=int(d["months"]); idem=str(d["idempotency_key"]); tx=str(d["wallet_transaction_id"])
    except Exception as e: return jsonify(error=str(e)),400
    if months<1 or months>120: return jsonify(error="months must be 1..120"),400
    old=Payment.query.filter_by(idempotency_key=idem).first()
    if old: return jsonify(status="already_processed",transaction_id=old.transaction_id,amount_gkach=old.amount_gkach)
    sub=Subscription.query.filter_by(institution_id=iid).first_or_404()
    amount=amount_for_months(months,sub.monthly_price_gkach)
    # Integration boundary: real production code must verify/debit Gkach atomically here.
    payment=apply_payment(sub,iid,tx,idem,months,inst.owner_user_id)
    db.session.commit()
    return jsonify(status="success",months=months,amount_gkach=amount,
                   transaction_id=payment.transaction_id,expiration=sub.expiration.isoformat(),
                   receipt={"institution":inst.name,"months":months,"amount_gkach":amount,
                            "transaction_id":payment.transaction_id,"paid_at":payment.created_at.isoformat()}),201

@api.get("/institutions/<int:iid>/payments")
def payments(iid):
    Institution.query.get_or_404(iid)
    return jsonify([{"date":p.created_at.isoformat(),"months":p.months,
        "amount_gkach":p.amount_gkach,"transaction_id":p.transaction_id}
        for p in Payment.query.filter_by(institution_id=iid).order_by(Payment.created_at.desc()).all()])

@api.post("/institutions/<int:iid>/sync/push")
def sync_push(iid):
    Institution.query.get_or_404(iid)
    ops=request.get_json(force=True).get("operations",[])
    accepted=[]; duplicates=[]
    for op in ops:
        if int(op.get("institution_id"))!=iid: return jsonify(error="tenant isolation violation"),403
        if canonical_checksum(op.get("payload"))!=op.get("checksum"):
            return jsonify(error=f"checksum mismatch: {op.get('operation_id')}"),400
        if SyncOperation.query.filter_by(operation_id=op["operation_id"]).first():
            duplicates.append(op["operation_id"]); continue
        db.session.add(SyncOperation(
            operation_id=op["operation_id"],institution_id=iid,device_id=op["device_id"],
            user_id=op["user_id"],entity_type=op["entity_type"],entity_id=op["entity_id"],
            operation_type=op["operation_type"],payload=json.dumps(op.get("payload")),
            local_version=int(op.get("local_version",1)),base_version=int(op.get("base_version",0)),
            checksum=op["checksum"]))
        accepted.append(op["operation_id"])
    db.session.commit()
    return jsonify(accepted=accepted,duplicates=duplicates)

@api.get("/institutions/<int:iid>/sync/pull")
def sync_pull(iid):
    Institution.query.get_or_404(iid)
    rows=SyncOperation.query.filter_by(institution_id=iid).order_by(SyncOperation.id.asc()).all()
    return jsonify([{"operation_id":r.operation_id,"device_id":r.device_id,"user_id":r.user_id,
        "entity_type":r.entity_type,"entity_id":r.entity_id,"operation_type":r.operation_type,
        "payload":json.loads(r.payload),"local_version":r.local_version,
        "base_version":r.base_version,"checksum":r.checksum} for r in rows])
