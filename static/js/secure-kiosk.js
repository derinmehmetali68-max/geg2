// Kiosk sistemi yer tutucusu - artık advanced-kiosk.js kullanılıyor
console.log('✅ Secure Kiosk: Advanced Kiosk sistemi kullanılıyor');

// Eğer hala secure-kiosk.js'e referans varsa, bunları advanced-kiosk'e yönlendir
if (typeof window.SecureKioskSystem === 'undefined') {
    window.SecureKioskSystem = function() {
        console.log('SecureKioskSystem başlatılıyor, advanced-kiosk.js kullanılıyor');
        return null;
    };
}
