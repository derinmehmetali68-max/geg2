// Analytics Dashboard JavaScript
class AnalyticsDashboard {
    constructor() {
        this.charts = {};
        this.init();
    }

    init() {
        this.loadDashboard();
        this.setupEventListeners();
    }

    setupEventListeners() {
        document.getElementById('refresh-btn')?.addEventListener('click', () => {
            this.refreshDashboard();
        });

        document.getElementById('export-btn')?.addEventListener('click', () => {
            this.exportReport();
        });
    }

    async loadDashboard() {
        try {
            await this.loadKPIs();
            await this.loadCharts();
        } catch (error) {
            console.error('Dashboard yükleme hatası:', error);
        }
    }

    async loadKPIs() {
        try {
            const response = await fetch('/api/analytics/kpis');
            const data = await response.json();
            
            if (data.success) {
                this.updateKPIs(data.kpis);
            }
        } catch (error) {
            console.error('KPI yükleme hatası:', error);
        }
    }

    updateKPIs(kpis) {
        Object.keys(kpis).forEach(key => {
            const element = document.getElementById(`kpi-${key}`);
            if (element) {
                element.textContent = kpis[key].toLocaleString('tr-TR');
            }
        });
    }

    async loadCharts() {
        try {
            const response = await fetch('/api/analytics/charts');
            const data = await response.json();
            
            if (data.success) {
                this.createBorrowTrendChart(data.borrowTrend);
                this.createCategoryChart(data.categories);
            }
        } catch (error) {
            console.error('Chart yükleme hatası:', error);
        }
    }

    createBorrowTrendChart(data) {
        const ctx = document.getElementById('borrowTrendChart');
        if (!ctx) return;

        if (this.charts.borrowTrend) {
            this.charts.borrowTrend.destroy();
        }

        this.charts.borrowTrend = new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: [{
                    label: 'Ödünç Alınan Kitaplar',
                    data: data.values,
                    borderColor: 'rgb(75, 192, 192)',
                    backgroundColor: 'rgba(75, 192, 192, 0.2)',
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                scales: {
                    y: { beginAtZero: true }
                }
            }
        });
    }

    createCategoryChart(data) {
        const ctx = document.getElementById('categoryChart');
        if (!ctx) return;

        if (this.charts.category) {
            this.charts.category.destroy();
        }

        this.charts.category = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: data.labels,
                datasets: [{
                    data: data.values,
                    backgroundColor: ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40']
                }]
            },
            options: {
                responsive: true
            }
        });
    }

    async refreshDashboard() {
        await this.loadDashboard();
        this.showToast('Dashboard güncellendi', 'success');
    }

    exportReport() {
        const url = '/api/analytics/export?format=excel';
        window.open(url, '_blank');
        this.showToast('Rapor indiriliyor...', 'info');
    }

    showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `alert alert-${type} position-fixed`;
        toast.style.cssText = 'top: 20px; right: 20px; z-index: 1050; max-width: 300px;';
        toast.textContent = message;
        
        document.body.appendChild(toast);
        
        setTimeout(() => {
            toast.remove();
        }, 3000);
    }
}

// Initialize dashboard
document.addEventListener('DOMContentLoaded', function() {
    if (document.getElementById('analytics-dashboard')) {
        new AnalyticsDashboard();
    }
}); 