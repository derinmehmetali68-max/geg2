#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os
import traceback
import webbrowser
from threading import Timer

def open_browser():
    """5 saniye bekleyip tarayıcıyı aç"""
    webbrowser.open('http://localhost:5000')

def main():
    print("="*60)
    print("KÜTÜPHANE YÖNETİM SİSTEMİ")
    print("="*60)
    print("Python Sürümü:", sys.version)
    print("Çalışma Dizini:", os.getcwd())
    print("-"*60)
    
    try:
        # Flask uygulamasını import et ve başlat
        print("Flask uygulaması başlatılıyor...")
        
        # app modülünü import et
        from app import app
        
        print("Sunucu başlatılıyor...")
        print("-"*60)
        print("Web arayüzü: http://localhost:5000")
        print("Çıkmak için: Ctrl+C")
        print("-"*60)
        
        # 5 saniye sonra tarayıcıyı aç
        timer = Timer(5, open_browser)
        timer.daemon = True
        timer.start()
        
        # Flask uygulamasını çalıştır
        app.run(host='0.0.0.0', port=5000, debug=False)
        
    except ImportError as e:
        print("\n!!! IMPORT HATASI !!!")
        print(f"Modül yüklenemedi: {e}")
        print("\nDetaylı hata:")
        print(traceback.format_exc())
        print("\nLütfen gerekli modüllerin kurulu olduğundan emin olun.")
        input("\nDevam etmek için Enter tuşuna basın...")
        sys.exit(1)
        
    except Exception as e:
        print("\n!!! HATA !!!")
        print(f"Hata türü: {type(e).__name__}")
        print(f"Hata mesajı: {e}")
        print("\nDetaylı hata:")
        print(traceback.format_exc())
        input("\nDevam etmek için Enter tuşuna basın...")
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nProgram kullanıcı tarafından durduruldu.")
        print("Güle güle!")
        sys.exit(0)