import os, sys, traceback
os.environ.setdefault('FLASK_ENV','development')
try:
    from app import create_app, socketio
    app = create_app('development')
    rules = sorted([r.rule for r in app.url_map.iter_rules() if 'notification' in r.rule.lower() or 'push' in r.rule.lower()])
    with open('_notif_verify.txt','w',encoding='utf-8') as f:
        f.write('APP CREATED OK\n')
        f.write('Notification/Push routes:\n')
        for r in rules: f.write(f' - {r}\n')
        f.write(f'Total routes: {len(list(app.url_map.iter_rules()))}\n')
        from app.services.notification_hub import NotificationHub
        lbl = NotificationHub.category_label('gkach','ht')
        f.write(f'category_label test: gkach/ht => {lbl}\n')
        lbl2 = NotificationHub.category_label('orders','fr')
        f.write(f'category_label test: orders/fr => {lbl2}\n')
    print('OK - see _notif_verify.txt')
except Exception as e:
    with open('_notif_verify.txt','w',encoding='utf-8') as f:
        traceback.print_exc(file=f)
    traceback.print_exc()
    sys.exit(1)
