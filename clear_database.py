#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Veritabanını temizleme scripti
Tüm tabloları drop edip yeniden oluşturur ve default verileri ekler
"""

import os
import sys

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import app, init_database
from models import db, User, Book, Member, Transaction, Category, Settings, Notification, EmailTemplate, Reservation, OnlineBorrowRequest

def clear_database():
    """Tüm veritabanını temizle ve yeniden oluştur"""
    
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
            print("\n📊 Varsayılan Admin Kullanıcı:")
            print("   Kullanıcı adı: admin")
            print("   Şifre: admin123")
            print("\n⚠️  ÖNEMLİ: İlk girişten sonra şifreyi değiştirin!")
            
            return True
            
        except Exception as e:
            print(f"❌ Hata: {e}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == '__main__':
    # Onay iste
    print("⚠️  UYARI: Bu işlem tüm veritabanını silecek!")
    print("   - Tüm kitaplar silinecek")
    print("   - Tüm üyeler silinecek")
    print("   - Tüm işlemler silinecek")
    print("   - Tüm ayarlar silinecek")
    print("   - Sadece default veriler kalacak")
    print()
    
    confirm = input("Devam etmek istiyor musunuz? (evet/hayır): ").strip().lower()
    
    if confirm in ['evet', 'e', 'yes', 'y']:
        success = clear_database()
        sys.exit(0 if success else 1)
    else:
        print("❌ İşlem iptal edildi.")
        sys.exit(1)

