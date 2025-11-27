import sys
import os
import traceback
import time

def main():
    try:
        # Import ana modülü
        import main
        main.main()
    except Exception as e:
        print("\n" + "="*60)
        print("HATA OLUŞTU!")
        print("="*60)
        print(f"Hata Tipi: {type(e).__name__}")
        print(f"Hata Mesajı: {str(e)}")
        print("\nDetaylı Hata:")
        print(traceback.format_exc())
        print("="*60)
        print("\nProgram 30 saniye sonra kapanacak...")
        time.sleep(30)
        sys.exit(1)

if __name__ == "__main__":
    try:
        print("Kütüphane Yönetim Sistemi başlatılıyor...")
        print("Python sürümü:", sys.version)
        print("Çalışma dizini:", os.getcwd())
        print("-"*60)
        main()
    except KeyboardInterrupt:
        print("\nProgram kullanıcı tarafından sonlandırıldı.")
        sys.exit(0)
    except Exception as e:
        print("\n" + "="*60)
        print("KRİTİK HATA!")
        print("="*60)
        print(f"Hata: {e}")
        print(traceback.format_exc())
        print("="*60)
        input("\nDevam etmek için Enter tuşuna basın...")
        sys.exit(1)