from app import create_app

app = create_app('development')

with app.app_context():
    from flask import url_for
    print("=== Checking EVENTS blueprint ===")
    
    rules = [str(r) for r in app.url_map.iter_rules() if 'event' in str(r).lower()]
    print(f"\nEVENTS routes: {rules}")
    
    endpoints = [ep.rule for ep in app.url_map.iter_rules() if ep.endpoint.startswith('events.')]
    print(f"events.* endpoints: {endpoints}")
    
    try:
        url = url_for('events.index')
        print(f"\nurl_for('events.index') = {url}")
    except Exception as e:
        print(f"\nERROR url_for('events.index'): {type(e).__name__}: {e}")
    
    print("\n=== Rendering base template snippet ===")
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
        print("Template rendered OK!")
        print(result)
    except Exception as e:
        print(f"ERROR rendering template: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
