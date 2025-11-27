// Kütüphane Yönetimi - Kitap ve İşlem Fonksiyonları - OPTİMİZE EDİLMİŞ
// Donma problemleri çözüldü, hızlı çalışma için basitleştirildi

// SAYFA DEĞİŞKENLERİ
let currentBookPage = 1;
let currentMemberPage = 1;
let currentTransactionPage = 1;

// ==================== KİTAP YÖNETİMİ - OPTİMİZE EDİLMİŞ ====================

// Kitapları yükle - Hızlı versiyon
function loadBooks(page = 1) {
    const search = $('#bookSearch').val() || '';
    
    $.ajax({
        url: '/api/books',
        method: 'GET',
        data: { 
            page: page, 
            per_page: 20, 
            search: search,
            category_id: $('#categoryFilter').val() || ''
        },
        timeout: 3000,
        success: function(data) {
            displayBooks(data.books);
            updatePagination(data.total, page, 'booksPagination');
            currentBookPage = page;
        },
        error: function() {
            $('#booksTableBody').html('<tr><td colspan="10" class="text-center text-danger">Yükleme hatası</td></tr>');
        }
    });
}

// Kitapları göster - Basitleştirilmiş
function displayBooks(books) {
    const tbody = $('#booksTableBody');
    tbody.empty();
    
    if (!books || books.length === 0) {
        tbody.html('<tr><td colspan="10" class="text-center text-muted">Kitap bulunamadı</td></tr>');
        return;
    }
    
    books.forEach(book => {
        const available = book.available > 0 ? 
            `<span class="badge bg-success">${book.available}</span>` : 
            `<span class="badge bg-danger">0</span>`;
            
        const location = (book.shelf || book.cupboard) ? 
            `${book.shelf || ''} ${book.cupboard || ''}`.trim() : '-';
            
        // Kapak görseli - DÜZELT: Doğru yol eklendi
        const coverPath = book.image_path || '/static/img/no_cover.png';
        const coverImg = `<img src="${coverPath}" alt="Kapak" style="height:48px;max-width:40px;object-fit:cover;border-radius:4px;" onerror="this.style.display='none';this.nextElementSibling.style.display='inline'"><span class="text-muted" style="display:none">📖</span>`;
        
        // Yardımcı fonksiyon - nan değerlerini temizle
        const cleanValue = (value) => {
            if (!value || value === 'nan' || value === 'N/A' || value === 'null' || value === 'none') {
                return '-';
            }
            return value;
        };
        
        tbody.append(`
            <tr>
                <td><input type="checkbox" class="book-checkbox" value="${book.isbn}"></td>
                <td><code>${book.isbn}</code></td>
                <td>${coverImg}</td>
                <td><strong>${cleanValue(book.title)}</strong></td>
                <td>${cleanValue(book.authors)}</td>
                <td>${cleanValue(book.publishers)}</td>
                <td><span class="badge bg-secondary">${cleanValue(book.category)}</span></td>
                <td><span class="badge bg-info">${cleanValue(book.shelf)}</span></td>
                <td><span class="badge bg-warning">${cleanValue(book.cupboard)}</span></td>
                <td>${available}</td>
                <td>
                    <div class="btn-group btn-group-sm">
                        <button class="btn btn-outline-info" onclick="viewBook('${book.isbn}')" title="Görüntüle">
                            <i class="bi bi-eye"></i>
                        </button>
                        <button class="btn btn-outline-warning" onclick="editBook('${book.isbn}')" title="Düzenle">
                            <i class="bi bi-pencil"></i>
                        </button>
                        <button class="btn btn-outline-secondary" onclick="openCoverUpload('${book.isbn}')" title="Kapak Yükle">
                            <i class="bi bi-image"></i>
                        </button>
                        <button class="btn btn-outline-danger" onclick="confirmDeleteBook('${book.isbn}')" title="Sil">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `);
    });
}

// Kitap ekle modalını göster
function showAddBookModal() {
    $('#addBookForm')[0].reset();
    $('#addBookModal').modal('show');
}

// Kitap ekle
function addBook() {
    const form = $('#addBookForm');
    const data = {
        isbn: form.find('#addBookISBN').val().trim(),
        title: form.find('#addBookTitle').val().trim(),
        authors: form.find('#addBookAuthors').val().trim(),
        publish_date: form.find('#addBookPublishDate').val().trim(),
        number_of_pages: parseInt(form.find('#addBookPages').val()) || 0,
        publishers: form.find('#addBookPublishers').val().trim(),
        languages: form.find('#addBookLanguages').val().trim(),
        quantity: parseInt(form.find('#addBookQuantity').val()) || 1,
        shelf: form.find('#addBookShelf').val().trim(),
        cupboard: form.find('#addBookCupboard').val().trim()
    };
    
    // Minimum doğrulama: ISBN yeterli, diğerleri opsiyonel
    if (!data.isbn) {
        showToast('ISBN gerekli', 'warning');
        return;
    }
    
    // Kategoriler (çoklu seçim) - API'ye string olarak gönder
    const selectedOptions = document.getElementById('addBookCategories')?.selectedOptions || [];
    const selectedCats = Array.from(selectedOptions).map(o => o.text); // Text değerlerini al
    
    // Kategorileri virgülle ayrılmış string olarak ekle (API böyle bekliyor)
    if (selectedCats.length > 0) {
        data.category = selectedCats.join(', ');
    }

    // AJAX call
    $.ajax({
        url: '/api/books/add',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(data),
        success: function(resp) {
            // Başarılı yanıt - kitap eklendi veya adet güncellendi
            const message = resp.message || 'Kitap eklendi';
            
            // Eğer warning varsa (kitap zaten mevcut, adet güncellendi)
            if (resp.warning) {
                showToast(`⚠️ ${resp.warning}\n\n✓ ${message}`, 'warning');
            } else {
                showToast(`✅ ${message}`, 'success');
            }
            
            $('#addBookModal').modal('hide');
            form[0].reset(); // Form'u temizle
            if (typeof loadBooks === 'function') {
                loadBooks(currentBookPage || 1);
            }

            // Kapak seçilmişse yükle
            const coverFile = document.getElementById('addBookCover').files[0];
            if (coverFile && data.isbn) {
                uploadBookCover(data.isbn, coverFile);
            }
        },
        error: function(xhr) {
            // Hata durumları
            const status = xhr.status;
            const errorData = xhr.responseJSON || {};
            
            if (status === 400 && errorData.message && errorData.message.includes('UNIQUE constraint')) {
                // SQLite UNIQUE constraint hatası
                showToast(`❌ Bu ISBN numarasına sahip kitap zaten mevcut!\n\nÖneri: Kitap zaten kayıtlıysa, mevcut kaydı düzenleyerek adet sayısını artırabilirsiniz.`, 'error');
            } else if (status === 409) {
                // Conflict hatası (duplicate)
                showToast(`❌ ${errorData.error || 'Bu kitap zaten kayıtlı'}\n\n${errorData.message || ''}`, 'error');
            } else {
                // Diğer hatalar
                const errorMsg = errorData.message || errorData.error || 'Kitap eklenirken hata oluştu';
                showToast(`❌ ${errorMsg}`, 'error');
            }
            
            console.error('Book add error:', xhr);
        }
    });
}

// Kitap düzenle
function editBook(isbn) {
    $.ajax({
        url: `/api/books/${isbn}`,
        method: 'GET',
        timeout: 2000,
        success: function(book) {
            // Form alanlarını doldur
            $('#editBookISBN').val(book.isbn);
            $('#editBookISBNDisplay').val(book.isbn);
            $('#editBookTitle').val(book.title || '');
            $('#editBookAuthors').val(book.authors || '');
            $('#editBookPublishers').val(book.publishers || '');
            $('#editBookPublishDate').val(book.publish_date || '');
            $('#editBookPages').val(book.number_of_pages || 0);
            $('#editBookLanguages').val(book.languages || 'Türkçe');
            $('#editBookQuantity').val(book.quantity || 1);
            $('#editBookShelf').val(book.shelf || '');
            $('#editBookCupboard').val(book.cupboard || '');
            
            // Kategorileri seç
            if (book.categories && Array.isArray(book.categories)) {
                $('#editBookCategories option').each(function() {
                    const optionValue = parseInt($(this).val());
                    $(this).prop('selected', book.categories.includes(optionValue));
                });
            }
            
            $('#editBookModal').modal('show');
        },
        error: function() {
            showToast('Kitap bilgileri alınamadı', 'error');
        }
    });
}

// Kitap güncelle
function updateBook() {
    const isbn = $('#editBookISBN').val();
    const form = $('#editBookForm');
    const data = {
        title: form.find('#editBookTitle').val().trim(),
        authors: form.find('#editBookAuthors').val().trim(),
        publish_date: form.find('#editBookPublishDate').val().trim(),
        number_of_pages: parseInt(form.find('#editBookPages').val()) || 0,
        publishers: form.find('#editBookPublishers').val().trim(),
        languages: form.find('#editBookLanguages').val().trim(),
        quantity: parseInt(form.find('#editBookQuantity').val()) || 1,
        shelf: form.find('#editBookShelf').val().trim(),
        cupboard: form.find('#editBookCupboard').val().trim()
    };
    // Eski tekil kategori alanı hala varsa güvenli şekilde ata
    const legacyCat = form.find('#editBookCategory');
    if (legacyCat && legacyCat.length) {
        const v = legacyCat.val();
        if (typeof v === 'string') {
            data.category = v.trim();
        }
    }
    
    // Düzenlemede alanlar opsiyonel
    
    const selectedCats = Array.from(document.getElementById('editBookCategories')?.selectedOptions || []).map(o => parseInt(o.value));

    $.ajax({
        url: `/api/books/${isbn}`,
        method: 'PUT',
        contentType: 'application/json',
        data: JSON.stringify(data),
        success: function(resp) {
            showToast(resp.message || 'Kitap güncellendi', 'success');
            $('#editBookModal').modal('hide');
            if (typeof loadBooks === 'function') {
                loadBooks(currentBookPage || 1);
            }

            // Kapak dosyası varsa yükle
            const coverFile = document.getElementById('editBookCover').files[0];
            if (coverFile && isbn) {
                uploadBookCover(isbn, coverFile);
            }

            // Kategorileri kaydet
            if (selectedCats.length) {
                saveBookCategories(isbn, selectedCats);
            }
        },
        error: function(xhr) {
            const errorMsg = xhr.responseJSON?.message || 'Güncelleme hatası';
            showToast(errorMsg, 'error');
            console.error('Book update error:', xhr);
        }
    });
}

// Kapak yükleme modalı yerine direkt dosya alanını kullan
function openCoverUpload(isbn) {
    editBook(isbn);
    setTimeout(() => {
        document.getElementById('editBookCover')?.focus();
    }, 200);
}

function uploadBookCover(isbn, file) {
    const formData = new FormData();
    formData.append('cover', file);

    $.ajax({
        url: `/api/books/${isbn}/upload-cover`,
        method: 'POST',
        data: formData,
        processData: false,
        contentType: false,
        success: function(resp) {
            showToast(resp.message || 'Kapak yüklendi', 'success');
            if (typeof loadBooks === 'function') {
                loadBooks(currentBookPage || 1);
            }
        },
        error: function(xhr) {
            const msg = xhr.responseJSON?.message || 'Kapak yüklenemedi';
            showToast(msg, 'error');
        }
    });
}

function saveBookCategories(isbn, categoryIds) {
    $.ajax({
        url: `/api/books/${isbn}/categories`,
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ category_ids: categoryIds }),
        success: function() {
            showToast('Kategoriler güncellendi', 'success');
        },
        error: function(xhr) {
            showToast(xhr.responseJSON?.message || 'Kategoriler güncellenemedi', 'error');
        }
    });
}

// Düzenleme modalı kategori listesinde yukarı/aşağı taşıma ve toplu seçim
window.moveCategoryOption = function(selectId, direction) {
    const sel = document.getElementById(selectId);
    if (!sel) return;
    const idx = sel.selectedIndex;
    if (idx < 0) return;
    const newIdx = idx + direction;
    if (newIdx < 0 || newIdx >= sel.options.length) return;
    const option = sel.options[idx];
    const swap = sel.options[newIdx];
    sel.removeChild(option);
    sel.insertBefore(option, direction > 0 ? swap.nextSibling : swap);
    sel.selectedIndex = newIdx;
}

window.selectAllCategories = function(selectId) {
    const sel = document.getElementById(selectId);
    if (!sel) return;
    Array.from(sel.options).forEach(o => o.selected = true);
}

window.clearAllCategories = function(selectId) {
    const sel = document.getElementById(selectId);
    if (!sel) return;
    Array.from(sel.options).forEach(o => o.selected = false);
}

// Kitap silme onayı
function confirmDeleteBook(isbn) {
    if (confirm('Bu kitabı silmek istediğinizden emin misiniz?')) {
        deleteBook(isbn);
    }
}

// Kitap sil
function deleteBook(isbn) {
    $.ajax({
        url: `/api/books/${isbn}`,
        method: 'DELETE',
        success: function(resp) {
            showToast(resp.message || 'Kitap silindi', 'success');
            loadBooks(currentBookPage);
        },
        error: function(xhr) {
            showToast(xhr.responseJSON?.message || 'Silme hatası', 'error');
        }
    });
}

// Kitap görüntüle
function viewBook(isbn) {
    window.location.href = `/book/${isbn}`;
}

// Kitap arama - Hızlı
const searchBooks = debounce(function() {
    loadBooks(1);
}, 300);

// ==================== ÜYE YÖNETİMİ - OPTİMİZE EDİLMİŞ ====================

// Üyeleri yükle
function loadMembers(page = 1) {
    const search = $('#memberSearch').val() || '';
    
    $.ajax({
        url: '/api/members',
        method: 'GET',
        data: { 
            page: page, 
            per_page: 20, 
            search: search
        },
        timeout: 3000,
        success: function(data) {
            displayMembers(data.members);
            updatePagination(data.total, page, 'membersPagination');
            currentMemberPage = page;
        },
        error: function() {
            $('#membersTableBody').html('<tr><td colspan="7" class="text-center text-danger">Yükleme hatası</td></tr>');
        }
    });
}

// Üyeleri göster
function displayMembers(members) {
    const tbody = $('#membersTableBody');
    tbody.empty();
    
    if (!members || members.length === 0) {
        tbody.html('<tr><td colspan="7" class="text-center text-muted">Üye bulunamadı</td></tr>');
        return;
    }
    
    members.forEach(member => {
        const typeBadge = {
            'Öğrenci': 'bg-primary',
            'Öğretmen': 'bg-success', 
            'Personel': 'bg-info'
        }[member.uye_turu] || 'bg-secondary';
        
        tbody.append(`
            <tr>
                <td>${member.id}</td>
                <td><strong>${member.ad_soyad}</strong></td>
                <td>${member.sinif || '-'}</td>
                <td><code>${member.numara}</code></td>
                <td>${member.email || '-'}</td>
                <td>${member.phone || '-'}</td>
                <td><span class="badge ${typeBadge}">${member.uye_turu}</span></td>
                <td>
                    <div class="btn-group btn-group-sm">
                        <button class="btn btn-outline-warning" onclick="editMember(${member.id})" title="Düzenle">
                            <i class="bi bi-pencil"></i>
                        </button>
                        <button class="btn btn-outline-danger" onclick="confirmDeleteMember(${member.id})" title="Sil">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `);
    });
}

// Üye silme onayı
function confirmDeleteMember(id) {
    if (confirm('Bu üyeyi silmek istediğinizden emin misiniz?')) {
        deleteMember(id);
    }
}

// Üye sil
function deleteMember(id) {
    $.ajax({
        url: `/api/members/${id}`,
        method: 'DELETE',
        success: function(resp) {
            showToast(resp.message || 'Üye silindi', 'success');
            loadMembers(currentMemberPage);
        },
        error: function(xhr) {
            showToast(xhr.responseJSON?.message || 'Silme hatası', 'error');
        }
    });
}

// Üye düzenle
function editMember(id) {
    $.ajax({
        url: `/api/members/${id}`,
        method: 'GET',
        timeout: 2000,
        success: function(member) {
            // Form alanlarını doldur
            $('#editMemberId').val(member.id);
            $('#editMemberName').val(member.ad_soyad);
            $('#editMemberClass').val(member.sinif);
            $('#editMemberNumber').val(member.numara);
            $('#editMemberEmail').val(member.email);
            $('#editMemberPhone').val(member.phone || '');
            $('#editMemberType').val(member.uye_turu);
            
            $('#editMemberModal').modal('show');
        },
        error: function() {
            showToast('Üye bilgileri alınamadı', 'error');
        }
    });
}

// Üye güncelle
function updateMember() {
    const id = $('#editMemberId').val();
    const form = $('#editMemberForm');
    const data = {
        ad_soyad: form.find('#editMemberName').val().trim(),
        sinif: form.find('#editMemberClass').val(),
        numara: form.find('#editMemberNumber').val().trim(),
        email: form.find('#editMemberEmail').val().trim(),
        phone: form.find('#editMemberPhone').val().trim(),
        uye_turu: form.find('#editMemberType').val()
    };
    
    if (!data.ad_soyad || !data.numara) {
        showToast('Ad soyad ve numara gerekli', 'warning');
        return;
    }
    
    $.ajax({
        url: `/api/members/${id}`,
        method: 'PUT',
        contentType: 'application/json',
        data: JSON.stringify(data),
        success: function(resp) {
            showToast(resp.message || 'Üye güncellendi', 'success');
            $('#editMemberModal').modal('hide');
            if (typeof loadMembers === 'function') {
                loadMembers(currentMemberPage || 1);
            }
        },
        error: function(xhr) {
            showToast(xhr.responseJSON?.message || 'Güncelleme hatası', 'error');
        }
    });
}

// Üye arama
const searchMembers = debounce(function() {
    loadMembers(1);
}, 300);

// Üye ekle modalını göster
function showAddMemberModal() {
    $('#addMemberForm')[0].reset();
    $('#addMemberModal').modal('show');
}

// Üye ekle
function addMember() {
    const form = $('#addMemberForm');
    const data = {
        ad_soyad: form.find('#addMemberName').val().trim(),
        sinif: form.find('#addMemberClass').val(),
        numara: form.find('#addMemberNumber').val().trim(),
        email: form.find('#addMemberEmail').val().trim(),
        phone: form.find('#addMemberPhone').val().trim(),
        uye_turu: form.find('#addMemberType').val()
    };
    
    // Validation
    // Eksik bilgiler olsa da kayda izin verilir (en azından bir ad/numara önerilir)
    if (!data.ad_soyad && !data.numara) {
        showToast('En az Ad Soyad veya Numara girin', 'warning');
        // yine de devam etmek isteyenler olabilir, uyarı olarak bırakıyoruz
    }
    
    // AJAX call
    $.ajax({
        url: '/api/members',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(data),
        success: function(resp) {
            showToast(resp.message || 'Üye eklendi', 'success');
            $('#addMemberModal').modal('hide');
            form[0].reset(); // Form'u temizle
            if (typeof loadMembers === 'function') {
                loadMembers(1);
            }
        },
        error: function(xhr) {
            const errorMsg = xhr.responseJSON?.message || 'Ekleme hatası';
            showToast(errorMsg, 'error');
            console.error('Member add error:', xhr);
        }
    });
}

// ==================== İŞLEM YÖNETİMİ - OPTİMİZE EDİLMİŞ ====================

// İşlemleri yükle - GELİŞTİRİLDİ
function loadTransactions(page = 1, status = 'all', search = '') {
    $.ajax({
        url: '/api/transactions',
        method: 'GET',
        data: { 
            page: page, 
            per_page: 20, 
            status: status,
            search: search
        },
        timeout: 3000,
        success: function(data) {
            displayTransactions(data.transactions);
            updatePagination(data.total, page, 'transactionsPagination');
            currentTransactionPage = page;
        },
        error: function() {
            $('#transactionsTableBody').html('<tr><td colspan="8" class="text-center text-danger">Yükleme hatası</td></tr>');
        }
    });
}

// İşlemleri göster
function displayTransactions(transactions) {
    const tbody = $('#transactionsTableBody');
    tbody.empty();
    
    if (!transactions || transactions.length === 0) {
        tbody.html('<tr><td colspan="8" class="text-center text-muted">İşlem bulunamadı</td></tr>');
        return;
    }
    
    transactions.forEach(trans => {
        let statusBadge, actionButton = '';
        if (trans.return_date) {
            statusBadge = '<span class="badge bg-success">İade Edildi</span>';
        } else if (trans.is_overdue) {
            statusBadge = '<span class="badge bg-danger">Gecikmiş</span>';
            actionButton = `<button class="btn btn-sm btn-primary" onclick="quickReturn(${trans.id})">Hızlı İade</button>`;
        } else {
            statusBadge = '<span class="badge bg-warning text-dark">Ödünçte</span>';
            actionButton = `<button class="btn btn-sm btn-primary" onclick="quickReturn(${trans.id})">Hızlı İade</button>`;
        }
        // Süre uzat butonu (iade edilmemiş ve yenileme hakkı varsa)
        if (!trans.return_date && trans.can_renew) {
            actionButton += ` <button class="btn btn-sm btn-warning" onclick="renewTransaction(${trans.id})">Süre Uzat</button>`;
        } else if (!trans.return_date && !trans.can_renew) {
            actionButton += ` <button class="btn btn-sm btn-outline-secondary" disabled>Yenileme Yok</button>`;
        }
        const rowClass = trans.is_overdue ? 'table-danger' : '';
        // Kalan gün/gün gecikme hesaplama
        let kalanGunHtml = '';
        if (trans.due_date && !trans.return_date) {
            const today = new Date();
            const due = new Date(trans.due_date);
            const diffTime = due.setHours(0,0,0,0) - today.setHours(0,0,0,0);
            const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
            if (diffDays > 0) {
                kalanGunHtml = `<span class='badge bg-info ms-1'>${diffDays} gün kaldı</span>`;
            } else if (diffDays === 0) {
                kalanGunHtml = `<span class='badge bg-warning text-dark ms-1'>Bugün teslim</span>`;
            } else {
                kalanGunHtml = `<span class='badge bg-danger ms-1'>${-diffDays} gün gecikti</span>`;
            }
        }
        tbody.append(`
            <tr class="${rowClass}">
                <td>${trans.id}</td>
                <td>
                    <strong>${trans.book_title}</strong><br>
                    <small class="text-muted"><code>${trans.isbn}</code></small>
                </td>
                <td>${trans.member_name}</td>
                <td>${formatDate(trans.borrow_date)}</td>
                <td class="${trans.is_overdue ? 'text-danger fw-bold' : ''}">${formatDate(trans.due_date)} ${kalanGunHtml}</td>
                <td>${trans.return_date ? formatDate(trans.return_date) : '-'}</td>
                <td>${statusBadge}</td>
                <td>${actionButton}</td>
            </tr>
        `);
    });
}

// Hızlı iade
function quickReturn(transactionId) {
    if (confirm('Bu kitabı iade almak istediğinizden emin misiniz?')) {
        $.ajax({
            url: `/api/transactions/${transactionId}/quick-return`,
            method: 'POST',
            success: function() {
                showToast('Kitap iade alındı', 'success');
                loadTransactions(currentTransactionPage);
            },
            error: function(xhr) {
                showToast(xhr.responseJSON?.message || 'İade hatası', 'error');
            }
        });
    }
}

// İşlem filtreleme
function filterTransactions(filter) {
    // Radio button'ları güncelle
    $(`input[value="${filter}"]`).prop('checked', true);
    const search = $('#transactionSearch').val() || '';
    loadTransactions(1, filter, search);
}

// İşlem arama - YENİ EKLENEN
const searchTransactions = debounce(function() {
    const search = $('#transactionSearch').val() || '';
    const status = $('input[name="statusFilter"]:checked').val() || 'all';
    loadTransactions(1, status, search);
}, 300);

// ==================== ÖDÜNÇ VER/İADE AL - BASİTLEŞTİRİLMİŞ ====================

// Ödünç ver
function borrowBook() {
    const isbn = $('#borrowISBN').val().trim();
    const schoolNo = $('#borrowMemberNo').val().trim();
    const dueDate = $('#borrowDueDate').val();
    
    if (!isbn || !schoolNo || !dueDate) {
        showToast('Tüm alanları doldurun', 'warning');
        return;
    }
    
    $.ajax({
        url: '/api/transactions/borrow',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            isbn: isbn,
            school_no: schoolNo,
            due_date: dueDate
        }),
        success: function() {
            showToast('Kitap ödünç verildi', 'success');
            $('#borrowForm')[0].reset();
            $('#borrowModal').modal('hide');
            loadTransactions(currentTransactionPage);
        },
        error: function(xhr) {
            showToast(xhr.responseJSON?.message || 'Ödünç verme hatası', 'error');
        }
    });
}

// İade al
function returnBook() {
    const isbn = $('#returnISBN').val().trim();
    const schoolNo = $('#returnMemberNo').val().trim();
    
    if (!isbn || !schoolNo) {
        showToast('ISBN ve üye numarası gerekli', 'warning');
        return;
    }
    
    $.ajax({
        url: '/api/transactions/return',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            isbn: isbn,
            school_no: schoolNo
        }),
        success: function() {
            showToast('Kitap iade alındı', 'success');
            $('#returnForm')[0].reset();
            $('#returnModal').modal('hide');
            loadTransactions(currentTransactionPage);
        },
        error: function(xhr) {
            showToast(xhr.responseJSON?.message || 'İade alma hatası', 'error');
        }
    });
}

// ==================== BİLDİRİM YÖNETİMİ ====================

// Bildirimleri yükle
function loadNotifications() {
    $.ajax({
        url: '/api/notifications',
        method: 'GET',
        timeout: 2000,
        success: function(data) {
            displayNotifications(data.notifications);
        },
        error: function() {
            $('#notificationsContainer').html('<div class="alert alert-danger">Bildirimler yüklenemedi</div>');
        }
    });
}

// Bildirimleri göster
function displayNotifications(notifications) {
    const container = $('#notificationsContainer');
    container.empty();
    
    if (!notifications || notifications.length === 0) {
        container.html('<div class="alert alert-info">Henüz bildirim yok</div>');
        return;
    }
    
    notifications.forEach(notif => {
        const typeClass = {
            'return_reminder': 'alert-warning',
            'overdue': 'alert-danger',
            'success': 'alert-success',
            'info': 'alert-info'
        }[notif.type] || 'alert-secondary';
        
        const readClass = notif.is_read ? 'opacity-75' : '';
        
        container.append(`
            <div class="alert ${typeClass} ${readClass}" data-id="${notif.id}">
                <div class="d-flex justify-content-between align-items-start">
                    <div>
                        <strong>${notif.message}</strong><br>
                        <small class="text-muted">${formatDate(notif.created_date)}</small>
                    </div>
                    <button class="btn btn-sm btn-outline-secondary" onclick="markNotificationRead(${notif.id})">
                        ${notif.is_read ? '✓' : 'Okundu işaretle'}
                    </button>
                </div>
            </div>
        `);
    });
}

// Bildirimi okundu işaretle
function markNotificationRead(id) {
    $.ajax({
        url: `/api/notifications/${id}/read`,
        method: 'POST',
        success: function() {
            $(`[data-id="${id}"]`).addClass('opacity-75').find('button').text('✓');
            checkNotifications(); // Badge'i güncelle
        }
    });
}

// ==================== YARDIMCI FONKSİYONLAR ====================

// Pagination güncelle - Basit versiyon
function updatePagination(total, current, containerId) {
    const totalPages = Math.ceil(total / 20);
    const container = $(`#${containerId}`);
    
    if (totalPages <= 1) {
        container.empty();
        return;
    }
    
    let html = '<nav><ul class="pagination pagination-sm justify-content-center">';
    
    // Önceki
    if (current > 1) {
        html += `<li class="page-item"><a class="page-link" href="#" onclick="loadCurrentPageData(${current - 1})">«</a></li>`;
    }
    
    // Sayfa numaraları (sadece yakın olanlar)
    const start = Math.max(1, current - 2);
    const end = Math.min(totalPages, current + 2);
    
    for (let i = start; i <= end; i++) {
        const active = i === current ? 'active' : '';
        html += `<li class="page-item ${active}"><a class="page-link" href="#" onclick="loadCurrentPageData(${i})">${i}</a></li>`;
    }
    
    // Sonraki
    if (current < totalPages) {
        html += `<li class="page-item"><a class="page-link" href="#" onclick="loadCurrentPageData(${current + 1})">»</a></li>`;
    }
    
    html += '</ul></nav>';
    container.html(html);
}

// ==================== EVENT LİSTENER'LAR ====================

$(document).ready(function() {
    console.log('📚 Kitap ve İşlem fonksiyonları yüklendi');
    
    // Arama event'leri
    $('#bookSearch').on('input', searchBooks);
    $('#memberSearch').on('input', searchMembers);
    $('#transactionSearch').on('input', searchTransactions);
    
    // ISBN alanında Enter tuşuna basınca bilgi getir
    $('#addBookISBN').on('keypress', function(e) {
        if (e.which === 13) { // Enter tuşu
            e.preventDefault();
            fetchBookFromISBN();
        }
    });
    
    // Form submit event'leri - ESC ile çıkış destekli
    $('#addBookForm').on('submit', function(e) {
        e.preventDefault();
        addBook();
    });
    
    $('#editBookForm').on('submit', function(e) {
        e.preventDefault();
        updateBook();
    });
    
    $('#borrowForm').on('submit', function(e) {
        e.preventDefault();
        borrowBook();
    });
    
    $('#returnForm').on('submit', function(e) {
        e.preventDefault();
        returnBook();
    });
    
    // Modal ESC ile kapanma desteği
    $('.modal').on('hidden.bs.modal', function() {
        $(this).find('form')[0]?.reset();
    });

    $('#addMemberForm').on('submit', function(e) {
        e.preventDefault();
        addMember();
    });
    
    $('#editMemberForm').on('submit', function(e) {
        e.preventDefault();
        updateMember();
    });
});

console.log('📖 Kitap ve İşlem Yönetimi Hazır - Optimize Edilmiş');

function renewTransaction(id) {
    if (confirm('Bu işlemin süresini uzatmak istiyor musunuz?')) {
        $.ajax({
            url: `/api/transactions/${id}/renew`,
            method: 'POST',
            success: function(resp) {
                showToast(resp.message || 'Süre uzatıldı', 'success');
                loadTransactions(currentTransactionPage);
            },
            error: function(xhr) {
                showToast(xhr.responseJSON?.message || 'Süre uzatılamadı', 'error');
            }
        });
    }
}

// ==================== EKSİK FONKSİYONLAR - YENİ EKLENEN ====================

// Eksik kapak resimlerini tamamla
window.downloadMissingCovers = function() {
    if (!confirm('Kapak resmi eksik kitaplar için otomatik resim indirme işlemi başlatılsın mı?\n(En fazla 20 kitap işlenir)')) {
        return;
    }

    showToast('Kapak resimleri indiriliyor...', 'info');

    $.ajax({
        url: '/api/books/download-missing-covers',
        method: 'POST',
        timeout: 120000, // 2 dakika timeout
        success: function(response) {
            if (response.success) {
                showToast(response.message, 'success');
                
                // Kitap listesini yenile
                if (typeof loadBooks === 'function') {
                    setTimeout(() => loadBooks(1), 1000);
                }
                
                // Detayları göster
                if (response.processed > 0) {
                    console.log('Cover download stats:', response);
                }
            } else {
                showToast(response.message, 'error');
            }
        },
        error: function(xhr) {
            const message = xhr.responseJSON?.message || 'Kapak resmi indirme hatası';
            showToast(message, 'error');
        }
    });
};

// ISBN hızlı ekleme fonksiyonları - GLOBAL OLARAK TANIMLA
window.showFetchBooksModal = function() {
    $('#fetchISBNs').val('');
    $('#fetchedBooksTable').hide();
    $('#fetchFileUploadArea').hide();
    $('#fetchFileInput').val('');
    $('#fetchProgress').hide();
    $('#fetchStatus').html('<p class="text-muted small">ISBN\'leri girin ve işleme başlayın</p>');
    $('#fetchBooksModal').modal('show');
};

window.fetchBooks = function() {
    const isbns = $('#fetchISBNs').val().split('\n').map(isbn => isbn.trim()).filter(isbn => isbn);
    
    if (isbns.length === 0) {
        showToast('Lütfen en az bir ISBN girin', 'warning');
        return;
    }
    
    $.ajax({
        url: '/api/books/fetch',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ isbns: isbns }),
        success: function(response) {
            displayFetchedBooks(response.books);
            $('#fetchedBooksTable').show();
        },
        error: function() {
            showToast('Kitap bilgileri alınırken hata oluştu', 'error');
        }
    });
};

window.fetchAndSaveAll = function() {
    const isbns = $('#fetchISBNs').val().split('\n').map(isbn => isbn.trim()).filter(isbn => isbn);
    
    if (isbns.length === 0) {
        showToast('Lütfen en az bir ISBN girin', 'warning');
        return;
    }

    // Büyük dosyalar için uyarı
    let warningMessage = '';
    if (isbns.length > 1000) {
        warningMessage = `⚠️ ${isbns.length} adet ISBN bulundu! Bu çok büyük bir işlem.\n\nTahmini süre: ${Math.ceil(isbns.length/10)} dakika\nBu işlem sırasında tarayıcıyı kapatmayın.\n\nDevam etmek istiyor musunuz?`;
    } else if (isbns.length > 100) {
        warningMessage = `📚 ${isbns.length} adet ISBN bulundu.\n\nTahmini süre: ${Math.ceil(isbns.length/20)} dakika\nBu işlem biraz zaman alacak.\n\nDevam etmek istiyor musunuz?`;
    } else if (isbns.length > 20) {
        warningMessage = `${isbns.length} adet ISBN bulundu. Bu işlem birkaç dakika sürebilir. Devam etmek istiyor musunuz?`;
    }
    
    if (warningMessage && !confirm(warningMessage)) {
        return;
    }

    // UI güncellemeleri
    const btn = $('#fetchAndSaveBtn');
    const originalText = btn.html();
    btn.prop('disabled', true).html('<i class="spinner-border spinner-border-sm"></i> İşleniyor...');

    $('#fetchProgress').show();
    $('#fetchStatus').html('<p class="text-primary">ISBN\'ler işleniyor...</p>');

    let completed = 0;
    const total = isbns.length;
    const results = [];

    // Dinamik batch boyutu (büyük dosyalar için daha büyük batch)
    let batchSize = 5;
    if (isbns.length > 500) {
        batchSize = 10; // 500+ için daha hızlı
    } else if (isbns.length > 100) {
        batchSize = 8;  // 100+ için orta hız
    }
    
    let currentBatch = 0;

    function processBatch() {
        const start = currentBatch * batchSize;
        const end = Math.min(start + batchSize, isbns.length);
        const currentISBNs = isbns.slice(start, end);

        if (currentISBNs.length === 0) {
            // İşlem tamamlandı - otomatik kaydet
            if (results.length > 0) {
                const successBooks = results.filter(r => !r.error);
                if (successBooks.length > 0) {
                    saveDirectlyToDatabase(successBooks, btn, originalText);
                } else {
                    showToast('Hiç kitap bilgisi bulunamadı', 'warning');
                    btn.prop('disabled', false).html(originalText);
                    $('#fetchProgress').hide();
                }
            } else {
                showToast('ISBN işleme hatası', 'error');
                btn.prop('disabled', false).html(originalText);
                $('#fetchProgress').hide();
            }
            return;
        }

        $.ajax({
            url: '/api/books/fetch-bulk',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({isbns: currentISBNs}),
            success: function(response) {
                if (response.books) {
                    results.push(...response.books);
                }
            },
            error: function(xhr) {
                console.error('Batch fetch error:', xhr);
            },
            complete: function() {
                completed += currentISBNs.length;
                const progressPercent = (completed / total) * 100;
                $('#fetchProgress .progress-bar').css('width', progressPercent + '%');
                $('#fetchStatus').html(`<p class="text-info">${completed}/${total} ISBN işlendi</p>`);

                currentBatch++;
                // Dinamik bekleme süresi
                const delay = isbns.length > 500 ? 500 : 1000; // Büyük dosyalar için daha hızlı
                setTimeout(processBatch, delay);
            }
        });
    }

    processBatch();
};

// Doğrudan veritabanına kaydet
function saveDirectlyToDatabase(books, btn, originalText) {
    $('#fetchStatus').html('<p class="text-success">Veritabanına kaydediliyor...</p>');

    $.ajax({
        url: '/api/books/import-bulk',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({books: books}),
        success: function(response) {
            if (response.success) {
                showToast(response.message, 'success');
                
                // Kitap listesini yenile
                if (typeof loadBooks === 'function') {
                    setTimeout(() => loadBooks(1), 1000);
                }
            } else {
                showToast(response.message, 'error');
            }
        },
        error: function(xhr) {
            const message = xhr.responseJSON?.message || 'Kaydetme hatası';
            showToast(message, 'error');
        },
        complete: function() {
            btn.prop('disabled', false).html(originalText);
            $('#fetchProgress').hide();
            $('#fetchStatus').html('<p class="text-muted small">İşlem tamamlandı</p>');
        }
    });
}

// Display fetched books
function displayFetchedBooks(books) {
    const tbody = $('#fetchedBooksBody');
    tbody.empty();
    window.fetchedBooks = books; // Global'e kaydet
    
    books.forEach((book, index) => {
        const actionButton = book.error ? 
            '<span class="text-danger">Bilgi bulunamadı</span>' :
            `<button class="btn btn-sm btn-success" onclick="saveFetchedBook(${index})">Kaydet</button>`;
            
        tbody.append(`
            <tr>
                <td><code>${book.isbn}</code></td>
                <td>${book.title}</td>
                <td>${book.authors}</td>
                <td>${actionButton}</td>
            </tr>
        `);
    });
}

// Save fetched book
function saveFetchedBook(index) {
    const book = window.fetchedBooks[index];
    
    $.ajax({
        url: '/api/books/add',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(book),
        success: function() {
            showToast(`"${book.title}" kaydedildi`, 'success');
            window.fetchedBooks.splice(index, 1);
            displayFetchedBooks(window.fetchedBooks);
            if (typeof loadBooks === 'function') {
                loadBooks(currentBookPage);
            }
        },
        error: function(xhr) {
            showToast(xhr.responseJSON?.message || 'Kaydetme hatası', 'error');
        }
    });
}

// Save all fetched books
function saveAllFetchedBooks() {
    const validBooks = window.fetchedBooks.filter(book => !book.error);
    
    if (validBooks.length === 0) {
        showToast('Kaydedilecek geçerli kitap yok', 'warning');
        return;
    }
    
    if (confirm(`${validBooks.length} kitabı kaydetmek istediğinizden emin misiniz?`)) {
        let saved = 0;
        let errors = 0;
        
        validBooks.forEach((book, index) => {
            $.ajax({
                url: '/api/books/add',
                method: 'POST',
                contentType: 'application/json',
                data: JSON.stringify(book),
                success: function() {
                    saved++;
                    if (saved + errors === validBooks.length) {
                        showToast(`${saved} kitap kaydedildi`, 'success');
                        $('#fetchBooksModal').modal('hide');
                        if (typeof loadBooks === 'function') {
                            loadBooks(1);
                        }
                    }
                },
                error: function() {
                    errors++;
                    if (saved + errors === validBooks.length) {
                        showToast(`${saved} kitap kaydedildi, ${errors} hata`, 'warning');
                    }
                }
            });
        });
    }
}

// Dosya yükleme seçeneklerini göster
window.showFetchFileOptions = function() {
    $('#fetchFileUploadArea').slideToggle();
};

// Yeni kitap eklerken ISBN'den bilgi getir
window.fetchBookFromISBN = function() {
    const isbn = $('#addBookISBN').val().trim();
    
    if (!isbn) {
        showToast('Lütfen önce ISBN numarası girin', 'warning');
        return;
    }
    
    // Buton durumunu güncelle
    const btn = event.target;
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="spinner-border spinner-border-sm"></i> Getiriliyor...';
    
    $.ajax({
        url: '/api/books/fetch-from-isbn',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ isbn: isbn }),
        timeout: 15000,
        success: function(response) {
            if (response.success && response.book) {
                const book = response.book;
                
                // Form alanlarını doldur
                $('#addBookTitle').val(book.title || '');
                $('#addBookAuthors').val(book.authors || '');
                $('#addBookPublishers').val(book.publishers || '');
                $('#addBookPublishDate').val(book.publish_date || '');
                $('#addBookPages').val(book.number_of_pages || '');
                $('#addBookLanguages').val(book.languages || 'Türkçe');
                
                // Kategori seçimi (varsa)
                if (book.categories && Array.isArray(book.categories)) {
                    $('#addBookCategories option').each(function() {
                        const categoryName = $(this).text().toLowerCase();
                        const shouldSelect = book.categories.some(cat =>
                            categoryName.includes(cat.toLowerCase())
                        );
                        $(this).prop('selected', shouldSelect);
                    });
                }
                
                showToast('Kitap bilgileri başarıyla getirildi!', 'success');
                
                // Başlık alanına focus
                $('#addBookTitle').focus();
            } else {
                showToast(response.message || 'Kitap bilgileri bulunamadı', 'warning');
            }
        },
        error: function(xhr) {
            let errorMsg = 'Kitap bilgileri alınamadı';
            if (xhr.responseJSON && xhr.responseJSON.message) {
                errorMsg = xhr.responseJSON.message;
            }
            showToast(errorMsg, 'error');
        },
        complete: function() {
            // Butonu eski haline döndür
            btn.disabled = false;
            btn.innerHTML = originalText;
        }
    });
};

// ISBN bilgi tamamlama fonksiyonu - DÜZELTİLDİ
window.completeBookInfo = function(isbn) {
    if (!isbn) {
        alert('ISBN bilgisi eksik!');
        return;
    }
    
    if (!confirm('Bu kitabın eksik bilgilerini ISBN\'den otomatik olarak tamamlamak istiyor musunuz?')) {
        return;
    }
    
    // showToast yoksa basit alert kullan
    const showMessage = (message, type) => {
        if (typeof showToast === 'function') {
            showToast(message, type);
        } else {
            alert(message);
        }
    };
    
    showMessage('Kitap bilgileri tamamlanıyor...', 'info');
    
    $.ajax({
        url: '/api/books/complete-info',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ isbn: isbn }),
        timeout: 30000,
        success: function(response) {
            if (response && response.success) {
                showMessage(response.message || 'Bilgiler başarıyla tamamlandı!', 'success');
                
                // Sayfayı yenile
                setTimeout(() => {
                    window.location.reload();
                }, 2000);
            } else {
                showMessage(response.message || 'Bilgi tamamlanamadı', 'warning');
            }
        },
        error: function(xhr, status, error) {
            let errorMessage = 'Bilgi tamamlama hatası!';
            
            try {
                if (xhr.responseJSON && xhr.responseJSON.message) {
                    errorMessage = xhr.responseJSON.message;
                } else if (xhr.responseText) {
                    errorMessage = `Hata: ${xhr.responseText}`;
                }
            } catch (e) {
                errorMessage = `Bağlantı hatası: ${error}`;
            }
            
            showMessage(errorMessage, 'error');
        }
    });

// TÜM KİTAPLARIN BİLGİLERİNİ KONTROL ET VE GÜNCELLE - YENİ FONKSİYON
window.completeAllBooksInfo = function() {
    const confirmMsg = `📚 TÜM KİTAPLARIN BİLGİLERİNİ DOĞRULA VE GÜNCELLE

Bu işlem:
• Veritabanındaki TÜM kitapların bilgilerini ISBN üzerinden API'den kontrol edecek
• DOLU OLSA BİLE tüm bilgileri yeniden doğrulayacak  
• Yanlış veya eksik bilgileri düzeltecek
• Kitap başlıkları, yazarları, yayınevlerini güncelleyecek
• Kapak resimlerini indirecek
• 20'şer kitap halinde işlem yapacak
• Uzun sürebilir (100+ kitap için birkaç dakika)

⚠️ DİKKAT: Mevcut tüm kitap bilgileri API'den gelen bilgilerle değiştirilecek!

Devam etmek istiyor musunuz?`;

    if (!confirm(confirmMsg)) {
        return;
    }

    // Modal oluştur veya mevcut progress gösterimi
    const progressHtml = `
        <div id="completeAllProgress" style="position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); 
             background: white; padding: 30px; border-radius: 10px; box-shadow: 0 5px 15px rgba(0,0,0,0.3); 
             z-index: 9999; min-width: 500px;">
            <h4>📚 Kitap Bilgileri Doğrulanıyor ve Güncelleniyor</h4>
            <div class="progress mb-3" style="height: 25px;">
                <div class="progress-bar progress-bar-striped progress-bar-animated bg-primary" 
                     role="progressbar" style="width: 0%">0%</div>
            </div>
            <div id="completeStatus">
                <p class="mb-1">Hazırlanıyor...</p>
                <small class="text-muted">İşlenen: <span id="processedCount">0</span> / <span id="totalCount">?</span></small>
            </div>
            <div id="currentBatch" class="alert alert-info mt-2" style="display: none;">
                <small><strong>Şu an işleniyor:</strong> <span id="currentISBNs"></span></small>
            </div>
            <div id="completeResults" class="mt-3" style="max-height: 200px; overflow-y: auto; display: none;">
                <h6>İşlem Detayları:</h6>
                <ul id="resultsList" class="small"></ul>
            </div>
            <div class="mt-3">
                <button class="btn btn-danger btn-sm" onclick="cancelCompleteAll()">İptal</button>
                <button class="btn btn-secondary btn-sm" onclick="$('#completeResults').toggle()">Detayları Göster/Gizle</button>
            </div>
        </div>
        <div id="completeAllOverlay" style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 9998;"></div>
    `;

    // Progress gösterimi ekle
    $('body').append(progressHtml);

    let cancelled = false;
    window.cancelCompleteAll = function() {
        cancelled = true;
        $('#completeAllProgress, #completeAllOverlay').remove();
        showToast('İşlem iptal edildi', 'warning');
    };

    // Önce tüm kitapların listesini al
    $.ajax({
        url: '/api/books/get-all-isbns',
        method: 'GET',
        success: function(response) {
            const allIsbns = response.isbns || [];
            const totalBooks = allIsbns.length;
            
            $('#totalCount').text(totalBooks);
            
            if (totalBooks === 0) {
                $('#completeAllProgress, #completeAllOverlay').remove();
                showToast('Hiç kitap bulunamadı', 'warning');
                return;
            }

            let processed = 0;
            let updated = 0;
            let verified = 0;
            let failed = 0;
            const batchSize = 20;
            const results = [];

            function processBatch(startIndex) {
                if (cancelled || startIndex >= totalBooks) {
                    // İşlem tamamlandı
                    $('#completeStatus').html(`
                        <p class="text-success"><strong>✅ İşlem Tamamlandı!</strong></p>
                        <p>Toplam: ${processed} kitap işlendi</p>
                        <p>Güncellenen: ${updated} | Doğrulanan: ${verified} | Başarısız: ${failed}</p>
                    `);
                    
                    $('#currentBatch').hide();
                    $('#completeResults').show();
                    
                    // Sonuçları detaylı göster
                    const summary = `
                        <li class="text-primary"><strong>Özet:</strong></li>
                        <li>✅ ${updated} kitap güncellendi</li>
                        <li>✔️ ${verified} kitap doğrulandı (değişiklik gerekmedi)</li>
                        <li>❌ ${failed} kitap için bilgi alınamadı</li>
                    `;
                    $('#resultsList').prepend(summary);
                    
                    setTimeout(() => {
                        $('#completeAllProgress, #completeAllOverlay').remove();
                        if (updated > 0) {
                            showToast(`${updated} kitap güncellendi, ${verified} kitap doğrulandı!`, 'success');
                            // Kitap listesini yenile
                            if (typeof loadBooks === 'function') {
                                loadBooks(1);
                            }
                        } else if (verified > 0) {
                            showToast(`Tüm kitaplar doğrulandı, güncelleme gerekmedi!`, 'info');
                        }
                    }, 5000);
                    return;
                }

                const endIndex = Math.min(startIndex + batchSize, totalBooks);
                const batchIsbns = allIsbns.slice(startIndex, endIndex);
                
                $('#completeStatus p').first().html(`<strong>${startIndex + 1}-${endIndex}</strong> arası kitaplar API'den kontrol ediliyor...`);
                $('#currentBatch').show();
                $('#currentISBNs').text(batchIsbns.slice(0, 3).join(', ') + (batchIsbns.length > 3 ? '...' : ''));

                // Batch halinde API'ye gönder - TÜM BİLGİLERİ KONTROL ET
                $.ajax({
                    url: '/api/books/verify-and-update-batch',
                    method: 'POST',
                    contentType: 'application/json',
                    data: JSON.stringify({ 
                        isbns: batchIsbns,
                        force_update: true,  // Dolu olsa bile güncelle
                        verify_all_fields: true,  // Tüm alanları kontrol et
                        include_covers: true,
                        include_titles: true
                    }),
                    timeout: 90000, // 1.5 dakika timeout
                    success: function(batchResponse) {
                        if (batchResponse.results) {
                            batchResponse.results.forEach(result => {
                                processed++;
                                if (result.updated) {
                                    updated++;
                                    results.push(`✅ ${result.isbn}: Güncellendi - ${result.changes || result.title || ''}`);
                                } else if (result.verified) {
                                    verified++;
                                    results.push(`✔️ ${result.isbn}: Doğrulandı - ${result.title || 'Değişiklik yok'}`);
                                } else if (result.error) {
                                    failed++;
                                    results.push(`❌ ${result.isbn}: ${result.error}`);
                                }
                            });
                        } else {
                            // Eğer batch response yoksa tüm batch'i başarısız say
                            processed += batchIsbns.length;
                            failed += batchIsbns.length;
                        }
                    },
                    error: function(xhr) {
                        // Hata durumunda bu batch'i atla
                        processed += batchIsbns.length;
                        failed += batchIsbns.length;
                        
                        const errorMsg = xhr.responseJSON?.message || 'API bağlantı hatası';
                        results.push(`⚠️ Batch ${startIndex + 1}-${endIndex}: ${errorMsg}`);
                        console.error('Batch error:', xhr);
                    },
                    complete: function() {
                        // Progress güncelle
                        const progressPercent = Math.round((processed / totalBooks) * 100);
                        $('#completeAllProgress .progress-bar')
                            .css('width', progressPercent + '%')
                            .text(progressPercent + '%');
                        $('#processedCount').text(processed);

                        // Son 10 sonucu göster
                        const lastResults = results.slice(-10);
                        $('#resultsList').html(lastResults.map(r => `<li>${r}</li>`).join(''));

                        // Sonraki batch'e geç (API limitleri için biraz bekleyerek)
                        if (!cancelled) {
                            setTimeout(() => processBatch(endIndex), 1500);
                        }
                    }
                });
            }

            // İlk batch'i başlat
            processBatch(0);
        },
        error: function(xhr) {
            $('#completeAllProgress, #completeAllOverlay').remove();
            showToast('Kitap listesi alınamadı. API bağlantısını kontrol edin!', 'error');
            console.error('Get ISBNs error:', xhr);
        }
    });
};
};
