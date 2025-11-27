#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cumhuriyet Anadolu Lisesi Kütüphane Yönetim Sistemi
Modüler Yapı - Ana Uygulama Dosyası

Bu dosya tüm modülleri bir araya getirir ve Flask uygulamasını başlatır.
Kod artık 5 modüle bölünmüştür:

1. config.py - Uygulama konfigürasyonu ve başlangıç ayarları
2. models.py - Veritabanı modelleri (SQLAlchemy)  
3. routes.py - Web sayfaları ve ana route'lar
4. api.py - Temel API endpoint'leri
5. api_extended.py - Ek API endpoint'leri
6. utils.py - Yardımcı fonksiyonlar ve servisler

Her modül yaklaşık 800-1000 satır koddan oluşur.
"""

import os
import sys

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Enhanced imports with fallback
try:
    from config_enhanced import app, db, login_manager, mail, csrf, cache, socketio, limiter
    enhanced_config = True
    print("✅ Enhanced configuration loaded!")
except ImportError:
    from config import app, init_app
    enhanced_config = False
    print("Warning: Using basic configuration")

# AI Engine
try:
    from ai_engine import get_ai_engine, initialize_ai_engine
    ai_available = True
    print("✅ AI Engine available!")
except ImportError:
    ai_available = False
    print("Warning: AI Engine not available")

# Celery Tasks
try:
    from celery_tasks import send_overdue_notifications, backup_database, generate_reports
    celery_available = True
    print("✅ Celery tasks available!")
except ImportError:
    celery_available = False
    print("Warning: Celery tasks not available")

# Import all models (this creates the database tables)
from models import *

# Import all utility functions
from utils import *

# Import all routes (web pages)
from routes import *

# Import all API endpoints
from api import *
from api_extended import *

# Enhanced routes
try:
    from routes_enhanced import register_enhanced_routes
    enhanced_routes_available = True
    print("✅ Enhanced routes available!")
    # Enhanced routes'ları register et
    register_enhanced_routes(app)
    print("✅ Enhanced routes registered!")
except ImportError:
    enhanced_routes_available = False
    print("Warning: Enhanced routes not available")

# Kiosk routes
try:
    from api_kiosk import register_kiosk_routes
    kiosk_routes_available = True
    print("✅ Kiosk routes available!")
    # Kiosk routes'ları register et
    register_kiosk_routes(app)
    print("✅ Kiosk routes registered!")
except ImportError:
    kiosk_routes_available = False
    print("Warning: Kiosk routes not available")

def main():
    """Ana uygulama fonksiyonu"""
    
    # Railway production check
    if os.environ.get('RAILWAY_ENVIRONMENT'):
        print("🚂 Railway Production Environment Detected")
        app.config['DEBUG'] = False
        
        # Database setup
        with app.app_context():
            try:
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
