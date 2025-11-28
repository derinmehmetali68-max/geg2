#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Otomatik veritabanı temizleme scripti (onay gerektirmez)
Railway'de kullanım için
"""

import os
import sys

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import app, init_database
from models import db

def clear_database_auto():
    """Tüm veritabanını temizle ve yeniden oluştur (otomatik)"""
    
    with app.app_context():
        try:
            print("🗑️  Veritabanı temizleniyor...")
            
            # Tüm tabloları drop et
            db.drop_all()
            print("✅ Tüm tablolar silindi")
            
            # Tabloları yeniden oluştur
            db.create_all()
            print("✅ Tablolar yeniden oluşturuldu")
            
            # Default verileri ekle
            print("📝 Default veriler ekleniyor...")
            init_database()
            print("✅ Default veriler eklendi")
            
            print("\n🎉 Veritabanı başarıyla temizlendi ve yeniden oluşturuldu!")
            return True
            
        except Exception as e:
            print(f"❌ Hata: {e}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == '__main__':
    success = clear_database_auto()
    sys.exit(0 if success else 1)

