/**
 * Service Worker - PWA Offline Support with Background Sync
 */

// Service Worker for CAL Library Management System
const CACHE_NAME = 'cal-library-v1.1.0';
const DATA_CACHE_NAME = 'cal-library-data-v1.1.0';

const urlsToCache = [
    '/',
    '/static/css/bootstrap.min.css',
    '/static/css/style.css',
    '/static/css/dark-mode.css',
    '/static/css/enhanced.css',
    '/static/css/modern-enhancements.css',
    '/static/js/jquery-3.6.0.min.js',
    '/static/js/bootstrap.bundle.min.js',
    '/static/js/main.js',
    '/static/js/books-and-transactions.js',
    '/static/js/pwa.js',
    '/static/js/pwa-features.js',
    '/static/img/icon-192x192.png',
    '/static/img/icon-144x144.png',
    '/static/manifest.json',
    '/offline',
    '/search',
    '/my_books',
    '/qr_borrow',
    '/kiosk-mode',
    '/advanced-kiosk'
];

// API endpoints to cache
const API_URLS = [
    '/api/books/search',
    '/api/stats',
    '/api/my-books'
];

// Install event
self.addEventListener('install', function(event) {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(function(cache) {
                console.log('Cache açıldı');
                return cache.addAll(urlsToCache);
            })
    );
});

// Fetch event - Enhanced with data caching
self.addEventListener('fetch', function(event) {
    // API istekleri için özel işlem
    if (event.request.url.includes('/api/')) {
        event.respondWith(
            caches.open(DATA_CACHE_NAME).then(function(cache) {
                return fetch(event.request)
                    .then(function(response) {
                        // Başarılı API yanıtlarını cache'le
                        if (response.status === 200) {
                            cache.put(event.request.url, response.clone());
                        }
                        return response;
                    })
                    .catch(function() {
                        // Offline durumunda cache'den döndür
                        return cache.match(event.request);
                    });
            })
        );
        return;
    }
    
    // Diğer istekler için standard cache stratejisi
    event.respondWith(
        caches.match(event.request)
            .then(function(response) {
                // Cache'den döndür veya network'ten getir
                if (response) {
                    return response;
                }
                
                return fetch(event.request)
                    .then(function(fetchResponse) {
                        // Dinamik cache'leme
                        if (fetchResponse.status === 200) {
                            const responseClone = fetchResponse.clone();
                            caches.open(CACHE_NAME).then(function(cache) {
                                cache.put(event.request, responseClone);
                            });
                        }
                        return fetchResponse;
                    })
                    .catch(function() {
                        // Offline durumunda offline sayfasını göster
                        if (event.request.destination === 'document') {
                            return caches.match('/offline');
                        }
                        // Image fallback
                        if (event.request.destination === 'image') {
                            return caches.match('/static/img/icon-192x192.png');
                        }
                    });
            })
    );
});

// Activate event - Enhanced with data cache cleanup
self.addEventListener('activate', function(event) {
    event.waitUntil(
        caches.keys().then(function(cacheNames) {
            return Promise.all(
                cacheNames.map(function(cacheName) {
                    if (cacheName !== CACHE_NAME && cacheName !== DATA_CACHE_NAME) {
                        console.log('Eski cache siliniyor:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        }).then(function() {
            // Service Worker'ı hemen aktif et
            return self.clients.claim();
        })
    );
});

// Push notification event
self.addEventListener('push', function(event) {
    const options = {
        body: event.data ? event.data.text() : 'Yeni bildirim',
        icon: '/static/img/icon-192x192.png',
        badge: '/static/img/icon-192x192.png',
        vibrate: [200, 100, 200],
        data: {
            dateOfArrival: Date.now(),
            primaryKey: 1
        },
        actions: [
            {
                action: 'explore',
                title: 'Görüntüle',
                icon: '/static/img/icon-192x192.png'
            },
            {
                action: 'close',
                title: 'Kapat',
                icon: '/static/img/icon-192x192.png'
            }
        ]
    };

    event.waitUntil(
        self.registration.showNotification('CAL Kütüphane', options)
    );
});

// Notification click event
self.addEventListener('notificationclick', function(event) {
    event.notification.close();

    if (event.action === 'explore') {
        event.waitUntil(
            clients.openWindow('/')
        );
    }
});

// Background Sync Event
self.addEventListener('sync', function(event) {
    console.log('🔄 Background Sync tetiklendi:', event.tag);
    
    if (event.tag === 'background-sync-library') {
        event.waitUntil(doBackgroundSync());
    }
});

async function doBackgroundSync() {
    try {
        console.log('🔄 Background sync başlatıldı');
        
        // IndexedDB'den bekleyen işlemleri al
        const pendingActions = await getPendingActions();
        
        for (const action of pendingActions) {
            try {
                const response = await fetch(action.url, {
                    method: action.method,
                    headers: action.headers,
                    body: action.body
                });
                
                if (response.ok) {
                    await removePendingAction(action.id);
                    console.log('✅ Background sync tamamlandı:', action.type);
                    
                    // Başarılı sync bildirimini gönder
                    await self.registration.showNotification('İşlem Tamamlandı', {
                        body: `${action.type} işlemi başarıyla tamamlandı`,
                        icon: '/static/img/icon-192x192.png',
                        badge: '/static/img/icon-192x192.png',
                        tag: 'sync-success'
                    });
                }
            } catch (error) {
                console.error('❌ Background sync hatası:', error);
            }
        }
    } catch (error) {
        console.error('❌ Background sync genel hatası:', error);
    }
}

// IndexedDB helper functions for background sync
async function getPendingActions() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open('LibraryDB', 1);
        
        request.onerror = () => reject(request.error);
        request.onsuccess = () => {
            const db = request.result;
            const transaction = db.transaction(['pendingActions'], 'readonly');
            const store = transaction.objectStore('pendingActions');
            const getRequest = store.getAll();
            
            getRequest.onsuccess = () => resolve(getRequest.result || []);
            getRequest.onerror = () => resolve([]);
        };
        
        request.onupgradeneeded = () => {
            const db = request.result;
            if (!db.objectStoreNames.contains('pendingActions')) {
                db.createObjectStore('pendingActions', { keyPath: 'id' });
            }
        };
    });
}

async function removePendingAction(actionId) {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open('LibraryDB', 1);
        
        request.onerror = () => reject(request.error);
        request.onsuccess = () => {
            const db = request.result;
            const transaction = db.transaction(['pendingActions'], 'readwrite');
            const store = transaction.objectStore('pendingActions');
            const deleteRequest = store.delete(actionId);
            
            deleteRequest.onsuccess = () => resolve();
            deleteRequest.onerror = () => resolve();
        };
    });
}

// Periodic Background Sync (if supported)
self.addEventListener('periodicsync', function(event) {
    console.log('⏰ Periodic Background Sync:', event.tag);
    
    if (event.tag === 'library-data-sync') {
        event.waitUntil(syncLibraryData());
    }
});

async function syncLibraryData() {
    try {
        // Kitap verilerini güncelle
        const booksResponse = await fetch('/api/books/search?limit=50');
        if (booksResponse.ok) {
            const cache = await caches.open(DATA_CACHE_NAME);
            cache.put('/api/books/search?limit=50', booksResponse.clone());
        }
        
        // İstatistikleri güncelle
        const statsResponse = await fetch('/api/stats');
        if (statsResponse.ok) {
            const cache = await caches.open(DATA_CACHE_NAME);
            cache.put('/api/stats', statsResponse.clone());
        }
        
        console.log('✅ Periodic sync tamamlandı');
    } catch (error) {
        console.error('❌ Periodic sync hatası:', error);
    }
}

console.log('🔧 Service Worker v1.1.0 yüklendi - Background Sync destekli!'); 