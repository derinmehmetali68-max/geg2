/**
 * Modern Kütüphane Yönetim Sistemi - Ana JavaScript Modülü
 * Modern ES6+ özellikleri ve performans optimizasyonları ile geliştirilmiştir
 */

// Modern Uygulama Konfigürasyonu
const AppConfig = {
    // API ve Network Ayarları
    timeout: 5000,
    maxRetries: 3,
    debounceDelay: 300,
    
    // UI Ayarları
    itemsPerPage: 20,
    animationDuration: 200,
    toastDuration: 4000,
    
    // Tema Ayarları
    defaultTheme: 'light',
    availableThemes: ['light', 'dark', 'rainbow', 'red', 'grey', 'bordo'],
    
    // Cache Ayarları
    cacheTimeout: 5 * 60 * 1000, // 5 dakika
    maxCacheSize: 50
};

/**
 * Modern Uygulama Sınıfı - Singleton Pattern
 */
class LibraryApp {
    constructor() {
        this.isLoading = false;
        this.activeRequests = new Map();
        this.cache = new Map();
        this.eventListeners = new Map();
        this.theme = localStorage.getItem('theme') || AppConfig.defaultTheme;
        
        // Bind methods
        this.handleKeyboard = this.handleKeyboard.bind(this);
        this.handleAjaxError = this.handleAjaxError.bind(this);
        
        this.init();
    }
    
    /**
     * Uygulamayı başlat
     */
    init() {
        console.log('🚀 Modern Kütüphane Sistemi başlatılıyor...');
        
        // Temel event listener'ları kaydet
        this.setupEventListeners();
        
        // AJAX ayarlarını yapılandır
        this.setupAjax();
        
        // Tema sistemini başlat
        this.initTheme();
        
        // Bildirim sistemini başlat
        this.initNotifications();
        
        console.log('✅ Sistem başarıyla başlatıldı');
    }
    
    /**
     * Event listener'ları ayarla
     */
    setupEventListeners() {
        // Klavye kısayolları
        document.addEventListener('keydown', this.handleKeyboard, true);
        
        // Sayfa yüklendiğinde
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.onPageLoad());
        } else {
            this.onPageLoad();
        }
        
        // Tema değişiklik butonları
        $(document).on('click', '[data-theme]', (e) => {
            const theme = $(e.target).data('theme');
            this.setTheme(theme);
        });
        
        // Tooltip'leri otomatik başlat
        $(document).on('mouseenter', '[data-bs-toggle="tooltip"]:not([data-tooltip-init])', function() {
            $(this).attr('data-tooltip-init', 'true').tooltip();
        });
    }
    
    /**
     * Klavye kısayollarını işle
     */
    handleKeyboard(e) {
        // ESC tuşu - Modal'ları kapat
    if (e.key === 'Escape') {
            this.closeModals();
            return;
        }
        
        // Ctrl+K - Hızlı arama
        if (e.ctrlKey && e.key === 'k') {
            e.preventDefault();
            this.focusSearch();
            return;
        }
        
        // Ctrl+/ - Kısayol yardımı
        if (e.ctrlKey && e.key === '/') {
        e.preventDefault();
            this.showKeyboardShortcuts();
            return;
        }
    }

    /**
     * AJAX ayarlarını yapılandır
     */
    setupAjax() {
        const self = this;
        
$.ajaxSetup({
    timeout: AppConfig.timeout,
            beforeSend: function(xhr, settings) {
                // İsteği kaydet
                const requestId = Date.now() + Math.random();
                self.activeRequests.set(requestId, xhr);
                
                // Loading göster (eğer showLoading false değilse)
                if (settings.showLoading !== false && !self.isLoading) {
                    self.showLoading();
                }
                
                return true;
            },
            complete: function(xhr, status) {
                // İsteği kaldır
                for (let [id, request] of self.activeRequests) {
                    if (request === xhr) {
                        self.activeRequests.delete(id);
                        break;
                    }
                }
                
                // Tüm istekler bittiyse loading'i gizle
                if (self.activeRequests.size === 0) {
                    self.hideLoading();
        }
    },
    error: function(xhr, status, error) {
                self.handleAjaxError(xhr, status, error);
            }
        });
    }
    
    /**
     * AJAX hata işleyicisi
     */
    handleAjaxError(xhr, status, error) {
        this.hideLoading();
        
        let message = 'Bir hata oluştu';
        
        switch (status) {
            case 'timeout':
                message = 'İşlem zaman aşımına uğradı';
                break;
            case 'abort':
                return; // İptal edilen istekler için mesaj gösterme
            case 'error':
                if (xhr.status === 0) {
                    message = 'Bağlantı hatası - İnternet bağlantınızı kontrol edin';
                } else if (xhr.status === 404) {
                    message = 'İstenen kaynak bulunamadı';
                } else if (xhr.status === 500) {
                    message = 'Sunucu hatası oluştu';
                } else if (xhr.responseJSON?.message) {
                    message = xhr.responseJSON.message;
                }
                break;
        }
        
        this.showToast(message, 'error');
    }

    /**
     * Sayfa yüklendiğinde çalışacak fonksiyon
     */
    onPageLoad() {
        // Alert'leri otomatik gizle
        setTimeout(() => {
            $('.alert:not(.alert-permanent)').fadeOut(AppConfig.animationDuration);
        }, 3000);
        
        // Sayfa spesifik verileri yükle
        this.loadPageData();
        
        // Performans metrikleri
        if (performance.navigation) {
            console.log(`📊 Sayfa yükleme süresi: ${performance.now().toFixed(2)}ms`);
        }
    }
    
    /**
     * Tema sistemini başlat
     */
    initTheme() {
        this.applyTheme(this.theme);
        
        // Sistem tema tercihi değişikliklerini dinle
        if (window.matchMedia) {
            const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
            mediaQuery.addListener((e) => {
                if (this.theme === 'auto') {
                    this.applyTheme(e.matches ? 'dark' : 'light');
                }
            });
        }
    }
    
    /**
     * Bildirim sistemini başlat
     */
    initNotifications() {
        if (this.isUserAuthenticated()) {
            // İlk bildirim kontrolü
            setTimeout(() => this.checkNotifications(), 1000);
            
            // Periyodik kontrol
            setInterval(() => this.checkNotifications(), 60000);
        }
    }

    /**
     * Tema uygula
     */
    applyTheme(theme) {
    // Önceki tema sınıflarını kaldır
        document.body.classList.remove(...AppConfig.availableThemes.map(t => `theme-${t}`));
    
    // Yeni tema sınıfını ekle
        if (theme !== 'light') {
            document.body.classList.add(`theme-${theme}`);
    }
    
    // LocalStorage'a kaydet
    localStorage.setItem('theme', theme);
        this.theme = theme;
    
    console.log(`🎨 Tema değiştirildi: ${theme}`);
        
        // Tema değişikliğini sunucuya bildir
        if (this.isUserAuthenticated()) {
            this.saveThemePreference(theme);
        }
    }
    
    /**
     * Tema tercihini sunucuya kaydet
     */
    async saveThemePreference(theme) {
        try {
            await $.post('/api/user/theme', { theme });
        } catch (error) {
            console.warn('Tema tercihi kaydedilemedi:', error);
        }
    }

    /**
     * Loading göster
     */
    showLoading() {
        if (this.isLoading) return;
        
        this.isLoading = true;
        
        // Minimal loading indicator
        const loader = $(`
            <div id="modern-loader" style="position: fixed; top: 0; left: 0; right: 0; 
                 height: 3px; background: linear-gradient(90deg, var(--primary-color), var(--info-color)); 
                 z-index: 9999; animation: loading-bar 1s ease-in-out infinite;">
            </div>
        `);
        
        $('body').append(loader);
    }
    
    /**
     * Loading gizle
     */
    hideLoading() {
        this.isLoading = false;
        $('#modern-loader').fadeOut(AppConfig.animationDuration, function() {
            $(this).remove();
        });
    }

    /**
     * Toast bildirimi göster
     */
    showToast(message, type = 'info', duration = AppConfig.toastDuration) {
        const types = {
            'info': { bg: 'bg-primary', icon: 'bi-info-circle' },
            'success': { bg: 'bg-success', icon: 'bi-check-circle' },
            'warning': { bg: 'bg-warning text-dark', icon: 'bi-exclamation-triangle' },
            'error': { bg: 'bg-danger', icon: 'bi-x-circle' },
            'danger': { bg: 'bg-danger', icon: 'bi-x-circle' }
        };
        
        const config = types[type] || types.info;
        const toastId = `toast-${Date.now()}`;
    
    const toast = $(`
            <div id="${toastId}" class="toast-notification" style="position: fixed; top: 20px; right: 20px; 
                 z-index: 10000; max-width: 350px; padding: 1rem 1.5rem; border-radius: 0.5rem; 
                 box-shadow: 0 10px 25px rgba(0,0,0,0.2); cursor: pointer; transform: translateX(100%); 
                 transition: transform 0.3s ease;" class="${config.bg}">
                <div style="display: flex; align-items: center; gap: 0.75rem;">
                    <i class="bi ${config.icon}" style="font-size: 1.25rem;"></i>
                    <span style="flex: 1; font-weight: 500;">${message}</span>
                    <i class="bi bi-x" style="font-size: 1.25rem; opacity: 0.7;"></i>
                </div>
        </div>
    `);
    
    $('body').append(toast);
    
        // Animate in
        setTimeout(() => {
            toast.css('transform', 'translateX(0)');
        }, 10);
    
    // Click to dismiss
        toast.on('click', () => this.dismissToast(toastId));
        
        // Auto dismiss
        setTimeout(() => this.dismissToast(toastId), duration);
    }
    
    /**
     * Toast'ı kapat
     */
    dismissToast(toastId) {
        const toast = $(`#${toastId}`);
        toast.css('transform', 'translateX(100%)');
        setTimeout(() => toast.remove(), 300);
    }

    /**
     * Modal'ları kapat
     */
    closeModals() {
        $('.modal').modal('hide');
        $('.modal-backdrop').remove();
        $('body').removeClass('modal-open').css('padding-right', '');
    }
    
    /**
     * Arama kutusuna odaklan
     */
    focusSearch() {
        const searchInput = $('input[type="search"], input[placeholder*="ara"], input[placeholder*="Ara"]').first();
        if (searchInput.length) {
            searchInput.focus();
            this.showToast('Hızlı arama aktif', 'info', 2000);
        }
    }
    
    /**
     * Klavye kısayolları yardımını göster
     */
    showKeyboardShortcuts() {
        const shortcuts = [
            { key: 'Esc', description: 'Modal\'ları kapat' },
            { key: 'Ctrl+K', description: 'Hızlı arama' },
            { key: 'Ctrl+/', description: 'Bu yardım menüsü' }
        ];
        
        let html = '<div class="keyboard-shortcuts"><h6>Klavye Kısayolları</h6><ul>';
        shortcuts.forEach(shortcut => {
            html += `<li><kbd>${shortcut.key}</kbd> ${shortcut.description}</li>`;
        });
        html += '</ul></div>';
        
        this.showToast(html, 'info', 5000);
    }

    /**
     * Kullanıcı giriş yapmış mı kontrol et
     */
    isUserAuthenticated() {
        return document.querySelector('#userDropdown') !== null;
    }
    
    /**
     * Bildirimleri kontrol et
     */
    async checkNotifications() {
        if (!this.isUserAuthenticated()) return;
        
        try {
            const response = await $.get('/api/notifications?unread_only=true');
            const count = response.notifications ? response.notifications.length : 0;
            this.updateNotificationBadge(count);
        } catch (error) {
            console.warn('Bildirimler alınamadı:', error);
        }
    }
    
    /**
     * Bildirim badge'ini güncelle
     */
    updateNotificationBadge(count) {
        const badge = $('#notificationBadge');
        if (count > 0) {
            badge.text(count).show();
        } else {
            badge.hide();
        }
    }

    /**
     * Sayfa spesifik verileri yükle
     */
    loadPageData() {
        const path = window.location.pathname;
        console.log('📄 Sayfa verileri yükleniyor:', path);
        
        // Sayfa spesifik yükleme fonksiyonlarını çağır
        switch (path) {
            case '/books':
                if (typeof loadBooks === 'function') {
                    setTimeout(() => loadBooks(1), 100);
                }
                break;
            case '/members':
                if (typeof loadMembers === 'function') {
                    setTimeout(() => loadMembers(1), 100);
                }
                break;
            case '/transactions':
                if (typeof loadTransactions === 'function') {
                    setTimeout(() => loadTransactions(1), 100);
                }
                break;
        }
    }

    /**
     * Utility fonksiyonlar
     */
    
    // Debounce utility
    debounce(func, wait) {
    let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
        clearTimeout(timeout);
            timeout = setTimeout(later, wait);
    };
}

    // Tarih/saat formatlama
    formatDate(dateString) {
        if (!dateString || dateString === '-') return '-';
        try {
            // 'YYYY-MM-DD HH:MM:SS' veya 'YYYY-MM-DD' destekle
            if (typeof dateString === 'string' && dateString.length > 10) {
                // Replace space with 'T' to ensure proper parsing in Safari/Edge
                const safe = dateString.replace(' ', 'T');
                const d = new Date(safe);
                if (!isNaN(d.getTime())) {
                    return d.toLocaleString('tr-TR');
                }
            }
            const d = new Date(dateString);
            if (!isNaN(d.getTime())) {
                return d.toLocaleDateString('tr-TR');
            }
            return dateString;
        } catch {
            return dateString;
        }
    }

    // Para formatlama
    formatCurrency(amount) {
    try {
        return new Intl.NumberFormat('tr-TR', {
            style: 'currency',
            currency: 'TRY'
        }).format(amount);
    } catch {
        return amount + ' TL';
    }
}

    // Panoya kopyala
    async copyToClipboard(text) {
        try {
            await navigator.clipboard.writeText(text);
            this.showToast('Panoya kopyalandı!', 'success', 2000);
        } catch {
            // Fallback
            const textArea = document.createElement('textarea');
            textArea.value = text;
            document.body.appendChild(textArea);
            textArea.select();
            document.execCommand('copy');
            document.body.removeChild(textArea);
            this.showToast('Panoya kopyalandı!', 'success', 2000);
        }
    }
}

// CSS animasyonu ekle
const style = document.createElement('style');
style.textContent = `
    @keyframes loading-bar {
        0% { transform: translateX(-100%); }
        100% { transform: translateX(100%); }
    }
    
    .keyboard-shortcuts ul {
        list-style: none;
        padding: 0;
        margin: 0.5rem 0;
    }
    
    .keyboard-shortcuts li {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0.25rem 0;
    }
    
    .keyboard-shortcuts kbd {
        background: rgba(255,255,255,0.2);
        padding: 0.25rem 0.5rem;
        border-radius: 0.25rem;
        font-size: 0.75rem;
    }
`;
document.head.appendChild(style);

// Global uygulama instance'ı oluştur
const app = new LibraryApp();

// Global fonksiyonları expose et (geriye uyumluluk için)
window.LibraryApp = app;
window.showToast = (message, type, duration) => app.showToast(message, type, duration);
window.applyTheme = (theme) => app.applyTheme(theme);
window.emergencyCleanup = () => app.closeModals();
// Geriye uyumluluk: yardımcı fonksiyonlar
window.debounce = (fn, wait) => app.debounce(fn, wait);
window.formatDate = (value) => app.formatDate(value);
window.formatCurrency = (amount) => app.formatCurrency(amount);

// Legacy support
window.loadCurrentPageData = (page) => {
    const path = window.location.pathname;
    switch (path) {
        case '/books':
            if (typeof loadBooks === 'function') loadBooks(page);
            break;
        case '/members':
            if (typeof loadMembers === 'function') loadMembers(page);
            break;
        case '/transactions':
            if (typeof loadTransactions === 'function') loadTransactions(page);
            break;
    }
};

console.log('📚 Modern Kütüphane JavaScript yüklendi');