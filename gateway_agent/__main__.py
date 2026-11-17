"""CLI:  python -m gateway_agent enroll|run|status --data-dir DIR --cloud-url URL"""
import argparse
import json
import sys
import time

from .agent import GatewayAgent
from .client import CloudRejected, UrllibTransport


def main(argv=None):
    p = argparse.ArgumentParser(prog='gateway_agent')
    p.add_argument('command', choices=['enroll', 'run', 'status', 'portal'])
    p.add_argument('--data-dir', required=True)
    p.add_argument('--cloud-url', required=True)
    p.add_argument('--token', help='one-time enrollment token (enroll)')
    p.add_argument('--interval', type=int, default=30)
    p.add_argument('--insecure-http', action='store_true', help='testing only')
    p.add_argument('--portal-host', default='0.0.0.0')
    p.add_argument('--portal-port', type=int, default=8080)
    p.add_argument('--access', choices=['none', 'ndsctl'], default='none')
    a = p.parse_args(argv)
    agent = GatewayAgent(a.data_dir, a.cloud_url,
                         transport=UrllibTransport(allow_insecure=a.insecure_http))
    if a.command == 'enroll':
        try:
            out = agent.enroll(a.token or '')
        except CloudRejected as e:
            print(f'Enrollment failed: {e}', file=sys.stderr)
            return 1
        print(json.dumps({'gateway_uid': out['gateway_uid'], 'vendor_uid': out['vendor_uid']}))
    elif a.command == 'status':
        print(json.dumps(agent.status(), indent=2))
    elif a.command == 'portal':
        from socketserver import ThreadingMixIn
        from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server
        from .portal.access import ArpMacResolver, NdsctlController, RecordingController
        from .portal.app import PortalApp

        class _Threaded(ThreadingMixIn, WSGIServer):
            daemon_threads = True

        class _Quiet(WSGIRequestHandler):
            def log_message(self, *args):        # never log request lines (no codes in logs)
                pass
        access = NdsctlController() if a.access == 'ndsctl' else RecordingController()
        srv = make_server(a.portal_host, a.portal_port, PortalApp(agent.engine, access,
                          ArpMacResolver()), server_class=_Threaded, handler_class=_Quiet)
        print(f'portal on {a.portal_host}:{a.portal_port} access={a.access}')
        srv.serve_forever()
    else:
        delay = 1
        while True:
            res = agent.run_once()
            delay = a.interval if res.get('online') else min(delay * 2, 300)  # backoff offline
            time.sleep(delay)
    return 0


if __name__ == '__main__':
    sys.exit(main())
