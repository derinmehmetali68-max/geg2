/**
 * Gelişmiş Kiosk Self-Check Sistemi
 * QR Tarama + Online Ödünç + Rezervasyon + Akıllı Öneriler
 */

class AdvancedKioskSystem {
    constructor() {
        this.currentMember = null;
        this.currentBook = null;
        this.scanner = null;
        this.isScanning = false;
        this.scanStep = 'member'; // 'member' -> 'book' -> 'action'
        this.speechSynthesis = window.speechSynthesis;
        this.recognition = null;
        
        this.init();
    }
    
    init() {
        console.log('🚀 Gelişmiş Kiosk Sistemi başlatılıyor...');
        
        // Event listeners
        this.setupEventListeners();
        
        // Ses tanıma desteği
        this.initSpeechRecognition();
        
        // Popüler kitapları yükle
        this.loadPopularBooks();
        
        // Son işlemleri yükle
        this.loadRecentTransactions();
        
        // Otomatik yenileme
        setInterval(() => this.loadRecentTransactions(), 30000);
        
        // Hoş geldin mesajı
        this.speak('Cumhuriyet Anadolu Lisesi Kütüphanesine hoş geldiniz!');
    }
    
    setupEventListeners() {
        // Giriş işlemleri - advanced_kiosk.html'de schoolNumber kullanılıyor
        $('#manualLoginForm').on('submit', (e) => {
            e.preventDefault();
            this.loginMember();
        });
        
        $('#loginBtn').on('click', () => this.loginMember());
        $('#scanMemberBtn').on('click', () => this.startMemberScan());
        $('#schoolNumber').on('keypress', (e) => {
            if (e.which === 13) {
                e.preventDefault();
                this.loginMember();
            }
        });
        
        // Scanner kontrolü
        $('#toggleScanner').on('click', () => this.toggleScanner());
        
        // Kitap arama
        $('#searchBooks').on('click', () => this.searchBooks());
        $('#bookSearchInput').on('keypress', (e) => {
            if (e.which === 13) this.searchBooks();
        });
        $('#voiceSearch').on('click', () => this.startVoiceSearch());
        
        // Ödünç alma ve iade işlemleri
        $('#requestBorrow').on('click', () => this.requestBorrow());
        $('#processReturn').on('click', () => this.processReturn());
        $('#scanBorrowQR').on('click', () => this.startTransactionQRScan('borrow'));
        $('#scanReturnQR').on('click', () => this.startTransactionQRScan('return'));
        $('#closeQRScanner').on('click', () => this.closeQRScanner());
        
        // Rezervasyon
        $('#reservationForm').on('submit', (e) => {
            e.preventDefault();
            this.makeReservation();
        });
        
        // İşlem onayı
        $('#confirmActionBtn').on('click', () => this.executeAction());
        
        // Tab değişikliklerinde scanner'ı durdur
        $('button[data-bs-toggle="pill"]').on('shown.bs.tab', (e) => {
            if (e.target.id !== 'scan-tab') {
                this.stopScanner();
            }
        });
        
        // Çıkış butonu
        $('#logoutBtn').on('click', (e) => {
            e.preventDefault();
            this.logout();
        });
        
        // Otomatik logout (5 dakika inaktivite)
        this.setupAutoLogout();
    }
    
    setupAutoLogout() {
        let inactivityTimer;
        const resetTimer = () => {
            clearTimeout(inactivityTimer);
            inactivityTimer = setTimeout(() => {
                if (this.currentMember) {
                    this.showNotification('Güvenlik nedeniyle oturum sonlandırıldı', 'warning');
                    this.logout();
                }
            }, 300000); // 5 dakika
        };
        
        // Kullanıcı aktivitelerini izle
        $(document).on('click keypress mousemove touchstart', resetTimer);
        resetTimer();
    }
    
    // Üye Giriş İşlemleri
    async loginMember() {
        // Okul numarasını al
        const memberInput = $('#schoolNumber').val().trim();
        
        if (!memberInput) {
            this.showNotification('Lütfen okul numaranızı girin', 'error');
            return;
        }
        
        this.updateStatus('⏳', 'Üye doğrulanıyor...', 'Lütfen bekleyin');
        this.showProgress(30);
        
        try {
            console.log('Üye doğrulanıyor:', memberInput);
            
            const response = await $.ajax({
                url: `/api/kiosk/verify-member/${memberInput}`,
                method: 'GET'
            });
            
            console.log('API yanıtı:', response);
            
            if (response.success) {
                this.currentMember = response.member;
            console.log('Üye başarıyla doğrulandı:', this.currentMember);
            
            // Session token oluştur
            try {
                const sessionResp = await $.ajax({
                    url: '/api/kiosk/start-session',
                    method: 'POST',
                    contentType: 'application/json',
                    data: JSON.stringify({ member_id: this.currentMember.id })
                });
                if (sessionResp.success) {
                    this.currentSession = { token: sessionResp.token, member_id: this.currentMember.id };
                    console.log('Session oluşturuldu:', this.currentSession);
                }
            } catch (e) {
                console.warn('Session başlatılamadı', e);
            }
            
            this.showMemberLogin();
            this.speak(`Hoş geldiniz ${response.member.name}`);
            this.showProgress(100);
            
            // Üye profilini ve önerileri yükle
            setTimeout(() => {
                this.loadMemberProfile();
                this.loadRecommendations();
            }, 100);
        } else {
            console.error('Üye doğrulama başarısız:', response.message);
            this.showNotification('Üye bulunamadı: ' + response.message, 'error');
            this.showProgress(0);
        }
        } catch (error) {
            console.error('Üye doğrulama hatası:', error);
            this.showNotification('Bağlantı hatası: ' + (error.responseJSON?.message || error.statusText || 'Bilinmeyen hata'), 'error');
            this.showProgress(0);
        }
    }
    
    showMemberLogin() {
        $('#loginPanel').addClass('d-none');
        $('#actionTabs').removeClass('d-none');
        
        this.updateStatus('👋', `Hoş geldiniz ${this.currentMember.name}!`, 
                         'İşlem yapmak için yukarıdaki sekmelerden birini seçin');
        
        // Üye bilgi kartını güncelle
        this.updateMemberInfoCard();
    }
    
    updateMemberInfoCard() {
        const member = this.currentMember;
        const html = `
            <div class="text-center fade-in-up">
                <div class="mb-3">
                    <i class="bi bi-person-circle display-4 text-primary"></i>
                </div>
                <h5 class="mb-1">${member.name}</h5>
                <p class="text-muted mb-2">Numara: ${member.number}</p>
                <p class="text-muted mb-3">Sınıf: ${member.class}</p>
                <div class="row text-center">
                    <div class="col-6">
                        <div class="border-end">
                            <div class="h4 text-primary mb-0">${member.active_books}</div>
                            <small class="text-muted">Aktif Kitap</small>
                        </div>
                    </div>
                    <div class="col-6">
                        <div class="h4 text-success mb-0">${member.max_books - member.active_books}</div>
                        <small class="text-muted">Kalan Hak</small>
                    </div>
                </div>
                <button class="btn btn-outline-secondary btn-sm mt-3" onclick="kioskSystem.logout()">
                    <i class="bi bi-box-arrow-right"></i> Çıkış
                </button>
            </div>
        `;
        $('#memberInfoCard').html(html);
    }
    
    logout() {
        this.currentMember = null;
        this.currentBook = null;
        this.currentSession = null;
        this.stopScanner();
        
        $('#actionTabs').addClass('d-none');
        $('#loginPanel').removeClass('d-none');
        $('#schoolNumber, #firstName').val('');
        
        // UI'yi sıfırla
        this.updateStatus('🔍', 'Hoş Geldiniz!', 'İşleme başlamak için üye kartınızı tarayın veya üye numaranızı girin');
        $('#memberInfoCard').html(`
            <div class="text-center">
                <i class="bi bi-person-circle display-4 text-muted"></i>
                <p class="text-muted">Üye girişi yapılmadı</p>
            </div>
        `);
        
        this.speak('Oturum sonlandırıldı. İyi günler dileriz!');
    }
    
    // QR Scanner İşlemleri
    startMemberScan() {
        this.scanStep = 'member';
        this.updateStatus('📱', 'QR kod taranıyor...', 'Üye kartınızdaki QR kodu kameraya gösterin');
        this.startScanner();
    }
    
    toggleScanner() {
        if (this.isScanning) {
            this.stopScanner();
        } else {
            this.scanStep = 'book';
            this.startScanner();
        }
    }
    
    startScanner() {
        if (this.isScanning) return;
        
        try {
            this.scanner = new Html5QrcodeScanner(
                "qr-reader",
                {
                    fps: 20,
                    qrbox: { width: 300, height: 300 },
                    aspectRatio: 1.0,
                    experimentalFeatures: {
                        useBarCodeDetectorIfSupported: true
                    }
                },
                false
            );
            
            this.scanner.render(
                (decodedText, decodedResult) => this.onScanSuccess(decodedText, decodedResult),
                (error) => {} // Sessiz hata
            );
            
            this.isScanning = true;
            $('#toggleScanner').html('<i class="bi bi-stop-circle"></i> Tarayıcıyı Durdur');
            $('#qr-reader').addClass('active');
            
            this.speak('QR kod tarayıcı başlatıldı');
            
        } catch (error) {
            console.error('Scanner başlatma hatası:', error);
            this.showNotification('Kamera erişimi sağlanamadı', 'error');
        }
    }
    
    stopScanner() {
        if (this.scanner && this.isScanning) {
            this.scanner.clear();
            this.scanner = null;
            this.isScanning = false;
            $('#toggleScanner').html('<i class="bi bi-camera"></i> Tarayıcıyı Başlat');
            $('#qr-reader').removeClass('active');
        }
    }
    
    onScanSuccess(decodedText, decodedResult) {
        console.log('QR kod okundu:', decodedText);
        
        // Ses ve titreşim geri bildirimi
        this.playBeepSound();
        this.vibrate();
        
        // Görsel geri bildirim
        $('#qr-reader').addClass('sound-feedback');
        setTimeout(() => $('#qr-reader').removeClass('sound-feedback'), 300);
        
        if (this.scanStep === 'member') {
            this.processMemberQR(decodedText);
        } else if (this.scanStep === 'book') {
            this.processBookQR(decodedText);
        }
        
        this.stopScanner();
    }
    
    async processMemberQR(qrData) {
        $('#schoolNumber').val(qrData);
        await this.loginMember();
    }
    
    async processBookQR(isbn) {
        if (!this.currentMember) {
            this.showNotification('Önce üye girişi yapmanız gerekiyor', 'warning');
            return;
        }
        
        this.updateStatus('⏳', 'Kitap doğrulanıyor...', 'Lütfen bekleyin');
        
        try {
            const response = await $.ajax({
                url: `/api/kiosk/verify-book/${isbn}`,
                method: 'GET',
                data: { member_id: this.currentMember.id }
            });
            
            if (response.success) {
                this.currentBook = response.book;
                this.showActionSelection();
            } else {
                this.showNotification('Kitap hatası: ' + response.message, 'error');
            }
        } catch (error) {
            this.showNotification('Kitap doğrulama hatası', 'error');
        }
    }
    
    showActionSelection() {
        const book = this.currentBook;
        const member = this.currentMember;
        
        let actionHtml = '';
        let actionText = '';
        
        if (book.user_has_book) {
            // İade işlemi
            actionHtml = `
                <div class="alert alert-info">
                    <h5><i class="bi bi-arrow-return-left"></i> İade İşlemi</h5>
                    <p>Bu kitabı iade etmek istediğinizden emin misiniz?</p>
                    <div class="row">
                        <div class="col-md-6">
                            <strong>Kitap:</strong> ${book.title}<br>
                            <strong>Yazar:</strong> ${book.authors}<br>
                            <strong>Ödünç Tarihi:</strong> ${book.borrow_date}
                        </div>
                        <div class="col-md-6">
                            <strong>İade Tarihi:</strong> ${book.due_date}<br>
                            <strong>Üye:</strong> ${member.name}<br>
                            <strong>Numara:</strong> ${member.number}
                        </div>
                    </div>
                </div>
            `;
            actionText = 'İade Et';
            this.pendingAction = 'return';
        } else {
            // Ödünç alma işlemi
            actionHtml = `
                <div class="alert alert-success">
                    <h5><i class="bi bi-plus-circle"></i> Ödünç Alma İşlemi</h5>
                    <p>Bu kitabı ödünç almak istediğinizden emin misiniz?</p>
                    <div class="row">
                        <div class="col-md-6">
                            <strong>Kitap:</strong> ${book.title}<br>
                            <strong>Yazar:</strong> ${book.authors}<br>
                            <strong>Mevcut:</strong> ${book.available}/${book.total}
                        </div>
                        <div class="col-md-6">
                            <strong>Üye:</strong> ${member.name}<br>
                            <strong>Aktif Kitap:</strong> ${member.active_books}/${member.max_books}<br>
                            <strong>İade Tarihi:</strong> ${this.calculateDueDate()}
                        </div>
                    </div>
                </div>
            `;
            actionText = 'Ödünç Al';
            this.pendingAction = 'borrow';
        }
        
        $('#confirmModalTitle').text('İşlem Onayı');
        $('#confirmModalBody').html(actionHtml);
        $('#confirmActionBtn').html(`<i class="bi bi-check-circle"></i> ${actionText}`);
        
        $('#confirmModal').modal('show');
        
        this.speak(`${book.title} kitabı için ${actionText.toLowerCase()} işlemi onayınızı bekliyor`);
    }
    
    async executeAction() {
        if (!this.pendingAction || !this.currentBook || !this.currentMember) return;
        
        $('#confirmModal').modal('hide');
        this.updateStatus('⏳', 'İşlem gerçekleştiriliyor...', 'Lütfen bekleyin');
        this.showProgress(50);
        
        try {
            const response = await $.ajax({
                url: '/api/kiosk/process-transaction',
                method: 'POST',
                contentType: 'application/json',
                data: JSON.stringify({
                    action: this.pendingAction,
                    isbn: this.currentBook.isbn,
                    member_id: this.currentMember.id,
                    method: 'advanced_kiosk',
                    notes: 'Gelişmiş kiosk sistemi ile işlem'
                })
            });
            
            this.showProgress(100);
            
            if (response.success) {
                this.showSuccessResult(response.message);
                this.loadRecentTransactions();
                this.loadMemberProfile(); // Üye bilgilerini güncelle

                // Donma önleyici: modal kapandıktan sonra state'i temizle ve odak ver
                setTimeout(() => {
                    try { $('#resultModal').modal('hide'); } catch(e) {}
                    this.pendingAction = null;
                    this.currentBook = null;
                    $('#bookSearchInput').trigger('focus');
                }, 1200);
            } else {
                this.showErrorResult(response.message);
            }
        } catch (error) {
            this.showErrorResult('İşlem sırasında hata oluştu');
            this.showProgress(0);
        }
        
        // Reset
        this.currentBook = null;
        this.pendingAction = null;
    }
    
    // Kitap Arama
    async searchBooks() {
        const query = $('#bookSearchInput').val().trim();
        
        if (!query) {
            this.showNotification('Arama terimi girin', 'warning');
            return;
        }
        
        try {
            const response = await $.ajax({
                url: '/api/books/search/quick',
                method: 'GET',
                data: { q: query, limit: 10 }
            });
            
            if (response.success && response.books.length > 0) {
                this.displaySearchResults(response.books);
            } else {
                $('#searchResults').html(`
                    <div class="alert alert-info text-center">
                        <i class="bi bi-search"></i>
                        <p class="mb-0">"${query}" için sonuç bulunamadı</p>
                    </div>
                `);
            }
        } catch (error) {
            this.showNotification('Arama hatası', 'error');
        }
    }
    
    displaySearchResults(books) {
        let html = '<div class="row">';
        
        books.forEach(book => {
            const available = book.available ? 'Mevcut' : 'Ödünçte';
            const badgeClass = book.available ? 'bg-success' : 'bg-warning';
            
            html += `
                <div class="col-md-6 mb-3">
                    <div class="card h-100 border-0 shadow-sm">
                        <div class="card-body">
                            <div class="d-flex">
                                <div class="flex-shrink-0 me-3">
                                    <img src="${book.image_path || '/static/img/no_cover.png'}" 
                                         alt="Kitap Kapağı" style="width: 60px; height: 80px; object-fit: cover; border-radius: 8px;">
                                </div>
                                <div class="flex-grow-1">
                                    <h6 class="card-title mb-1">${book.title}</h6>
                                    <p class="card-text small text-muted mb-2">${book.authors}</p>
                                    <div class="d-flex justify-content-between align-items-center">
                                        <span class="badge ${badgeClass}">${available}</span>
                                        <button class="btn btn-sm btn-primary" onclick="kioskSystem.selectBook('${book.isbn}')">
                                            <i class="bi bi-plus-circle"></i> Seç
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        });
        
        html += '</div>';
        $('#searchResults').html(html);
    }
    
    async selectBook(isbn) {
        if (!this.currentMember) {
            this.showNotification('Önce üye girişi yapmanız gerekiyor', 'warning');
            return;
        }
        
        await this.processBookQR(isbn);
    }
    
    // Rezervasyon İşlemleri
    async makeReservation() {
        const bookInput = $('#reserveBookInput').val().trim();
        const pickupDate = $('#pickupDate').val();
        const pickupTime = $('#pickupTime').val();
        const notes = $('#reserveNotes').val();
        
        if (!bookInput || !pickupDate || !pickupTime) {
            this.showNotification('Tüm alanları doldurun', 'warning');
            return;
        }
        
        if (!this.currentMember) {
            this.showNotification('Önce üye girişi yapmanız gerekiyor', 'warning');
            return;
        }
        
        try {
            // Kiosk modunda rezervasyon özelliği geçici olarak devre dışı
            this.showNotification('Rezervasyon özelliği şu anda kiosk modunda kullanılamıyor. Lütfen kütüphaneciye başvurun.', 'warning');
            
        } catch (error) {
            this.showNotification('Rezervasyon hatası', 'error');
        }
    }
    
    // Veri Yükleme İşlemleri
    async loadPopularBooks() {
        try {
            const response = await $.ajax({
                url: '/api/books/recommendations',
                method: 'GET'
            });
            
            if (response.recommendations && response.recommendations.length > 0) {
                let html = '';
                response.recommendations.slice(0, 5).forEach(book => {
                    html += `
                        <div class="d-flex align-items-center mb-2">
                            <img src="${book.image_path}" alt="" class="me-2" 
                                 style="width: 30px; height: 40px; object-fit: cover; border-radius: 4px;">
                            <div class="flex-grow-1">
                                <div class="small fw-bold">${book.title}</div>
                                <div class="small text-muted">${book.authors}</div>
                            </div>
                        </div>
                    `;
                });
                $('#popularBooks').html(html);
            }
        } catch (error) {
            console.error('Popüler kitaplar yüklenemedi:', error);
        }
    }
    
    async loadRecentTransactions() {
        try {
            const response = await $.ajax({
                url: '/api/kiosk/recent-transactions',
                method: 'GET'
            });
            
            if (response.success && response.transactions.length > 0) {
                let html = '';
                response.transactions.slice(0, 5).forEach(transaction => {
                    const actionIcon = transaction.action === 'borrow' ? 
                        'bi-plus-circle text-success' : 'bi-arrow-return-left text-warning';
                    const actionText = transaction.action === 'borrow' ? 'Ödünç' : 'İade';
                    
                    html += `
                        <div class="d-flex align-items-center mb-2 p-2 bg-light rounded">
                            <i class="bi ${actionIcon} me-2"></i>
                            <div class="flex-grow-1">
                                <div class="small fw-bold">${actionText}</div>
                                <div class="small text-muted">${transaction.book_title}</div>
                                <div class="small text-muted">${transaction.member_name}</div>
                            </div>
                            <small class="text-muted">${transaction.time}</small>
                        </div>
                    `;
                });
                $('#recentTransactions').html(html);
            } else {
                $('#recentTransactions').html('<p class="text-muted text-center">Henüz işlem yok</p>');
            }
        } catch (error) {
            console.error('Son işlemler yüklenemedi:', error);
        }
    }
    
    async loadMemberProfile() {
        if (!this.currentMember) return;
        
        try {
            const response = await $.ajax({
                url: `/api/advanced-kiosk/member-profile/${this.currentMember.id}`,
                method: 'GET'
            });
            
            if (response.success) {
                this.displayMemberBooks(response.active_books);
            }
        } catch (error) {
            console.error('Üye profil bilgileri yüklenemedi:', error);
            // Hata durumunda basit profil göster
            this.displayMemberBooks([]);
        }
    }
    
    displayMemberBooks(books) {
        let html = `
            <div class="row">
                <div class="col-md-6">
                    <h5><i class="bi bi-book"></i> Ödünç Aldığım Kitaplar</h5>
        `;
        
        if (books.length > 0) {
            books.forEach(book => {
                const isOverdue = book.is_overdue;
                const statusClass = isOverdue ? 'text-danger' : 'text-success';
                const statusText = isOverdue ? `${Math.abs(book.days_remaining)} gün gecikme` : `${book.days_remaining} gün kaldı`;
                
                html += `
                    <div class="card mb-2">
                        <div class="card-body p-3">
                            <h6 class="card-title mb-1">${book.title}</h6>
                            <p class="card-text small text-muted mb-2">${book.authors}</p>
                            <div class="d-flex justify-content-between align-items-center">
                                <span class="small ${statusClass}">${statusText}</span>
                                <button class="btn btn-sm btn-outline-primary" onclick="kioskSystem.processBookQR('${book.isbn}')">
                                    İade Et
                                </button>
                            </div>
                        </div>
                    </div>
                `;
            });
        } else {
            html += '<p class="text-muted">Ödünç alınmış kitap yok</p>';
        }
        
        html += `
                </div>
                <div class="col-md-6">
                    <h5><i class="bi bi-calendar"></i> Rezervasyonlarım</h5>
                    <div id="memberReservations">Yükleniyor...</div>
                </div>
            </div>
        `;
        
        $('#memberProfile').html(html);
        this.loadActiveReservations();
    }
    
    async loadActiveReservations() {
        if (!this.currentMember) return;
        
        try {
            // Kiosk modunda rezervasyon bilgileri için basit çözüm
            const html = '<p class="text-muted">Aktif rezervasyon yok</p>';
            $('#activeReservations, #memberReservations').html(html);
        } catch (error) {
            console.error('Rezervasyonlar yüklenemedi:', error);
        }
    }
    
    async loadRecommendations() {
        if (!this.currentMember) return;
        
        try {
            const response = await $.ajax({
                url: `/api/advanced-kiosk/smart-recommendations/${this.currentMember.id}`,
                method: 'GET'
            });
            
            if (response.success && response.recommendations && response.recommendations.length > 0) {
                let html = '';
                response.recommendations.slice(0, 3).forEach(book => {
                    html += `
                        <div class="card mb-2">
                            <div class="card-body p-3">
                                <div class="d-flex">
                                    <img src="${book.image_path || '/static/img/no_cover.png'}" alt="" class="me-2" 
                                         style="width: 40px; height: 55px; object-fit: cover; border-radius: 4px;">
                                    <div class="flex-grow-1">
                                        <h6 class="card-title mb-1">${book.title}</h6>
                                        <p class="card-text small text-muted mb-2">${book.authors}</p>
                                        <small class="text-primary">${book.recommendation_reason || 'Önerilen kitap'}</small>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;
                });
                $('#recommendations').html(html);
            } else {
                $('#recommendations').html('<p class="text-muted text-center">Henüz öneri yok</p>');
            }
        } catch (error) {
            console.error('Öneriler yüklenemedi:', error);
            $('#recommendations').html('<p class="text-muted text-center">Öneriler yüklenemedi</p>');
        }
    }
    
    // Ses Tanıma
    initSpeechRecognition() {
        if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
            this.recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
            this.recognition.lang = 'tr-TR';
            this.recognition.continuous = false;
            this.recognition.interimResults = false;
            
            this.recognition.onresult = (event) => {
                const transcript = event.results[0][0].transcript;
                $('#bookSearchInput').val(transcript);
                this.searchBooks();
                this.speak(`"${transcript}" için arama yapılıyor`);
            };
            
            this.recognition.onerror = (event) => {
                console.error('Ses tanıma hatası:', event.error);
                this.showNotification('Ses tanıma hatası', 'error');
            };
        }
    }
    
    startVoiceSearch() {
        if (this.recognition) {
            this.recognition.start();
            this.showNotification('Konuşun...', 'info');
            this.speak('Aranacak kitabın adını söyleyin');
        } else {
            this.showNotification('Ses tanıma desteklenmiyor', 'error');
        }
    }
    
    // Ödünç Alma İşlemleri
    async requestBorrow() {
        const isbn = $('#borrowISBN').val().trim();
        
        if (!isbn) {
            this.showNotification('Lütfen kitap ISBN numarası girin', 'warning');
            return;
        }
        
        if (!this.currentMember) {
            this.showNotification('Önce giriş yapmanız gerekiyor', 'warning');
            return;
        }
        
        if (!this.currentSession) {
            this.showNotification('Oturum bulunamadı, tekrar giriş yapın', 'error');
            return;
        }
        
        this.updateStatus('⏳', 'Ödünç alma talebi oluşturuluyor...', 'Lütfen bekleyin');
        
        try {
            const response = await $.ajax({
                url: '/api/kiosk/request-borrow',
                method: 'POST',
                contentType: 'application/json',
                data: JSON.stringify({
                    isbn: isbn,
                    session_token: this.currentSession.token
                })
            });
            
            if (response.success) {
                this.showSuccessResult('Ödünç alma talebi başarıyla oluşturuldu!');
                $('#borrowISBN').val('');
            } else {
                this.showErrorResult(response.message || 'Talep oluşturulamadı');
            }
        } catch (error) {
            console.error('Ödünç alma hatası:', error);
            this.showErrorResult('Talep oluşturma hatası');
        }
    }
    
    // İade İşlemi
    async processReturn() {
        const isbn = $('#returnISBN').val().trim();
        
        if (!isbn) {
            this.showNotification('Lütfen iade edilecek kitabın ISBN numarasını girin', 'warning');
            return;
        }
        
        if (!this.currentMember) {
            this.showNotification('Önce giriş yapmanız gerekiyor', 'warning');
            return;
        }
        
        this.updateStatus('⏳', 'İade işlemi gerçekleştiriliyor...', 'Lütfen bekleyin');
        
        try {
            const response = await $.ajax({
                url: '/api/kiosk/process-return',
                method: 'POST',
                contentType: 'application/json',
                data: JSON.stringify({
                    isbn: isbn,
                    member_id: this.currentMember.id,
                    session_token: this.currentSession ? this.currentSession.token : null
                })
            });
            
            if (response.success) {
                this.showSuccessResult('Kitap başarıyla iade edildi!');
                $('#returnISBN').val('');
                this.loadMemberProfile(); // Profili güncelle
            } else {
                this.showErrorResult(response.message || 'İade işlemi başarısız');
            }
        } catch (error) {
            console.error('İade hatası:', error);
            this.showErrorResult('İade işlemi hatası');
        }
    }
    
    // QR Scanner İşlemleri
    startTransactionQRScan(type) {
        this.scanType = type;
        $('#qrScannerCard').show();
        
        try {
            if (this.transactionScanner) {
                this.transactionScanner.clear();
            }
            
            this.transactionScanner = new Html5QrcodeScanner(
                "transactionQRReader",
                {
                    fps: 20,
                    qrbox: { width: 250, height: 250 }
                },
                false
            );
            
            this.transactionScanner.render(
                (decodedText) => {
                    console.log('QR okundu:', decodedText);
                    this.playBeepSound();
                    
                    if (this.scanType === 'borrow') {
                        $('#borrowISBN').val(decodedText);
                    } else {
                        $('#returnISBN').val(decodedText);
                    }
                    
                    this.closeQRScanner();
                },
                (error) => {}
            );
        } catch (error) {
            console.error('QR Scanner hatası:', error);
            this.showNotification('Kamera erişimi sağlanamadı', 'error');
        }
    }
    
    closeQRScanner() {
        $('#qrScannerCard').hide();
        if (this.transactionScanner) {
            this.transactionScanner.clear();
            this.transactionScanner = null;
        }
    }
    
    // Yardımcı Fonksiyonlar
    updateStatus(icon, title, message) {
        $('#statusIcon').text(icon);
        $('#statusTitle').text(title);
        $('#statusMessage').text(message);
    }
    
    showProgress(percent) {
        if (percent > 0) {
            $('#progressBar').removeClass('d-none');
            $('#progressBar .progress-bar').css('width', percent + '%');
        } else {
            $('#progressBar').addClass('d-none');
        }
    }
    
    showSuccessResult(message) {
        $('#resultModalTitle').text('✅ İşlem Başarılı');
        $('#resultModalBody').html(`
            <div class="text-success mb-3">
                <i class="bi bi-check-circle display-4"></i>
            </div>
            <p class="h5">${message}</p>
        `);
        $('#resultModal').modal('show');
        setTimeout(() => {
            try { $('#resultModal').modal('hide'); } catch(e) {}
            $('#bookSearchInput').trigger('focus');
        }, 1200);
        this.speak('İşlem başarıyla tamamlandı');
    }
    
    showErrorResult(message) {
        $('#resultModalTitle').text('❌ İşlem Hatası');
        $('#resultModalBody').html(`
            <div class="text-danger mb-3">
                <i class="bi bi-x-circle display-4"></i>
            </div>
            <p class="h5">${message}</p>
        `);
        $('#resultModal').modal('show');
        setTimeout(() => {
            try { $('#resultModal').modal('hide'); } catch(e) {}
            $('#bookSearchInput').trigger('focus');
        }, 1500);
        this.speak('İşlem sırasında hata oluştu');
    }
    
    showNotification(message, type = 'info') {
        const alertClass = type === 'success' ? 'alert-success' : 
                          type === 'error' ? 'alert-danger' : 
                          type === 'warning' ? 'alert-warning' : 'alert-info';
        
        const notification = $(`
            <div class="alert ${alertClass} alert-dismissible fade show position-fixed" 
                 style="top: 20px; right: 20px; z-index: 9999; max-width: 300px;">
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `);
        
        $('body').append(notification);
        
        // Otomatik kaldır
        setTimeout(() => notification.alert('close'), 5000);
    }
    
    calculateDueDate() {
        const now = new Date();
        now.setDate(now.getDate() + 14); // 14 gün sonra
        return now.toLocaleDateString('tr-TR');
    }
    
    speak(text) {
        if (this.speechSynthesis && this.speechSynthesis.speaking === false) {
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.lang = 'tr-TR';
            utterance.rate = 0.9;
            utterance.pitch = 1;
            this.speechSynthesis.speak(utterance);
        }
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
            gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.2);
            
            oscillator.start(audioContext.currentTime);
            oscillator.stop(audioContext.currentTime + 0.2);
        } catch (error) {
            console.log('Ses çalma hatası:', error);
        }
    }
    
    vibrate() {
        if ('vibrate' in navigator) {
            navigator.vibrate([200, 100, 200]);
        }
    }
}

// Global instance
let kioskSystem;

$(document).ready(function() {
    kioskSystem = new AdvancedKioskSystem();
    
    // Bugünün tarihini rezervasyon formuna set et
    const today = new Date();
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);
    
    $('#pickupDate').attr('min', tomorrow.toISOString().split('T')[0]);
    $('#pickupDate').val(tomorrow.toISOString().split('T')[0]);
});

console.log('✅ Gelişmiş Kiosk Sistemi yüklendi!');
