/**
 * PWA Features - Progressive Web App
 */

// Service Worker Registration
if ('serviceWorker' in navigator) {
    window.addEventListener('load', function() {
        navigator.serviceWorker.register('/sw.js')
            .then(function(registration) {
                console.log('✅ Service Worker kayıtlı');
                
                if ('PushManager' in window) {
                    initializePushNotifications(registration);
                }
            })
            .catch(function(error) {
                console.log('❌ Service Worker hatası:', error);
            });
    });
}

// Push Notifications
async function initializePushNotifications(registration) {
    try {
        const permission = await Notification.requestPermission();
        
        if (permission === 'granted') {
            console.log('✅ Bildirim izni verildi');
        }
    } catch (error) {
        console.error('❌ Push notification hatası:', error);
    }
}

// PWA Install
let deferredPrompt;

window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
    showInstallButton();
});

function showInstallButton() {
    const installBtn = document.createElement('button');
    installBtn.id = 'install-button';
    installBtn.className = 'btn btn-primary btn-sm position-fixed';
    installBtn.style.cssText = 'bottom: 20px; right: 20px; z-index: 1000;';
    installBtn.innerHTML = '<i class="bi bi-download"></i> Uygulamayı Yükle';
    installBtn.addEventListener('click', installPWA);
    
    document.body.appendChild(installBtn);
}

async function installPWA() {
    if (deferredPrompt) {
        deferredPrompt.prompt();
        const { outcome } = await deferredPrompt.userChoice;
        
        if (outcome === 'accepted') {
            console.log('✅ PWA yüklendi');
        }
        
        deferredPrompt = null;
        document.getElementById('install-button').style.display = 'none';
    }
}

// Online/Offline Status
window.addEventListener('online', function() {
    showNotification('🌐 İnternet bağlantısı geri geldi', 'success');
});

window.addEventListener('offline', function() {
    showNotification('📡 Offline modda çalışıyorsunuz', 'warning');
});

// Dark Mode
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
}

// Initialize
document.addEventListener('DOMContentLoaded', function() {
    // Apply saved theme
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark') {
        document.body.classList.add('dark-mode');
    }
    
    // Theme toggle
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', toggleDarkMode);
    }
    
    console.log('🚀 PWA özellikleri yüklendi');
});

function showNotification(message, type = 'info') {
    // Basit notification
    const notification = document.createElement('div');
    notification.className = `alert alert-${type === 'success' ? 'success' : type === 'warning' ? 'warning' : 'info'} position-fixed`;
    notification.style.cssText = 'top: 20px; right: 20px; z-index: 1050; max-width: 300px;';
    notification.textContent = message;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.remove();
    }, 3000);
}

console.log('✅ PWA modülü yüklendi!'); 