from app import create_app

a = create_app()
a.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
