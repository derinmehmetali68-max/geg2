/**
 * PWA ve Modern JavaScript Özellikleri
 * Service Worker, Push Notifications, Offline Support
 */

// Service Worker Registration
if ('serviceWorker' in navigator) {
    window.addEventListener('load', function() {
        navigator.serviceWorker.register('/sw.js')
            .then(function(registration) {
                console.log('✅ Service Worker kayıtlı:', registration.scope);
                
                // Push notification desteği kontrol et
                if ('PushManager' in window) {
                    initializePushNotifications(registration);
                }
            })
            .catch(function(error) {
                console.log('❌ Service Worker kaydı başarısız:', error);
            });
    });
}

// Push Notifications
async function initializePushNotifications(registration) {
    try {
        const permission = await Notification.requestPermission();
        
        if (permission === 'granted') {
            console.log('✅ Bildirim izni verildi');
            
            // VAPID public key (production'da environment variable'dan alınmalı)
            const vapidPublicKey = 'your-vapid-public-key-here';
            
            const subscription = await registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: urlBase64ToUint8Array(vapidPublicKey)
            });
            
            // Subscription'ı sunucuya gönder
            await fetch('/api/push/subscribe', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(subscription)
            });
            
            console.log('✅ Push notification aboneliği oluşturuldu');
        }
    } catch (error) {
        console.error('❌ Push notification hatası:', error);
    }
}

// VAPID key conversion utility
function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding)
        .replace(/-/g, '+')
        .replace(/_/g, '/');

    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);

    for (let i = 0; i < rawData.length; ++i) {
        outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
}

// Enhanced PWA Install Manager
class PWAInstallManager {
    constructor() {
        this.deferredPrompt = null;
        this.isInstalled = false;
        this.installButton = null;
        
        this.init();
    }
    
    init() {
        // Check if already installed
        this.checkInstallStatus();
        
        // Listen for install prompt
        window.addEventListener('beforeinstallprompt', this.handleBeforeInstallPrompt.bind(this));
        
        // Listen for app installed
        window.addEventListener('appinstalled', this.handleAppInstalled.bind(this));
        
        // Check for iOS Safari add to home screen
        this.checkIOSInstall();
    }
    
    checkInstallStatus() {
        // Check if running in standalone mode
        if (window.matchMedia('(display-mode: standalone)').matches) {
            this.isInstalled = true;
            console.log('✅ PWA zaten yüklü (standalone mode)');
            return;
        }
        
        // Check for iOS Safari standalone
        if (window.navigator.standalone === true) {
            this.isInstalled = true;
            console.log('✅ PWA zaten yüklü (iOS Safari)');
            return;
        }
        
        // Check localStorage for install status
        if (localStorage.getItem('pwa-installed') === 'true') {
            this.isInstalled = true;
            console.log('✅ PWA yükleme durumu: Yüklü');
        }
    }
    
    handleBeforeInstallPrompt(e) {
        console.log('📱 PWA yükleme prompt'u hazır');
        
        // Prevent the mini-infobar from appearing on mobile
        e.preventDefault();
        
        // Stash the event so it can be triggered later
        this.deferredPrompt = e;
        
        // Show install button if not already installed
        if (!this.isInstalled) {
            this.showInstallPrompt();
        }
    }
    
    handleAppInstalled(e) {
        console.log('✅ PWA başarıyla yüklendi!');
        this.isInstalled = true;
        localStorage.setItem('pwa-installed', 'true');
        
        // Hide install button
        this.hideInstallButton();
        
        // Show success message
        this.showInstallSuccessMessage();
        
        // Clear the deferredPrompt
        this.deferredPrompt = null;
    }
    
    showInstallPrompt() {
        // Create enhanced install prompt
        this.createEnhancedInstallPrompt();
        
        // Show after a delay to not be intrusive
        setTimeout(() => {
            if (!this.isInstalled && this.deferredPrompt) {
                this.showInstallButton();
            }
        }, 5000); // 5 second delay
    }
    
    createEnhancedInstallPrompt() {
        // Create a more attractive install prompt
        const promptHtml = `
            <div id="pwa-install-banner" class="alert alert-info alert-dismissible position-fixed" style="top: 10px; right: 10px; z-index: 1050; max-width: 350px; display: none;">
                <div class="d-flex align-items-center">
                    <div class="me-3">
                        <i class="bi bi-phone display-6 text-primary"></i>
                    </div>
                    <div class="flex-grow-1">
                        <h6 class="alert-heading mb-1">Uygulamayı Yükle</h6>
                        <p class="mb-2 small">Kütüphane sistemini telefonunuza yükleyerek daha hızlı erişim sağlayın!</p>
                        <div class="d-grid gap-1 d-md-flex">
                            <button class="btn btn-primary btn-sm" id="install-pwa-btn">
                                <i class="bi bi-download"></i> Yükle
                            </button>
                            <button class="btn btn-outline-secondary btn-sm" id="dismiss-install-btn">
                                Daha Sonra
                            </button>
                        </div>
                    </div>
                </div>
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        
        // Add to page if not exists
        if (!document.getElementById('pwa-install-banner')) {
            document.body.insertAdjacentHTML('beforeend', promptHtml);
            
            // Add event listeners
            document.getElementById('install-pwa-btn').addEventListener('click', this.installPWA.bind(this));
            document.getElementById('dismiss-install-btn').addEventListener('click', this.dismissInstallPrompt.bind(this));
        }
    }
    
    showInstallButton() {
        const banner = document.getElementById('pwa-install-banner');
        if (banner && !this.isInstalled) {
            banner.style.display = 'block';
            
            // Auto-hide after 15 seconds
            setTimeout(() => {
                if (banner.style.display === 'block') {
                    banner.style.display = 'none';
                }
            }, 15000);
        }
    }
    
    hideInstallButton() {
        const banner = document.getElementById('pwa-install-banner');
        if (banner) {
            banner.style.display = 'none';
        }
    }
    
    dismissInstallPrompt() {
        this.hideInstallButton();
        
        // Don't show again for 7 days
        const dismissTime = new Date().getTime() + (7 * 24 * 60 * 60 * 1000);
        localStorage.setItem('pwa-install-dismissed', dismissTime.toString());
    }
    
    async installPWA() {
        if (!this.deferredPrompt) {
            console.log('❌ Install prompt mevcut değil');
            return;
        }
        
        try {
            // Show the install prompt
            this.deferredPrompt.prompt();
            
            // Wait for the user to respond to the prompt
            const { outcome } = await this.deferredPrompt.userChoice;
            
            console.log(`👤 Kullanıcı seçimi: ${outcome}`);
            
            if (outcome === 'accepted') {
                console.log('✅ Kullanıcı PWA yüklemeyi kabul etti');
                this.hideInstallButton();
            } else {
                console.log('❌ Kullanıcı PWA yüklemeyi reddetti');
                this.dismissInstallPrompt();
            }
            
            // Clear the deferredPrompt
            this.deferredPrompt = null;
            
        } catch (error) {
            console.error('❌ PWA yükleme hatası:', error);
        }
    }
    
    checkIOSInstall() {
        // Check for iOS Safari
        const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
        const isInStandaloneMode = window.navigator.standalone === true;
        
        if (isIOS && !isInStandaloneMode && !this.isInstalled) {
            // Show iOS-specific install instructions
            setTimeout(() => {
                this.showIOSInstallInstructions();
            }, 10000); // Show after 10 seconds
        }
    }
    
    showIOSInstallInstructions() {
        // Check if already dismissed
        const dismissTime = localStorage.getItem('ios-install-dismissed');
        if (dismissTime && new Date().getTime() < parseInt(dismissTime)) {
            return;
        }
        
        const iosPromptHtml = `
            <div id="ios-install-banner" class="alert alert-info position-fixed" style="bottom: 10px; left: 10px; right: 10px; z-index: 1050; display: none;">
                <div class="d-flex align-items-center">
                    <div class="me-3">
                        <i class="bi bi-phone display-6 text-primary"></i>
                    </div>
                    <div class="flex-grow-1">
                        <h6 class="alert-heading mb-1">Ana Ekrana Ekle</h6>
                        <p class="mb-2 small">
                            Bu uygulamayı ana ekranınıza eklemek için:
                            <br>1. <i class="bi bi-share"></i> Paylaş butonuna basın
                            <br>2. "Ana Ekrana Ekle" seçeneğini seçin
                        </p>
                        <button class="btn btn-outline-secondary btn-sm" onclick="document.getElementById('ios-install-banner').style.display='none'; localStorage.setItem('ios-install-dismissed', (new Date().getTime() + 7*24*60*60*1000).toString());">
                            Anladım
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        if (!document.getElementById('ios-install-banner')) {
            document.body.insertAdjacentHTML('beforeend', iosPromptHtml);
            document.getElementById('ios-install-banner').style.display = 'block';
            
            // Auto-hide after 20 seconds
            setTimeout(() => {
                const banner = document.getElementById('ios-install-banner');
                if (banner && banner.style.display === 'block') {
                    banner.style.display = 'none';
                }
            }, 20000);
        }
    }
    
    showInstallSuccessMessage() {
        showNotification('🎉 Uygulama başarıyla yüklendi! Artık ana ekranınızdan erişebilirsiniz.', 'success');
    }
}

// Global instance
const pwaInstallManager = new PWAInstallManager();

// Legacy function for compatibility
async function installPWA() {
    return pwaInstallManager.installPWA();
}

// Online/Offline Status
window.addEventListener('online', function() {
    showNotification('🌐 İnternet bağlantısı geri geldi', 'success');
    syncOfflineActions();
});

window.addEventListener('offline', function() {
    showNotification('📡 İnternet bağlantısı kesildi. Offline modda çalışıyorsunuz.', 'warning');
});

// Offline Actions Sync
async function syncOfflineActions() {
    try {
        const offlineActions = getOfflineActions();
        
        for (const action of offlineActions) {
            try {
                const response = await fetch(action.url, {
                    method: action.method,
                    headers: action.headers,
                    body: action.body
                });
                
                if (response.ok) {
                    removeOfflineAction(action.id);
                    console.log('✅ Offline aksiyon senkronize edildi:', action.type);
                }
            } catch (error) {
                console.log('❌ Offline aksiyon senkronizasyonu başarısız:', error);
            }
        }
    } catch (error) {
        console.error('❌ Offline senkronizasyon hatası:', error);
    }
}

// Enhanced Offline Actions with IndexedDB and Background Sync
class OfflineActionManager {
    constructor() {
        this.dbName = 'LibraryDB';
        this.dbVersion = 1;
        this.storeName = 'pendingActions';
        this.init();
    }
    
    async init() {
        try {
            this.db = await this.openDB();
            console.log('✅ OfflineActionManager başlatıldı');
        } catch (error) {
            console.error('❌ OfflineActionManager hatası:', error);
            // Fallback to localStorage
            this.useLocalStorage = true;
        }
    }
    
    openDB() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(this.dbName, this.dbVersion);
            
            request.onerror = () => reject(request.error);
            request.onsuccess = () => resolve(request.result);
            
            request.onupgradeneeded = () => {
                const db = request.result;
                if (!db.objectStoreNames.contains(this.storeName)) {
                    const store = db.createObjectStore(this.storeName, { keyPath: 'id' });
                    store.createIndex('timestamp', 'timestamp', { unique: false });
                    store.createIndex('type', 'type', { unique: false });
                }
            };
        });
    }
    
    async saveAction(action) {
        action.id = Date.now() + Math.random();
        action.timestamp = new Date().toISOString();
        
        if (this.useLocalStorage) {
            return this.saveToLocalStorage(action);
        }
        
        try {
            const transaction = this.db.transaction([this.storeName], 'readwrite');
            const store = transaction.objectStore(this.storeName);
            await store.add(action);
            
            // Background Sync'i tetikle
            this.requestBackgroundSync();
            
            console.log('✅ Offline aksiyon kaydedildi:', action.type);
        } catch (error) {
            console.error('❌ Offline aksiyon kaydetme hatası:', error);
            this.saveToLocalStorage(action);
        }
    }
    
    async getActions() {
        if (this.useLocalStorage) {
            return this.getFromLocalStorage();
        }
        
        try {
            const transaction = this.db.transaction([this.storeName], 'readonly');
            const store = transaction.objectStore(this.storeName);
            return await store.getAll();
        } catch (error) {
            console.error('❌ Offline aksiyon okuma hatası:', error);
            return this.getFromLocalStorage();
        }
    }
    
    async removeAction(actionId) {
        if (this.useLocalStorage) {
            return this.removeFromLocalStorage(actionId);
        }
        
        try {
            const transaction = this.db.transaction([this.storeName], 'readwrite');
            const store = transaction.objectStore(this.storeName);
            await store.delete(actionId);
            console.log('✅ Offline aksiyon silindi:', actionId);
        } catch (error) {
            console.error('❌ Offline aksiyon silme hatası:', error);
            this.removeFromLocalStorage(actionId);
        }
    }
    
    async requestBackgroundSync() {
        try {
            if ('serviceWorker' in navigator && 'sync' in window.ServiceWorkerRegistration.prototype) {
                const registration = await navigator.serviceWorker.ready;
                await registration.sync.register('background-sync-library');
                console.log('✅ Background Sync tetiklendi');
            }
        } catch (error) {
            console.error('❌ Background Sync tetikleme hatası:', error);
        }
    }
    
    // LocalStorage fallback methods
    saveToLocalStorage(action) {
        const actions = this.getFromLocalStorage();
        actions.push(action);
        localStorage.setItem('offlineActions', JSON.stringify(actions));
    }
    
    getFromLocalStorage() {
        try {
            return JSON.parse(localStorage.getItem('offlineActions') || '[]');
        } catch (error) {
            return [];
        }
    }
    
    removeFromLocalStorage(actionId) {
        const actions = this.getFromLocalStorage();
        const filteredActions = actions.filter(action => action.id !== actionId);
        localStorage.setItem('offlineActions', JSON.stringify(filteredActions));
    }
}

// Global instance
const offlineActionManager = new OfflineActionManager();

// Legacy functions for compatibility
function saveOfflineAction(action) {
    return offlineActionManager.saveAction(action);
}

function getOfflineActions() {
    return offlineActionManager.getActions();
}

function removeOfflineAction(actionId) {
    return offlineActionManager.removeAction(actionId);
}

// Enhanced QR Scanner
class EnhancedQRScanner {
    constructor(elementId) {
        this.elementId = elementId;
        this.scanner = null;
        this.isScanning = false;
    }
    
    async start() {
        try {
            // Html5QrcodeScanner kütüphanesi gerekli
            if (typeof Html5QrcodeScanner === 'undefined') {
                console.error('❌ Html5QrcodeScanner kütüphanesi yüklenmemiş');
                return;
            }
            
            this.scanner = new Html5QrcodeScanner(this.elementId, {
                qrbox: { width: 250, height: 250 },
                fps: 20,
                experimentalFeatures: {
                    useBarCodeDetectorIfSupported: true
                }
            });
            
            this.scanner.render(
                (decodedText, decodedResult) => {
                    this.onScanSuccess(decodedText, decodedResult);
                },
                (error) => {
                    // Scan failure - silent
                }
            );
            
            this.isScanning = true;
            console.log('✅ QR Scanner başlatıldı');
            
        } catch (error) {
            console.error('❌ QR Scanner başlatma hatası:', error);
        }
    }
    
    stop() {
        if (this.scanner && this.isScanning) {
            this.scanner.clear();
            this.isScanning = false;
            console.log('⏹️ QR Scanner durduruldu');
        }
    }
    
    onScanSuccess(decodedText, decodedResult) {
        // Vibration feedback
        if ('vibrate' in navigator) {
            navigator.vibrate(200);
        }
        
        // Audio feedback
        this.playBeepSound();
        
        // Process scanned data
        this.processScannedData(decodedText);
        
        // Stop scanning after successful scan
        this.stop();
    }
    
    playBeepSound() {
        try {
            const audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = audioContext.createOscillator();
            const gainNode = audioContext.createGain();
            
            oscillator.connect(gainNode);
            gainNode.connect(audioContext.destination);
            
            oscillator.frequency.value = 800;
            oscillator.type = 'square';
            
            gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.1);
            
            oscillator.start(audioContext.currentTime);
            oscillator.stop(audioContext.currentTime + 0.1);
        } catch (error) {
            console.log('🔇 Audio feedback hatası:', error);
        }
    }
    
    processScannedData(data) {
        console.log('📱 QR Kod okundu:', data);
        
        // ISBN kontrolü
        if (this.isISBN(data)) {
            window.location.href = `/book/${data}`;
        } else {
            showNotification('QR kod işlendi: ' + data, 'info');
        }
    }
    
    isISBN(text) {
        // Basit ISBN kontrolü
        const cleanText = text.replace(/[^0-9X]/g, '');
        return cleanText.length === 10 || cleanText.length === 13;
    }
}

// Voice Search
class VoiceSearch {
    constructor() {
        this.recognition = null;
        this.isListening = false;
        
        if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
            this.recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
            this.recognition.lang = 'tr-TR';
            this.recognition.continuous = false;
            this.recognition.interimResults = false;
            
            this.setupEventListeners();
        }
    }
    
    setupEventListeners() {
        this.recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            this.processVoiceSearch(transcript);
        };
        
        this.recognition.onerror = (event) => {
            console.error('🎤 Ses tanıma hatası:', event.error);
            this.stopListening();
        };
        
        this.recognition.onend = () => {
            this.stopListening();
        };
    }
    
    startListening() {
        if (this.recognition && !this.isListening) {
            this.recognition.start();
            this.isListening = true;
            this.showVoiceIndicator();
            console.log('🎤 Ses tanıma başlatıldı');
        }
    }
    
    stopListening() {
        this.isListening = false;
        this.hideVoiceIndicator();
    }
    
    processVoiceSearch(query) {
        console.log('🎤 Ses komutu:', query);
        
        // Search sayfasına yönlendir
        const searchUrl = `/search?q=${encodeURIComponent(query)}&type=voice`;
        window.location.href = searchUrl;
    }
    
    showVoiceIndicator() {
        // Voice indicator göster
        const indicator = document.getElementById('voice-indicator');
        if (indicator) {
            indicator.style.display = 'block';
        }
    }
    
    hideVoiceIndicator() {
        // Voice indicator gizle
        const indicator = document.getElementById('voice-indicator');
        if (indicator) {
            indicator.style.display = 'none';
        }
    }
}

// Gesture Handler
class GestureHandler {
    constructor() {
        this.touchStartX = 0;
        this.touchStartY = 0;
        this.touchEndX = 0;
        this.touchEndY = 0;
        this.minSwipeDistance = 50;
        
        this.init();
    }
    
    init() {
        document.addEventListener('touchstart', this.handleTouchStart.bind(this), false);
        document.addEventListener('touchend', this.handleTouchEnd.bind(this), false);
    }
    
    handleTouchStart(event) {
        this.touchStartX = event.changedTouches[0].screenX;
        this.touchStartY = event.changedTouches[0].screenY;
    }
    
    handleTouchEnd(event) {
        this.touchEndX = event.changedTouches[0].screenX;
        this.touchEndY = event.changedTouches[0].screenY;
        this.handleGesture();
    }
    
    handleGesture() {
        const deltaX = this.touchEndX - this.touchStartX;
        const deltaY = this.touchEndY - this.touchStartY;
        
        if (Math.abs(deltaX) > Math.abs(deltaY)) {
            // Horizontal swipe
            if (deltaX > this.minSwipeDistance) {
                this.onSwipeRight();
            } else if (deltaX < -this.minSwipeDistance) {
                this.onSwipeLeft();
            }
        } else {
            // Vertical swipe
            if (deltaY > this.minSwipeDistance) {
                this.onSwipeDown();
            } else if (deltaY < -this.minSwipeDistance) {
                this.onSwipeUp();
            }
        }
    }
    
    onSwipeLeft() {
        // Sidebar'ı kapat
        const sidebar = document.querySelector('.sidebar');
        if (sidebar && sidebar.classList.contains('show')) {
            sidebar.classList.remove('show');
        }
    }
    
    onSwipeRight() {
        // Sidebar'ı aç
        const sidebar = document.querySelector('.sidebar');
        if (sidebar && !sidebar.classList.contains('show')) {
            sidebar.classList.add('show');
        }
    }
    
    onSwipeUp() {
        // Sayfanın üstüne git
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
    
    onSwipeDown() {
        // Sayfa yenile (sadece en üstteyse)
        if (window.scrollY === 0) {
            location.reload();
        }
    }
}

// Dark Mode Toggle
function toggleDarkMode() {
    const body = document.body;
    const isDark = body.classList.contains('dark-mode');
    
    if (isDark) {
        body.classList.remove('dark-mode');
        localStorage.setItem('theme', 'light');
    } else {
        body.classList.add('dark-mode');
        localStorage.setItem('theme', 'dark');
    }
    
    // Theme icon'u güncelle
    updateThemeIcon(!isDark);
}

function updateThemeIcon(isDark) {
    const themeIcon = document.querySelector('#theme-toggle i');
    if (themeIcon) {
        themeIcon.className = isDark ? 'bi bi-sun' : 'bi bi-moon';
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    // Apply saved theme
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark') {
        document.body.classList.add('dark-mode');
        updateThemeIcon(true);
    }
    
    // Initialize gesture handler
    new GestureHandler();
    
    // Initialize voice search
    const voiceSearch = new VoiceSearch();
    
    // Voice search button event
    const voiceButton = document.getElementById('voice-search-btn');
    if (voiceButton) {
        voiceButton.addEventListener('click', () => {
            voiceSearch.startListening();
        });
    }
    
    // Theme toggle button event
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', toggleDarkMode);
    }
    
    console.log('🚀 PWA özellikleri yüklendi');
});

// Utility function for notifications
function showNotification(message, type = 'info') {
    // Bootstrap toast veya basit alert kullan
    if (typeof bootstrap !== 'undefined' && bootstrap.Toast) {
        // Bootstrap toast implementation
        const toastHtml = `
            <div class="toast align-items-center text-white bg-${type === 'success' ? 'success' : type === 'warning' ? 'warning' : type === 'error' ? 'danger' : 'primary'} border-0" role="alert">
                <div class="d-flex">
                    <div class="toast-body">${message}</div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
                </div>
            </div>
        `;
        
        // Toast container oluştur veya kullan
        let toastContainer = document.getElementById('toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.id = 'toast-container';
            toastContainer.className = 'toast-container position-fixed bottom-0 end-0 p-3';
            document.body.appendChild(toastContainer);
        }
        
        toastContainer.insertAdjacentHTML('beforeend', toastHtml);
        const toastElement = toastContainer.lastElementChild;
        const toast = new bootstrap.Toast(toastElement);
        toast.show();
        
        // Toast'ı otomatik temizle
        toastElement.addEventListener('hidden.bs.toast', () => {
            toastElement.remove();
        });
    } else {
        // Fallback: basit alert
        alert(message);
    }
}

console.log('✅ PWA Features modülü yüklendi!'); 