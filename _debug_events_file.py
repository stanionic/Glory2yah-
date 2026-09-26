import sys
import traceback

log_file = r"c:\Users\Ops\OneDrive\Desktop\dev\Glory2YahPub - Copy\_debug_events_output.txt"

with open(log_file, "w") as f:
    try:
        f.write("=== IMPORT CREATE_APP\n")
        from app import create_app
        f.write("OK - create_app imported\n")
        app = create_app('development')
        f.write("OK - app created\n")
        
        with app.app_context():
            from flask import url_for
            f.write("\n=== CHECKING EVENTS BLUEPRINT\n")
            
            all_rules = [str(r) for r in app.url_map.iter_rules()]
            event_rules = [r for r in all_rules if 'event' in r.lower()]
            f.write(f"\nEVENTS routes: {event_rules}\n")
            
            all_endpoints = [ep.endpoint for ep in app.url_map.iter_rules()]
            event_endpoints = [e for e in all_endpoints if e.startswith('events.')]
            f.write(f"events.* endpoints: {event_endpoints}\n")
            
            try:
                url = url_for('events.index')
                f.write(f"\nurl_for('events.index') = {url}\n")
            except Exception as e:
                f.write(f"\nERROR url_for('events.index'): {type(e).__name__}: {e}\n")
                f.write(traceback.format_exc())
            
            f.write("\n=== ALL REGISTERED BLUEPRINTS\n")
            for bp_name, bp in app.blueprints.items():
                f.write(f"  - {bp_name}\n")
            
            f.write("\n=== TRYING DIRECT EVENTS IMPORT\n")
            try:
                from app.routes.events import events_bp, admin_events_bp
                f.write("OK - direct import of events_bp and admin_events_bp\n")
                f.write(f"  events_bp name: {events_bp.name}\n")
                f.write(f"  admin_events_bp name: {admin_events_bp.name}\n")
            except Exception as e:
                f.write(f"ERROR importing events: {type(e).__name__}: {e}\n")
                f.write(traceback.format_exc())
            
            f.write("\n=== RENDERING SERVICE ITEM TEMPLATE\n")
            from flask import render_template_string
            tmpl = """
            <a href="{{ url_for('events.index') }}" class="service-item">
                <span class="service-icon">🗓️</span>
                <span class="service-name">Evènman</span>
                <span class="service-desc">SOS ALO LEGLIZ</span>
            </a>
            """
            try:
                result = render_template_string(tmpl)
                f.write("Template rendered OK!\n")
                f.write(result + "\n")
            except Exception as e:
                f.write(f"ERROR rendering template: {type(e).__name__}: {e}\n")
                f.write(traceback.format_exc())
                
    except Exception as e:
        f.write(f"\nFATAL ERROR: {type(e).__name__}: {e}\n")
        f.write(traceback.format_exc())

print(f"Done. Output written to {log_file}")
