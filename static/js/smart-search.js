/**
 * Smart Search System
 * AI destekli akıllı arama ve öneri sistemi
 */

class SmartSearch {
    constructor(searchInputId, suggestionsId) {
        this.searchInput = document.getElementById(searchInputId);
        this.suggestionsContainer = document.getElementById(suggestionsId);
        this.searchHistory = JSON.parse(localStorage.getItem('searchHistory') || '[]');
        this.searchCache = new Map();
        this.debounceTimer = null;
        this.currentRequest = null;
        
        this.init();
    }

    init() {
        if (!this.searchInput) return;
        
        this.setupEventListeners();
        this.createSuggestionsContainer();
        this.loadSearchHistory();
    }

    setupEventListeners() {
        // Search input events
        this.searchInput.addEventListener('input', (e) => {
            this.handleInput(e.target.value);
        });

        this.searchInput.addEventListener('focus', () => {
            this.showSuggestions();
        });

        this.searchInput.addEventListener('keydown', (e) => {
            this.handleKeyNavigation(e);
        });

        // Click outside to hide suggestions
        document.addEventListener('click', (e) => {
            if (!this.searchInput.contains(e.target) && 
                !this.suggestionsContainer.contains(e.target)) {
                this.hideSuggestions();
            }
        });
    }

    createSuggestionsContainer() {
        if (!this.suggestionsContainer) {
            this.suggestionsContainer = document.createElement('div');
            this.suggestionsContainer.id = 'search-suggestions';
            this.suggestionsContainer.className = 'search-suggestions';
            this.searchInput.parentNode.appendChild(this.suggestionsContainer);
        }
    }

    handleInput(query) {
        clearTimeout(this.debounceTimer);
        
        if (query.length < 2) {
            this.showRecentSearches();
            return;
        }

        this.debounceTimer = setTimeout(() => {
            this.performSearch(query);
        }, 300);
    }

    async performSearch(query) {
        // Cancel previous request
        if (this.currentRequest) {
            this.currentRequest.abort();
        }

        // Check cache first
        if (this.searchCache.has(query)) {
            this.displaySuggestions(this.searchCache.get(query));
            return;
        }

        try {
            this.showLoadingState();
            
            const controller = new AbortController();
            this.currentRequest = controller;

            // Smart search API call
            const response = await fetch('/api/search/smart', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    query: query,
                    include_ai_suggestions: true,
                    max_results: 10
                }),
                signal: controller.signal
            });

            if (!response.ok) {
                throw new Error('Search failed');
            }

            const data = await response.json();
            
            // Cache results
            this.searchCache.set(query, data);
            
            this.displaySuggestions(data);
            
        } catch (error) {
            if (error.name !== 'AbortError') {
                console.error('Search error:', error);
                this.showErrorState();
            }
        } finally {
            this.currentRequest = null;
        }
    }

    displaySuggestions(data) {
        this.suggestionsContainer.innerHTML = '';

        if (!data.suggestions || data.suggestions.length === 0) {
            this.showNoResults();
            return;
        }

        // Group suggestions by type
        const groups = {
            books: data.suggestions.filter(s => s.type === 'book'),
            authors: data.suggestions.filter(s => s.type === 'author'),
            categories: data.suggestions.filter(s => s.type === 'category'),
            ai_suggestions: data.ai_suggestions || []
        };

        // Display book suggestions
        if (groups.books.length > 0) {
            this.addSuggestionGroup('📚 Kitaplar', groups.books, 'book');
        }

        // Display author suggestions
        if (groups.authors.length > 0) {
            this.addSuggestionGroup('✍️ Yazarlar', groups.authors, 'author');
        }

        // Display category suggestions
        if (groups.categories.length > 0) {
            this.addSuggestionGroup('📂 Kategoriler', groups.categories, 'category');
        }

        // Display AI suggestions
        if (groups.ai_suggestions.length > 0) {
            this.addSuggestionGroup('🤖 AI Önerileri', groups.ai_suggestions, 'ai');
        }

        this.showSuggestions();
    }

    addSuggestionGroup(title, items, type) {
        const groupElement = document.createElement('div');
        groupElement.className = 'suggestion-group';
        
        const titleElement = document.createElement('div');
        titleElement.className = 'suggestion-group-title';
        titleElement.textContent = title;
        groupElement.appendChild(titleElement);

        items.forEach(item => {
            const suggestionElement = document.createElement('div');
            suggestionElement.className = 'search-suggestion';
            suggestionElement.dataset.type = type;
            suggestionElement.dataset.value = item.value || item.title;
            
            suggestionElement.innerHTML = this.formatSuggestion(item, type);
            
            suggestionElement.addEventListener('click', () => {
                this.selectSuggestion(item, type);
            });

            groupElement.appendChild(suggestionElement);
        });

        this.suggestionsContainer.appendChild(groupElement);
    }

    formatSuggestion(item, type) {
        switch (type) {
            case 'book':
                return `
                    <div class="suggestion-content">
                        <div class="suggestion-title">${this.highlightMatch(item.title)}</div>
                        <div class="suggestion-subtitle">${item.authors || 'Bilinmeyen Yazar'}</div>
                        <div class="suggestion-meta">
                            <span class="badge bg-${item.available ? 'success' : 'warning'}">
                                ${item.available ? 'Mevcut' : 'Ödünçte'}
                            </span>
                            ${item.category ? `<span class="category">${item.category}</span>` : ''}
                        </div>
                    </div>
                `;
            
            case 'author':
                return `
                    <div class="suggestion-content">
                        <div class="suggestion-title">${this.highlightMatch(item.name)}</div>
                        <div class="suggestion-subtitle">${item.book_count} kitap</div>
                    </div>
                `;
            
            case 'category':
                return `
                    <div class="suggestion-content">
                        <div class="suggestion-title">${this.highlightMatch(item.name)}</div>
                        <div class="suggestion-subtitle">${item.book_count} kitap</div>
                    </div>
                `;
            
            case 'ai':
                return `
                    <div class="suggestion-content">
                        <div class="suggestion-title">${item.title}</div>
                        <div class="suggestion-subtitle">${item.reason}</div>
                        <div class="suggestion-meta">
                            <span class="badge bg-info">AI Önerisi</span>
                            <span class="confidence">%${Math.round(item.confidence * 100)} güven</span>
                        </div>
                    </div>
                `;
            
            default:
                return `<div class="suggestion-content">${item.title || item.name}</div>`;
        }
    }

    highlightMatch(text) {
        const query = this.searchInput.value.toLowerCase();
        const regex = new RegExp(`(${query})`, 'gi');
        return text.replace(regex, '<mark>$1</mark>');
    }

    selectSuggestion(item, type) {
        // Update search input
        this.searchInput.value = item.title || item.name || item.value;
        
        // Add to search history
        this.addToSearchHistory(item, type);
        
        // Hide suggestions
        this.hideSuggestions();
        
        // Navigate or perform action based on type
        switch (type) {
            case 'book':
                if (item.isbn) {
                    window.location.href = `/book/${item.isbn}`;
                }
                break;
            
            case 'author':
                window.location.href = `/search?author=${encodeURIComponent(item.name)}`;
                break;
            
            case 'category':
                window.location.href = `/search?category=${encodeURIComponent(item.name)}`;
                break;
            
            case 'ai':
                if (item.action === 'search') {
                    window.location.href = `/search?q=${encodeURIComponent(item.query)}`;
                } else if (item.action === 'recommend') {
                    window.location.href = `/recommendations?based_on=${encodeURIComponent(item.title)}`;
                }
                break;
        }
    }

    addToSearchHistory(item, type) {
        const historyItem = {
            title: item.title || item.name,
            type: type,
            timestamp: Date.now(),
            data: item
        };

        // Remove duplicates
        this.searchHistory = this.searchHistory.filter(h => 
            h.title !== historyItem.title || h.type !== historyItem.type
        );

        // Add to beginning
        this.searchHistory.unshift(historyItem);

        // Keep only last 20 searches
        this.searchHistory = this.searchHistory.slice(0, 20);

        // Save to localStorage
        localStorage.setItem('searchHistory', JSON.stringify(this.searchHistory));
    }

    showRecentSearches() {
        if (this.searchHistory.length === 0) {
            this.hideSuggestions();
            return;
        }

        this.suggestionsContainer.innerHTML = '';
        
        const titleElement = document.createElement('div');
        titleElement.className = 'suggestion-group-title';
        titleElement.textContent = '🕐 Son Aramalar';
        this.suggestionsContainer.appendChild(titleElement);

        this.searchHistory.slice(0, 5).forEach(item => {
            const suggestionElement = document.createElement('div');
            suggestionElement.className = 'search-suggestion recent';
            
            suggestionElement.innerHTML = `
                <div class="suggestion-content">
                    <div class="suggestion-title">${item.title}</div>
                    <div class="suggestion-subtitle">${this.getTypeLabel(item.type)}</div>
                </div>
                <button class="remove-history" onclick="event.stopPropagation(); smartSearch.removeFromHistory('${item.title}', '${item.type}')">
                    <i class="bi bi-x"></i>
                </button>
            `;
            
            suggestionElement.addEventListener('click', () => {
                this.selectSuggestion(item.data, item.type);
            });

            this.suggestionsContainer.appendChild(suggestionElement);
        });

        this.showSuggestions();
    }

    removeFromHistory(title, type) {
        this.searchHistory = this.searchHistory.filter(h => 
            h.title !== title || h.type !== type
        );
        localStorage.setItem('searchHistory', JSON.stringify(this.searchHistory));
        this.showRecentSearches();
    }

    getTypeLabel(type) {
        const labels = {
            'book': 'Kitap',
            'author': 'Yazar',
            'category': 'Kategori',
            'ai': 'AI Önerisi'
        };
        return labels[type] || 'Arama';
    }

    showLoadingState() {
        this.suggestionsContainer.innerHTML = `
            <div class="suggestion-loading">
                <div class="spinner-border spinner-border-sm" role="status"></div>
                <span class="ms-2">Aranıyor...</span>
            </div>
        `;
        this.showSuggestions();
    }

    showErrorState() {
        this.suggestionsContainer.innerHTML = `
            <div class="suggestion-error">
                <i class="bi bi-exclamation-triangle"></i>
                <span class="ms-2">Arama sırasında hata oluştu</span>
            </div>
        `;
        this.showSuggestions();
    }

    showNoResults() {
        this.suggestionsContainer.innerHTML = `
            <div class="suggestion-no-results">
                <i class="bi bi-search"></i>
                <span class="ms-2">Sonuç bulunamadı</span>
            </div>
        `;
        this.showSuggestions();
    }

    showSuggestions() {
        this.suggestionsContainer.style.display = 'block';
    }

    hideSuggestions() {
        this.suggestionsContainer.style.display = 'none';
    }

    handleKeyNavigation(e) {
        const suggestions = this.suggestionsContainer.querySelectorAll('.search-suggestion');
        const current = this.suggestionsContainer.querySelector('.search-suggestion.active');
        
        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                if (current) {
                    current.classList.remove('active');
                    const next = current.nextElementSibling;
                    if (next && next.classList.contains('search-suggestion')) {
                        next.classList.add('active');
                    } else {
                        suggestions[0]?.classList.add('active');
                    }
                } else {
                    suggestions[0]?.classList.add('active');
                }
                break;
            
            case 'ArrowUp':
                e.preventDefault();
                if (current) {
                    current.classList.remove('active');
                    const prev = current.previousElementSibling;
                    if (prev && prev.classList.contains('search-suggestion')) {
                        prev.classList.add('active');
                    } else {
                        suggestions[suggestions.length - 1]?.classList.add('active');
                    }
                } else {
                    suggestions[suggestions.length - 1]?.classList.add('active');
                }
                break;
            
            case 'Enter':
                if (current) {
                    e.preventDefault();
                    current.click();
                }
                break;
            
            case 'Escape':
                this.hideSuggestions();
                break;
        }
    }

    loadSearchHistory() {
        // Load search history from localStorage
        this.searchHistory = JSON.parse(localStorage.getItem('searchHistory') || '[]');
    }

    clearSearchHistory() {
        this.searchHistory = [];
        localStorage.removeItem('searchHistory');
        this.hideSuggestions();
    }
}

// Auto-initialize
document.addEventListener('DOMContentLoaded', function() {
    // Initialize for main search
    if (document.getElementById('search-input')) {
        window.smartSearch = new SmartSearch('search-input', 'search-suggestions');
    }
    
    // Initialize for navbar search
    if (document.getElementById('navbar-search')) {
        window.navbarSmartSearch = new SmartSearch('navbar-search', 'navbar-suggestions');
    }
}); 