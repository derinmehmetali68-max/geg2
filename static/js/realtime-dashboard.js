/**
 * Real-time Dashboard Enhancements
 * WebSocket tabanlı canlı güncellemeler
 */

class RealTimeDashboard {
    constructor() {
        this.socket = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;
        this.isConnected = false;
        
        this.init();
    }

    init() {
        this.connectWebSocket();
        this.setupEventListeners();
        this.startHeartbeat();
    }

    connectWebSocket() {
        try {
            // WebSocket bağlantısı
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws/dashboard`;
            
            this.socket = new WebSocket(wsUrl);
            
            this.socket.onopen = () => {
                console.log('✅ WebSocket bağlantısı kuruldu');
                this.isConnected = true;
                this.reconnectAttempts = 0;
                this.showConnectionStatus('connected');
            };
            
            this.socket.onmessage = (event) => {
                this.handleMessage(JSON.parse(event.data));
            };
            
            this.socket.onclose = () => {
                console.log('⚠️ WebSocket bağlantısı kapandı');
                this.isConnected = false;
                this.showConnectionStatus('disconnected');
                this.attemptReconnect();
            };
            
            this.socket.onerror = (error) => {
                console.error('❌ WebSocket hatası:', error);
                this.showConnectionStatus('error');
            };
            
        } catch (error) {
            console.error('WebSocket bağlantı hatası:', error);
            this.fallbackToPolling();
        }
    }

    handleMessage(data) {
        switch (data.type) {
            case 'kpi_update':
                this.updateKPIs(data.payload);
                break;
            case 'new_transaction':
                this.showNewTransaction(data.payload);
                break;
            case 'user_activity':
                this.updateUserActivity(data.payload);
                break;
            case 'system_alert':
                this.showSystemAlert(data.payload);
                break;
            case 'book_status_change':
                this.updateBookStatus(data.payload);
                break;
        }
    }

    updateKPIs(kpis) {
        Object.keys(kpis).forEach(key => {
            const element = document.getElementById(`kpi-${key}`);
            if (element) {
                this.animateValue(element, parseInt(element.textContent) || 0, kpis[key]);
            }
        });
    }

    animateValue(element, start, end) {
        const duration = 1000;
        const startTime = Date.now();
        
        const animate = () => {
            const elapsed = Date.now() - startTime;
            const progress = Math.min(elapsed / duration, 1);
            
            const current = Math.floor(start + (end - start) * progress);
            element.textContent = current.toLocaleString('tr-TR');
            
            if (progress < 1) {
                requestAnimationFrame(animate);
            }
        };
        
        animate();
    }

    showNewTransaction(transaction) {
        const notification = document.createElement('div');
        notification.className = 'notification success show';
        notification.innerHTML = `
            <div class="notification-header">
                <strong>Yeni İşlem</strong>
                <button class="btn-close" onclick="this.parentElement.parentElement.remove()"></button>
            </div>
            <div class="notification-body">
                <p>${transaction.type}: ${transaction.book_title}</p>
                <small>Üye: ${transaction.member_name}</small>
            </div>
        `;
        
        document.body.appendChild(notification);
        
        // Auto remove after 5 seconds
        setTimeout(() => {
            if (notification.parentElement) {
                notification.remove();
            }
        }, 5000);
    }

    updateUserActivity(activity) {
        const activityList = document.getElementById('user-activity-list');
        if (activityList) {
            const activityItem = document.createElement('div');
            activityItem.className = 'activity-item new';
            activityItem.innerHTML = `
                <div class="activity-icon">
                    <i class="bi bi-person"></i>
                </div>
                <div class="activity-content">
                    <div class="activity-text">${activity.message}</div>
                    <div class="activity-time">${new Date(activity.timestamp).toLocaleString('tr-TR')}</div>
                </div>
            `;
            
            activityList.insertBefore(activityItem, activityList.firstChild);
            
            // Remove old items (keep only 10)
            while (activityList.children.length > 10) {
                activityList.removeChild(activityList.lastChild);
            }
            
            // Remove 'new' class after animation
            setTimeout(() => {
                activityItem.classList.remove('new');
            }, 1000);
        }
    }

    showSystemAlert(alert) {
        const alertElement = document.createElement('div');
        alertElement.className = `alert alert-${alert.level} alert-dismissible fade show position-fixed`;
        alertElement.style.cssText = 'top: 20px; right: 20px; z-index: 1060; max-width: 400px;';
        alertElement.innerHTML = `
            <strong>${alert.title}</strong> ${alert.message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        document.body.appendChild(alertElement);
    }

    updateBookStatus(bookData) {
        const bookElement = document.querySelector(`[data-isbn="${bookData.isbn}"]`);
        if (bookElement) {
            const statusBadge = bookElement.querySelector('.book-status');
            if (statusBadge) {
                statusBadge.className = `book-status ${bookData.status}`;
                statusBadge.textContent = bookData.status === 'available' ? 'Mevcut' : 'Ödünçte';
            }
        }
    }

    showConnectionStatus(status) {
        const indicator = document.getElementById('connection-indicator');
        if (indicator) {
            indicator.className = `connection-indicator ${status}`;
            
            const statusText = {
                'connected': '🟢 Bağlı',
                'disconnected': '🟡 Bağlantı Kesildi',
                'error': '🔴 Hata'
            };
            
            indicator.textContent = statusText[status] || '❓ Bilinmiyor';
        }
    }

    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
            
            console.log(`🔄 Yeniden bağlanma denemesi ${this.reconnectAttempts}/${this.maxReconnectAttempts} (${delay}ms sonra)`);
            
            setTimeout(() => {
                this.connectWebSocket();
            }, delay);
        } else {
            console.log('❌ Maksimum yeniden bağlanma denemesi aşıldı, polling moduna geçiliyor');
            this.fallbackToPolling();
        }
    }

    fallbackToPolling() {
        console.log('📡 Polling moduna geçildi');
        
        // Poll every 30 seconds
        setInterval(() => {
            if (!this.isConnected) {
                this.fetchUpdates();
            }
        }, 30000);
    }

    async fetchUpdates() {
        try {
            const response = await fetch('/api/dashboard/updates');
            const data = await response.json();
            
            if (data.success) {
                this.updateKPIs(data.kpis);
            }
        } catch (error) {
            console.error('Polling güncellemesi hatası:', error);
        }
    }

    startHeartbeat() {
        setInterval(() => {
            if (this.isConnected && this.socket.readyState === WebSocket.OPEN) {
                this.socket.send(JSON.stringify({ type: 'ping' }));
            }
        }, 30000); // 30 seconds
    }

    setupEventListeners() {
        // Page visibility change
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                console.log('📱 Sayfa arka plana geçti');
            } else {
                console.log('📱 Sayfa ön plana geçti');
                if (!this.isConnected) {
                    this.connectWebSocket();
                }
            }
        });

        // Window focus/blur
        window.addEventListener('focus', () => {
            if (!this.isConnected) {
                this.connectWebSocket();
            }
        });
    }

    sendMessage(type, payload) {
        if (this.isConnected && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify({ type, payload }));
        }
    }

    disconnect() {
        if (this.socket) {
            this.socket.close();
        }
    }
}

// Auto-initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    if (document.getElementById('dashboard-container')) {
        window.realTimeDashboard = new RealTimeDashboard();
    }
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (window.realTimeDashboard) {
        window.realTimeDashboard.disconnect();
    }
}); 