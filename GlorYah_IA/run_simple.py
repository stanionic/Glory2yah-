#!/usr/bin/env python3
"""
Simple runner for MANDEMMAPBAW - No AI dependencies required
This version runs with fallback responses only
"""

import os
os.environ['USE_FALLBACK_ONLY'] = '1'

from app import app, init_db

if __name__ == '__main__':
    print("=" * 60)
    print("MANDEMMAPBAW - Simple Mode (Fallback Only)")
    print("=" * 60)
    print()
    print("Starting in fallback mode...")
    print("AI models will not be loaded.")
    print("The app will use fallback responses.")
    print()
    
    init_db()
    
    host = '0.0.0.0'
    port = 5000
    
    print(f"Starting server on http://{host}:{port}")
    print("Press Ctrl+C to stop")
    print()
    
    app.run(debug=True, host=host, port=port)
