"""Insert 2 sample APPROVED video ADS into SQLite for debugging video loading bug.
Renders pages via test_client + NDJSON logs + writes HTML + writes debug summary.
"""
import os, json, sys, time, uuid, threading
from datetime import datetime, timedelta
sys.path.insert(0, os.path.abspath('.'))
from app import create_app, db

_DBG = '.dbg/trae-debug-log-publish-video-not-loading.ndjson'
_DBG_LOCK = threading.Lock()
def _vlog(h, m, d=None, r='pre', loc='_seed_video_ads.py'):
    try:
        p = {'sessionId':'publish-video-not-loading','runId':r,'hypothesisId':h,'location':loc,
             'msg':'[DEBUG] '+m,'data':d or {},'ts':int(time.time()*1000)}
        with _DBG_LOCK:
            os.makedirs('.dbg', exist_ok=True)
            with open(_DBG,'a',encoding='utf-8') as f:
                f.write(json.dumps(p)+'\n')
    except Exception: pass

app = create_app('development')
with app.app_context():
    # Ensure tables
    try:
        db.create_all()
    except Exception as e:
        print(f'create_all warn: {e}')
    from app.models.ad import Ad
    from app.models.user import User
    # Ensure a test user (whatsapp = +50911111111, user_whatsapp for ownership)
    u = User.query.filter_by(whatsapp='+50911111111').first()
    if not u:
        u = User(whatsapp='+50911111111', pseudo='UserTest', password_hash='pbkdf2:sha256:1000$xx')
        try: db.session.add(u); db.session.commit()
        except Exception: db.session.rollback()
    uid = u.whatsapp
    # Fake a video filename (static/uploads doesn't need to exist for HTML test)
    video_name_1 = 'sample-video-1.mp4'
    video_name_2 = 'sample-video-2.mp4'
    # Insert/update 2 APPROVED video ads if missing
    ad1_id = 'AD-VIDEO-00001'
    ad2_id = 'AD-VIDEO-00002'
    # Ensure not exist
    for (aid, title, desc, cat, price, qty) in [
        (ad1_id, 'Test Videyo 1 30s - Konsèy Jadinaj', 'Yon videyo ki montre fason pou plante nan pwòp lakay ou (dizèn segonn).', 'other', 0, 0),
        (ad2_id, 'Test Videyo 2 - Vèsè Jou a Jan 3:16', 'Pou tout moun ki vle tann bon nouvèl la, vèsè jou a, videyo 30 segonn.', 'other', 0, 0),
    ]:
        a = Ad.query.filter_by(ad_id=aid).first()
        if not a:
            ad = Ad(ad_id=aid, user_whatsapp=uid, title=title, description=desc,
                    media_type='video', images=None, video=video_name_1 if aid==ad1_id else video_name_2,
                    ad_type='publish', price_gkach=price, quantity=qty, category=cat,
                    admin_status='approved', payment_status='paid', publish_fee_gkach=1000,
                    created_at=datetime.utcnow() - timedelta(hours=3))
            try:
                db.session.add(ad); db.session.commit()
                _vlog('H1', f'INSERT video AD approved {aid}', {'ad_id':aid,'title':title,'video':ad.video}, r='post')
            except Exception as e:
                db.session.rollback()
                _vlog('H1', f'FAILED insert {aid}', {'error':str(e)}, r='post')
        else:
            a.admin_status='approved'
            a.payment_status='paid'
            a.media_type='video'
            a.video = video_name_1 if aid==ad1_id else video_name_2
            try:
                db.session.commit()
                _vlog('H1', f'UPDATED existing {aid} → approved + video={a.video}', {'ad_id':aid,'video':a.video}, r='post')
            except Exception as e:
                db.session.rollback()

    # Now render via test_client
    client = app.test_client()
    PAGES = [('/', 'home.html'),
             ('/mache/', 'mache.html'),
             ('/submit_ad', 'submit_ad.html'),
             (f'/ad/{ad1_id}', f'ad_{ad1_id}.html')]
    os.makedirs('_dbg_pages', exist_ok=True)
    for path, fn in PAGES:
        try:
            t0 = time.time()
            resp = client.get(path, follow_redirects=True)
            ms = int((time.time()-t0)*1000)
            html_bytes = resp.data or b''
            html_text = html_bytes.decode('utf-8', errors='ignore')
            out = os.path.join('_dbg_pages', fn)
            with open(out,'w',encoding='utf-8') as f:
                f.write(html_text)
            # quick heuristics: <video>, <iframe>, product cards, empty state
            cnt_video = html_text.count('<video')
            cnt_source_video = html_text.count('video[src') + html_text.count('src="/static/uploads/sample-video')
            cnt_pwodui = html_text.count('pwodui')
            cnt_empty = html_text.count('Pa gen pwodui') or html_text.count('Pa gen piblisite')
            _vlog('H2', f'GET {path} status={resp.status_code} bytes={len(html_bytes)} ms={ms}',
                  {'path':path,'status':resp.status_code,'bytes':len(html_bytes),'ms':ms,
                   'video_tag_count':cnt_video,'sample_video_src_count':cnt_source_video,
                   'pwodui_txt':cnt_pwodui,'empty_state_present':bool(cnt_empty)},
                  r='post', loc='_seed_video_ads.py')
        except Exception as e:
            _vlog('H4', f'GET {path} FAILED', {'path':path,'error':str(e)}, r='post')

    summary = {
        'video_ads_count_in_approved': len([a for a in Ad.query.filter_by(admin_status='approved').all() if a.media_type=='video']),
        'all_approved_count': Ad.query.filter_by(admin_status='approved').count(),
        'sample_video_ads_exist': [a.ad_id for a in Ad.query.filter(Ad.ad_id.in_([ad1_id,ad2_id])).all()],
    }
    try:
        with open('_dbg_pages/_video_seed_summary.json','w',encoding='utf-8') as f:
            json.dump(summary,f,indent=2)
        _vlog('H1','seed summary', summary, r='post')
    except Exception: pass
    print('DONE', summary)
