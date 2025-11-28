#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cumhuriyet Anadolu Lisesi Kütüphane Yönetim Sistemi
Railway Production Deployment

Ana uygulama dosyası - Sadece mevcut modülleri import eder.
"""

import os
import sys

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import basic configuration
from config import app, init_app

# Import all models (this creates the database tables)
from models import *

# Import all utility functions
from utils import *

# Import all routes (web pages)
from routes import *

# Import all API endpoints
from api import *
from api_extended import *

# Kiosk routes (optional)
try:
    from api_kiosk import register_kiosk_routes
    register_kiosk_routes(app)
    print("✅ Kiosk routes registered!")
except ImportError:
    print("⚠️ Kiosk routes not available")

# Clear database API endpoint
try:
    from api_clear_database import clear_db_bp
    app.register_blueprint(clear_db_bp)
    print("✅ Clear database API registered!")
except ImportError:
    print("⚠️ Clear database API not available")

def main():
    """Ana uygulama fonksiyonu"""
    
    # Railway production check
    if os.environ.get('RAILWAY_ENVIRONMENT'):
        print("🚂 Railway Production Environment Detected")
        app.config['DEBUG'] = False
        
        # Database setup
        with app.app_context():
            try:
                from models import db
                db.create_all()
                print("✅ Database tables created/verified")
            except Exception as e:
                print(f"❌ Database error: {e}")
        
        # Run with gunicorn (Railway will handle this)
        port = int(os.environ.get('PORT', 5000))
        print(f"🚀 Starting on port {port}")
        
    else:
        # Local development
        print("🔧 Local Development Environment")
        app.run(debug=True, host='0.0.0.0', port=5000)

if __name__ == '__main__':
    main()
