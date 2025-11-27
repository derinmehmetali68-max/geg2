from flask import request, jsonify
from flask_login import current_user
from flask_mail import Message
from datetime import datetime, timedelta
import requests
import qrcode
import io
import base64
import os
import tempfile
import shutil
import subprocess
import sys
import secrets
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm

# Disable SSL warnings for PyInstaller executable
if hasattr(sys, 'frozen'):
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from config import app, mail, get_setting
from models import db, User, Book, Member, Transaction, Category, BookCategory, Notification, SearchHistory, Review, Reservation, Fine, ActivityLog, Settings, EmailTemplate, OnlineBorrowRequest, QRCode

def log_activity(action, details=None, user_id=None):
    """Log user activity"""
    try:
        # Eğer user_id parametresi verilmemişse, current_user'dan al
        if user_id is None:
            user_id = current_user.id if current_user.is_authenticated else None
        
        log = ActivityLog(
            user_id=user_id,
            action=action,
            details=details,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        db.session.add(log)
        db.session.commit()
    except:
        pass

def generate_qr_code(data):
    """Generate QR code and return base64 string"""
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffer = io.BytesIO()
    img.save(buffer, 'PNG')
    buffer.seek(0)
    
    return base64.b64encode(buffer.getvalue()).decode()

def save_qr_code(isbn):
    """Save QR code for a book"""
    data = f"BOOK:{isbn}"
    qr_image = generate_qr_code(data)
    
    # Save to file
    qr_path = f"static/qrcodes/{isbn}.png"
    with open(qr_path, "wb") as f:
        f.write(base64.b64decode(qr_image))
    
    return qr_path

# Image helpers
def normalize_cover_url(image_path):
    """Kapak görüntü yolu/URL'sini istemci için normalize eder.

    Kurallar:
    - Boşsa no_cover döner
    - http/https ile başlıyorsa olduğu gibi döner
    - /static/ ile başlıyorsa olduğu gibi döner
    - Aksi halde filename olarak kabul edip /static/book_covers/ ile birleştirir
    """
    if not image_path:
        return '/static/img/no_cover.png'

    path = str(image_path).strip()
    if path.startswith('http://') or path.startswith('https://'):
        return path
    if path.startswith('/static/'):
        return path
    return f"/static/book_covers/{path}"

def download_cover_image(image_url, isbn):
    """Verilen image_url'i indirip static/book_covers/{isbn}.jpg olarak kaydeder.
    Başarılı olursa filename (örn. 978...jpg) döner, aksi halde None.
    """
    try:
        if not image_url or not isbn:
            return None
        filename = f"{isbn}.jpg"
        save_dir = os.path.join(app.root_path, 'static', 'book_covers')
        os.makedirs(save_dir, exist_ok=True)
        save_path = os.path.join(save_dir, filename)

        # SSL certificate verification disabled for PyInstaller executable compatibility
        import sys
        if hasattr(sys, 'frozen'):
            # Running as PyInstaller executable
            resp = requests.get(image_url, verify=False, timeout=10)
        else:
            # Running normally
            resp = requests.get(image_url, timeout=10)
        if resp.status_code == 200 and resp.content:
            with open(save_path, 'wb') as f:
                f.write(resp.content)
            return filename
    except Exception as e:
        try:
            print(f"download_cover_image error for {isbn}: {e}")
        except Exception:
            pass
    return None

# --- Turkish text normalization and scoring helpers ---
def normalize_text_tr(value: str) -> str:
    """Türkçe için basit normalizasyon: küçük harf, aksan/özel harfleri sadeleştir, fazla boşlukları sil."""
    if not value:
        return ''
    s = str(value)
    replacements = {
        'Ç': 'C', 'Ş': 'S', 'Ğ': 'G', 'İ': 'I', 'I': 'I', 'Ö': 'O', 'Ü': 'U',
        'ç': 'c', 'ş': 's', 'ğ': 'g', 'ı': 'i', 'ö': 'o', 'ü': 'u'
    }
    s = ''.join(replacements.get(ch, ch) for ch in s)
    s = s.lower()
    s = ' '.join(s.split())
    return s

def compute_relevance_score(query: str, title: str, authors: str = '', publishers: str = '') -> float:
    """Basit alaka puanı: tam eşleşme/başlangıç/alt dize ve benzerlik puanı.
    Daha yüksek puan daha alakalı demektir.
    """
    import difflib
    q = normalize_text_tr(query)
    t = normalize_text_tr(title)
    a = normalize_text_tr(authors)
    p = normalize_text_tr(publishers)
    score = 0.0
    if not q or not (t or a or p):
        return score
    # Title exact
    if t == q:
        score += 120
    # Title startswith
    if t.startswith(q):
        score += 70
    # Title contains
    if q in t:
        score += 50
    # Token coverage in title
    tokens = [tok for tok in q.split(' ') if tok]
    if tokens:
        covered = sum(1 for tok in tokens if tok in t)
        score += covered * 12
    # Authors/publishers
    if q in a:
        score += 25
    if q in p:
        score += 10
    # Fuzzy similarity on title
    try:
        ratio = difflib.SequenceMatcher(None, q, t).ratio()
        score += ratio * 40
    except Exception:
        pass
    return score

def calculate_fine(due_date, return_date=None):
    """Calculate fine amount for overdue books (supports YYYY-MM-DD and YYYY-MM-DD HH:MM:SS)"""
    def _parse_dt(value):
        if isinstance(value, datetime):
            return value
        if not value:
            return None
        # Try full datetime first
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt)
            except Exception:
                continue
        return None

    ret_dt = _parse_dt(return_date) or datetime.now()
    due_dt = _parse_dt(due_date)
    if not due_dt:
        return 0.0
    
    if ret_dt <= due_dt:
        return 0.0
    
    days_overdue = (ret_dt.date() - due_dt.date()).days
    fine_per_day = float(get_setting('fine_per_day', '1.0'))
    return max(0, days_overdue) * fine_per_day

def send_email(to_email, template_name, context):
    """Send email using template"""
    if get_setting('email_notifications', 'true') != 'true':
        return False
    
    template = EmailTemplate.query.filter_by(name=template_name, is_active=True).first()
    if not template:
        return False
    
    try:
        # Replace variables in template
        subject = template.subject
        body = template.body
        
        for key, value in context.items():
            subject = subject.replace(f"{{{{{key}}}}}", str(value))
            body = body.replace(f"{{{{{key}}}}}", str(value))
        
        msg = Message(
            subject=subject,
            recipients=[to_email],
            body=body
        )
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Email sending error: {e}")
        return False

def fetch_book_info_from_api(isbn):
    """Hibrit API sistemi - Google Books ve Open Library'den en iyi bilgileri birleştir"""
    
    def is_empty_or_invalid(value):
        """Boş, nan, N/A gibi geçersiz değerleri kontrol et"""
        if not value:
            return True
        if isinstance(value, str):
            clean = value.strip().lower()
            return clean in ['', 'nan', 'n/a', 'null', 'none', 'unknown']
        return value == 0
    
    # Her iki API'den de veri çek
    google_info = fetch_from_google_books(isbn)
    openlib_info = fetch_from_openlibrary(isbn)
    
    # Eğer hiçbirinden veri gelmezse None döndür
    if not google_info and not openlib_info:
        return None
    
    # En iyi bilgileri birleştir
    combined_info = {
        'isbn': isbn,
        'title': '',
        'authors': '',
        'publish_date': '',
        'number_of_pages': 0,
        'publishers': '',
        'languages': '',
        'description': '',
        'image_url': ''
    }
    
    # Başlık - önce Google Books, sonra Open Library
    if google_info and not is_empty_or_invalid(google_info.get('title')):
        combined_info['title'] = google_info['title']
    elif openlib_info and not is_empty_or_invalid(openlib_info.get('title')):
        combined_info['title'] = openlib_info['title']
    
    # Yazar - önce Google Books, sonra Open Library
    if google_info and not is_empty_or_invalid(google_info.get('authors')):
        combined_info['authors'] = google_info['authors']
    elif openlib_info and not is_empty_or_invalid(openlib_info.get('authors')):
        combined_info['authors'] = openlib_info['authors']
    
    # Yayınevi - önce Google Books, sonra Open Library
    if google_info and not is_empty_or_invalid(google_info.get('publishers')):
        combined_info['publishers'] = google_info['publishers']
    elif openlib_info and not is_empty_or_invalid(openlib_info.get('publishers')):
        combined_info['publishers'] = openlib_info['publishers']
    
    # Yayın tarihi - önce Google Books, sonra Open Library
    if google_info and not is_empty_or_invalid(google_info.get('publish_date')):
        combined_info['publish_date'] = google_info['publish_date']
    elif openlib_info and not is_empty_or_invalid(openlib_info.get('publish_date')):
        combined_info['publish_date'] = openlib_info['publish_date']
    
    # Sayfa sayısı - önce Google Books, sonra Open Library
    if google_info and google_info.get('number_of_pages', 0) > 0:
        combined_info['number_of_pages'] = google_info['number_of_pages']
    elif openlib_info and openlib_info.get('number_of_pages', 0) > 0:
        combined_info['number_of_pages'] = openlib_info['number_of_pages']
    
    # Dil - önce Google Books, sonra Open Library
    if google_info and not is_empty_or_invalid(google_info.get('languages')):
        combined_info['languages'] = google_info['languages']
    elif openlib_info and not is_empty_or_invalid(openlib_info.get('languages')):
        combined_info['languages'] = openlib_info['languages']
    
    # Açıklama - önce Google Books, sonra Open Library
    if google_info and not is_empty_or_invalid(google_info.get('description')):
        combined_info['description'] = google_info['description']
    elif openlib_info and not is_empty_or_invalid(openlib_info.get('description')):
        combined_info['description'] = openlib_info['description']
    
    # Kapak resmi - önce Google Books, sonra Open Library
    if google_info and google_info.get('image_url'):
        combined_info['image_url'] = google_info['image_url']
    elif openlib_info and openlib_info.get('image_url'):
        combined_info['image_url'] = openlib_info['image_url']
    
    return combined_info

def fetch_from_google_books(isbn):
    """Fetch book info from Google Books API"""
    try:
        url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
        # SSL certificate verification disabled for PyInstaller executable compatibility
        import sys
        if hasattr(sys, 'frozen'):
            # Running as PyInstaller executable
            response = requests.get(url, verify=False, timeout=10)
        else:
            # Running normally
            response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get("totalItems", 0) > 0:
            item = data["items"][0]["volumeInfo"]
            return {
                "isbn": isbn,
                "title": item.get("title", "N/A"),
                "authors": ", ".join(item.get("authors", [])) or "N/A",
                "publish_date": item.get("publishedDate", "N/A"),
                "number_of_pages": item.get("pageCount", 0),
                "publishers": item.get("publisher", "N/A"),
                "languages": item.get("language", "N/A"),
                "description": item.get("description", ""),
                "image_url": item.get("imageLinks", {}).get("thumbnail")
            }
    except:
        pass
    return None

def fetch_from_openlibrary_for_cover(isbn):
    try:
        url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
        # SSL certificate verification disabled for PyInstaller executable compatibility
        import sys
        if hasattr(sys, 'frozen'):
            # Running as PyInstaller executable
            response = requests.get(url, verify=False, timeout=10)
        else:
            # Running normally
            response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        key = f"ISBN:{isbn}"
        if key in data and "cover" in data[key]:
            book = data[key]
            image_url = book["cover"].get("large") or book["cover"].get("medium") or None
            return {"image_url": image_url}
    except Exception as e:
        print(f"OpenLibrary Cover Error: {e}")
    return None

def fetch_from_openlibrary(isbn):
    try:
        url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
        # SSL certificate verification disabled for PyInstaller executable compatibility
        import sys
        if hasattr(sys, 'frozen'):
            # Running as PyInstaller executable
            response = requests.get(url, verify=False, timeout=10)
        else:
            # Running normally
            response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        key = f"ISBN:{isbn}"
        if key in data:
            book = data[key]
            # Güvenli veri çıkarma fonksiyonları
            def safe_get_authors(authors_data):
                if not authors_data:
                    return ""
                try:
                    if isinstance(authors_data, list):
                        return ", ".join([author.get('name', '') for author in authors_data if author.get('name')])
                    return ""
                except:
                    return ""
            
            def safe_get_publishers(publishers_data):
                if not publishers_data:
                    return ""
                try:
                    if isinstance(publishers_data, list):
                        return ", ".join([pub.get('name', '') for pub in publishers_data if pub.get('name')])
                    return ""
                except:
                    return ""
            
            def safe_get_languages(languages_data):
                if not languages_data:
                    return ""
                try:
                    if isinstance(languages_data, list):
                        langs = []
                        for lang in languages_data:
                            if isinstance(lang, dict) and 'key' in lang:
                                lang_code = lang['key'].split('/')[-1]
                                langs.append(lang_code)
                        return ", ".join(langs) if langs else ""
                    return ""
                except:
                    return ""
            
            def safe_get_description(desc_data):
                if not desc_data:
                    return ""
                try:
                    if isinstance(desc_data, dict):
                        return desc_data.get("value", "")
                    elif isinstance(desc_data, str):
                        return desc_data
                    return ""
                except:
                    return ""
            
            book_info = {
                "isbn": isbn,
                "title": book.get("title", ""),
                "authors": safe_get_authors(book.get("authors")),
                "publish_date": book.get("publish_date", ""),
                "number_of_pages": book.get("number_of_pages", 0) or 0,
                "publishers": safe_get_publishers(book.get("publishers")),
                "languages": safe_get_languages(book.get("languages")),
                "description": safe_get_description(book.get("description")),
                "image_url": None
            }
            if "cover" in book:
                image_url = book["cover"].get("large") or book["cover"].get("medium") or None
                book_info["image_url"] = image_url
            return book_info
    except Exception as e:
        print(f"OpenLibrary Error: {e}")
    return None

def add_notification(type, message, related_isbn=None):
    """Add a new notification"""
    notification = Notification(
        type=type,
        message=message,
        created_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        related_isbn=related_isbn
    )
    db.session.add(notification)
    db.session.commit()

def check_overdue_books():
    """Check for overdue books and create notifications"""
    # Books due soon
    upcoming = db.session.query(Transaction, Book, Member).join(Book, Transaction.isbn == Book.isbn)\
        .join(Member, Transaction.member_id == Member.id)\
        .filter(Transaction.return_date == None)\
        .filter(Transaction.due_date <= (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d"))\
        .filter(Transaction.due_date >= datetime.now().strftime("%Y-%m-%d")).all()
    
    for trans, book, member in upcoming:
        message = f"'{book.title}' kitabı {member.ad_soyad} tarafından {trans.due_date} tarihine kadar iade edilmelidir."
        add_notification("return_reminder", message, book.isbn)
    
    # Overdue books
    overdue = db.session.query(Transaction, Book, Member).join(Book, Transaction.isbn == Book.isbn)\
        .join(Member, Transaction.member_id == Member.id)\
        .filter(Transaction.return_date == None)\
        .filter(Transaction.due_date < datetime.now().strftime("%Y-%m-%d")).all()
    
    for trans, book, member in overdue:
        message = f"'{book.title}' kitabı {member.ad_soyad} tarafından {trans.due_date} tarihinden beri gecikmiştir."
        add_notification("overdue", message, book.isbn)

def process_borrow_transaction(book, member, method, notes):
    """Ödünç alma işlemini işle"""
    # Ceza kontrolü
    if member.penalty_until and datetime.now() < member.penalty_until:
        return jsonify({'success': False, 'message': 'Üyenin ceza süresi devam ediyor'}), 403
    
    # Kullanılabilirlik kontrolü
    borrowed_count = Transaction.query.filter_by(isbn=book.isbn, return_date=None).count()
    if book.quantity <= borrowed_count:
        return jsonify({'success': False, 'message': 'Kitap şu anda mevcut değil'}), 400
    
    # Kullanıcının bu kitabı zaten ödünç alıp almadığını kontrol et
    existing_borrow = Transaction.query.filter_by(
        isbn=book.isbn, 
        member_id=member.id, 
        return_date=None
    ).first()
    
    if existing_borrow:
        return jsonify({'success': False, 'message': 'Bu üye kitabı zaten ödünç almış'}), 400
    
    # Aktif ödünç alma sayısı kontrolü
    active_borrows = Transaction.query.filter_by(member_id=member.id, return_date=None).count()
    max_books = int(get_setting('max_books_per_member', '5'))
    if active_borrows >= max_books:
        return jsonify({'success': False, 'message': f'Üye maksimum {max_books} kitap ödünç alabilir'}), 400
    
    # Ödünç alma işlemi
    due_date = (datetime.now() + timedelta(days=int(get_setting('max_borrow_days', '14')))).strftime('%Y-%m-%d %H:%M:%S')
    
    transaction = Transaction(
        isbn=book.isbn,
        member_id=member.id,
        borrow_date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        due_date=due_date,
        notes=f'{method.upper()} ile ödünç alındı - {notes}'
    )
    
    # Kitap istatistiklerini güvenli şekilde güncelle
    book.last_borrowed_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    book.total_borrow_count = (book.total_borrow_count or 0) + 1
    
    # Üye istatistiklerini güvenli şekilde güncelle
    member.total_borrowed = (member.total_borrowed or 0) + 1
    member.current_borrowed = (member.current_borrowed or 0) + 1
    
    db.session.add(transaction)
    db.session.commit()
    
    # Bildirim oluştur
    add_notification('borrow', f'"{book.title}" kitabı ödünç alındı', book.isbn)
    
    # E-posta bildirimi gönder
    if member.email:
        send_email(member.email, 'book_borrowed', {
            'member_name': member.ad_soyad,
            'book_title': book.title,
            'due_date': due_date,
            'borrow_date': transaction.borrow_date
        })
    
    log_activity('borrow_transaction', f'{method.upper()} ile ödünç alma: {book.title} - {member.ad_soyad}')
    
    return jsonify({
        'success': True,
        'message': 'Kitap başarıyla ödünç alındı',
        'transaction': {
            'id': transaction.id,
            'book_title': book.title,
            'member_name': member.ad_soyad,
            'due_date': due_date,
            'borrow_date': transaction.borrow_date,
            'method': method
        }
    })

def process_return_transaction(transaction, notes, method, check_fines=True):
    """
    Bir iade işlemini işler, kitap durumunu günceller ve gerekirse ceza oluşturur.
    Kiosk gibi kullanıcı oturumu olmayan ortamlarla uyumludur.
    """
    if not transaction:
        return {'success': False, 'message': 'İade edilecek işlem bulunamadı.'}

    # İade işlemi
    transaction.return_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    previous_notes = transaction.notes or ''
    try:
        method_label = str(method).upper()
    except AttributeError:
        method_label = str(method) # method'un string olmayan bir tip olma ihtimaline karşı
    transaction.notes = (previous_notes + ' - ' if previous_notes else '') + f'{method_label} ile iade edildi. Not: {notes}'

    # Kitap durumunu güncelle
    book = Book.query.get(transaction.isbn)
    if book:
        book.status = 'available'

    # Güvenli kullanıcı ID'si al - kiosk ortamında current_user olmayabilir
    try:
        user_id = current_user.id if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated else None
    except Exception:
        user_id = None  # Kiosk ortamında kullanıcı girişi yok

    # Ceza kontrolü (sadece check_fines True ise)
    if check_fines:
        try:
            due_date = datetime.strptime(transaction.due_date, '%Y-%m-%d')
            return_date_dt = datetime.now()
            if return_date_dt > due_date:
                days_late = (return_date_dt - due_date).days
                if days_late > 0:
                    fine_amount = days_late * 0.5  # Günlük 0.5 TL ceza
                    fine = Fine(
                        user_id=user_id, # Güvenli user_id'yi kullan
                        member_id=transaction.member_id,
                        transaction_id=transaction.id,
                        amount=fine_amount,
                        reason=f"{days_late} gün geç iade"
                    )
                    db.session.add(fine)
                    log_activity('fine_created', f'Ceza oluşturuldu: {fine_amount} TL, Üye ID: {transaction.member_id}', user_id=user_id)
        except (ValueError, TypeError) as e:
            log_activity('error', f"Ceza hesaplama hatası: {str(e)} - transaction ID: {transaction.id}")

    log_activity('book_returned', f'Kitap iade edildi: {book.title if book else transaction.isbn}, Üye ID: {transaction.member_id}', user_id=user_id)
    
    # Veritabanı değişikliklerini kaydet
    try:
        db.session.commit()
        return {'success': True, 'message': 'İade işlemi başarılı'}
    except Exception as e:
        db.session.rollback()
        log_activity('error', f'İade işlemi commit hatası: {str(e)}', user_id=user_id)
        return {'success': False, 'message': f'Veritabanı hatası: {str(e)}'}

# Backup and Restore Functions
def create_backup():
    """Create database backup"""
    try:
        backup_dir = 'backups'
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f'backup_{timestamp}.db'
        backup_path = os.path.join(backup_dir, backup_filename)
        
        # Copy database file
        shutil.copy2('instance/books_info.db', backup_path)
        
        log_activity('create_backup', f'Created backup: {backup_filename}')
        
        return backup_filename
    except Exception as e:
        print(f"Backup error: {e}")
        return None

def restore_backup(filename):
    """Restore database from backup"""
    try:
        backup_dir = 'backups'
        backup_path = os.path.join(backup_dir, filename)
        
        if not os.path.exists(backup_path) or not filename.endswith('.db'):
            return False
        
        # Tüm bağlantıları kapat
        db.session.close_all()
        db.engine.dispose()
        
        # Mevcut veritabanını yedekle
        shutil.copy2('instance/books_info.db', 'instance/books_info_before_restore.db')
        
        # Yedeği geri yükle
        shutil.copy2(backup_path, 'instance/books_info.db')
        
        log_activity('restore_backup', f'Restored from backup: {filename}')
        
        # Windows Explorer'da dosyayı aç
        abs_db_path = os.path.abspath('instance/books_info.db')
        subprocess.Popen(f'explorer /select,"{abs_db_path}"')
        
        # Otomatik yeniden başlatma (Windows için)
        os.execl(sys.executable, sys.executable, *sys.argv)
        
        return True
    except Exception as e:
        print(f"Restore error: {e}")
        return False

# QR Code Functions
def generate_user_qr():
    """Generate QR code for user"""
    qr_token = secrets.token_urlsafe(32)
    expiry_time = datetime.utcnow() + timedelta(minutes=30)  # 30 dakika geçerli
    
    # QR kod bilgilerini veritabanına kaydet
    qr_code = QRCode(
        user_id=current_user.id,
        token=qr_token,
        expiry_time=expiry_time,
        status='active'
    )
    
    db.session.add(qr_code)
    db.session.commit()
    
    # QR kod URL'si oluştur
    qr_url = f"{request.host_url}qr/verify/{qr_token}"
    
    return {
        'qr_token': qr_token,
        'qr_url': qr_url,
        'expiry_time': expiry_time.strftime('%H:%M:%S'),
        'expires_in': 30  # dakika
    }

def verify_qr_code(token):
    """Verify QR code token"""
    qr_code = QRCode.query.filter_by(token=token).first()
    
    if not qr_code:
        return {'success': False, 'message': 'QR kod bulunamadı'}
    
    if qr_code.status != 'active':
        return {'success': False, 'message': 'QR kod kullanılmış veya süresi dolmuş'}
    
    if datetime.utcnow() > qr_code.expiry_time:
        qr_code.status = 'expired'
        db.session.commit()
        return {'success': False, 'message': 'QR kod süresi dolmuş'}
    
    # Kullanıcı bilgilerini getir
    user = User.query.get(qr_code.user_id)
    member = Member.query.filter_by(user_id=qr_code.user_id).first()
    
    return {
        'success': True,
        'user_info': {
            'username': user.username,
            'email': user.email,
            'member_name': member.ad_soyad if member else 'Üye bilgisi bulunamadı',
            'member_id': member.id if member else None
        },
        'expires_in': int((qr_code.expiry_time - datetime.utcnow()).total_seconds())
    }

def use_qr_code(token):
    """Use QR code (mark as used)"""
    qr_code = QRCode.query.filter_by(token=token).first()
    
    if not qr_code or qr_code.status != 'active':
        return False
    
    qr_code.status = 'used'
    qr_code.used_at = datetime.utcnow()
    db.session.commit()
    
    return True

# PDF Generation Functions - Simple approach for Turkish support
def create_html_to_pdf(title, subtitle, headers, rows, stats_text):
    """Create PDF from HTML - Better Turkish support"""
    from datetime import datetime
    import tempfile
    import os
    
    # HTML template with proper UTF-8 and Turkish support
    html_content = f"""
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
        <style>
            @page {{
                size: A4 landscape;
                margin: 1.2cm;
            }}
            body {{
                font-family: Arial, sans-serif;
                color: #333;
                line-height: 1.3;
            }}
            .header {{
                text-align: center;
                margin-bottom: 24px;
            }}
            .title {{
                font-size: 16px;
                font-weight: bold;
                color: #1e3a8a;
                margin-bottom: 8px;
            }}
            .subtitle {{
                font-size: 13px;
                font-weight: bold;
                margin-bottom: 8px;
            }}
            .date {{
                font-size: 10px;
                color: #666;
                margin-bottom: 16px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 12px;
                font-size: 9px;
            }}
            th {{
                background-color: #6b7280;
                color: white;
                padding: 6px 3px;
                text-align: left;
                border: 1px solid #333;
                font-weight: bold;
            }}
            td {{
                padding: 4px 3px;
                border: 1px solid #ddd;
                background-color: #f5f5dc;
            }}
            tr:nth-child(even) td {{
                background-color: #f9f9f9;
            }}
            .stats {{
                margin-top: 12px;
                font-weight: bold;
                font-size: 10px;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="title">{title}</div>
            <div class="subtitle">{subtitle}</div>
            <div class="date">Rapor Tarihi: {datetime.now().strftime('%d.%m.%Y %H:%M')}</div>
        </div>
        
        <table>
            <thead>
                <tr>
    """
    
    # Add headers
    for header in headers:
        html_content += f"<th>{header}</th>"
    
    html_content += """
                </tr>
            </thead>
            <tbody>
    """
    
    # Add rows
    for row in rows:
        html_content += "<tr>"
        for cell in row:
            html_content += f"<td>{cell}</td>"
        html_content += "</tr>"
    
    html_content += f"""
            </tbody>
        </table>
        
        <div class="stats">
            {stats_text}
        </div>
    </body>
    </html>
    """
    
    try:
        # Try weasyprint first (better Turkish support)
        from weasyprint import HTML, CSS
        from weasyprint.text.fonts import FontConfiguration
        
        buffer = BytesIO()
        font_config = FontConfiguration()
        
        # Create PDF from HTML
        html_doc = HTML(string=html_content, encoding='utf-8')
        css = CSS(string='@page { size: A4 landscape; margin: 1.2cm; }', font_config=font_config)
        
        html_doc.write_pdf(buffer, stylesheets=[css], font_config=font_config)
        buffer.seek(0)
        return buffer
        
    except ImportError:
        try:
            # Fallback to pdfkit
            import pdfkit
            
            options = {
                'page-size': 'A4',
                'orientation': 'Landscape',
                'margin-top': '0.5in',
                'margin-right': '0.5in', 
                'margin-bottom': '0.5in',
                'margin-left': '0.5in',
                'encoding': 'UTF-8',
                'no-outline': None,
                'enable-local-file-access': None
            }
            
            pdf_bytes = pdfkit.from_string(html_content, False, options=options)
            buffer = BytesIO(pdf_bytes)
            return buffer
            
        except:
            # Last fallback - simple text-based PDF
            return create_simple_text_pdf_fallback(title, subtitle, headers, rows, stats_text)

def create_simple_text_pdf_fallback(title, subtitle, headers, rows, stats_text):
    """Ultra simple PDF fallback using only basic ASCII"""
    buffer = BytesIO()
    # Landscape sayfa
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    width, height = landscape(A4)
    
    # Convert everything to ASCII
    def to_ascii(text):
        if text is None:
            return ""
        text = str(text)
        replacements = {
            'ç': 'c', 'ğ': 'g', 'ı': 'i', 'ö': 'o', 'ş': 's', 'ü': 'u',
            'Ç': 'C', 'Ğ': 'G', 'İ': 'I', 'Ö': 'O', 'Ş': 'S', 'Ü': 'U'
        }
        for tr_char, ascii_char in replacements.items():
            text = text.replace(tr_char, ascii_char)
        # Remove any remaining non-ASCII
        text = ''.join(char for char in text if ord(char) < 128)
        return text
    
    # Title
    ascii_title = to_ascii(title)
    c.setFont('Helvetica-Bold', 16)
    text_width = c.stringWidth(ascii_title, 'Helvetica-Bold', 16)
    c.drawString((width - text_width) / 2, height - 60, ascii_title)
    
    # Subtitle
    ascii_subtitle = to_ascii(subtitle)
    c.setFont('Helvetica-Bold', 12)
    text_width = c.stringWidth(ascii_subtitle, 'Helvetica-Bold', 12)
    c.drawString((width - text_width) / 2, height - 90, ascii_subtitle)
    
    # Date
    from datetime import datetime
    date_str = f"Rapor Tarihi: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    c.setFont('Helvetica', 10)
    text_width = c.stringWidth(date_str, 'Helvetica', 10)
    c.drawString((width - text_width) / 2, height - 120, date_str)
    
    # Simple table
    y = height - 170
    c.setFont('Helvetica-Bold', 8)
    x_positions = [50, 140, 240, 340, 440, 500]
    
    # Headers
    for i, header in enumerate(headers):
        if i < len(x_positions):
            ascii_header = to_ascii(header)
            c.drawString(x_positions[i], y, ascii_header)
    
    # Rows
    y -= 20
    c.setFont('Helvetica', 7)
    
    for row in rows[:50]:  # Limit to 50 rows
        if y < 50:
            c.showPage()
            y = height - 50
        
        for i, cell in enumerate(row):
            if i < len(x_positions):
                ascii_cell = to_ascii(str(cell))
                if len(ascii_cell) > 15:
                    ascii_cell = ascii_cell[:12] + '...'
                c.drawString(x_positions[i], y, ascii_cell)
        y -= 15
    
    # Stats
    c.setFont('Helvetica-Bold', 10)
    ascii_stats = to_ascii(stats_text)
    c.drawString(50, y - 20, ascii_stats)
    
    c.save()
    buffer.seek(0)
    return buffer

# Basit ReportLab PDF fonksiyonu - QR kod PDF'i gibi çalışır
def create_simple_reportlab_pdf(title, subtitle, headers, rows, stats_text):
    """Create PDF using ReportLab - Simple and reliable like QR PDF"""
    buffer = BytesIO()
    # Rapor çıktıları yatay (landscape)
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    width, height = landscape(A4)
    
    # Türkçe karakterleri ASCII'ye çevir (normalize + diacritic remove)
    def to_ascii(text):
        if not text:
            return ''
        import unicodedata as _ud
        # Önce bilinen Türkçe harfleri dönüştür
        tr_chars = {
            'İ': 'I', 'İ': 'I', 'ı': 'i', 'Ğ': 'G', 'ğ': 'g', 'Ü': 'U', 'ü': 'u',
            'Ş': 'S', 'ş': 's', 'Ö': 'O', 'ö': 'o', 'Ç': 'C', 'ç': 'c'
        }
        for tr, en in tr_chars.items():
            text = text.replace(tr, en)
        # Unicode normalize edip combining mark'ları temizle
        normalized = _ud.normalize('NFKD', text)
        stripped = ''.join(ch for ch in normalized if _ud.category(ch) != 'Mn')
        return stripped
    
    # Header
    c.setFont('Helvetica-Bold', 8)
    title_ascii = to_ascii(title)
    title_width = c.stringWidth(title_ascii, 'Helvetica-Bold', 16)
    c.drawString((width - title_width) / 2, height - 50, title_ascii)
    
    c.setFont('Helvetica-Bold', 8)
    subtitle_ascii = to_ascii(subtitle)
    subtitle_width = c.stringWidth(subtitle_ascii, 'Helvetica-Bold', 14)
    c.drawString((width - subtitle_width) / 2, height - 80, subtitle_ascii)
    
    # Date
    from datetime import datetime
    date_str = f"Rapor Tarihi: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    c.setFont('Helvetica', 8)
    date_width = c.stringWidth(date_str, 'Helvetica', 10)
    c.drawString((width - date_width) / 2, height - 100, date_str)
    
    # Table headers
    y = height - 140
    c.setFont('Helvetica-Bold', 9)

    # Column positions ve max uzunluklar (liste türüne göre optimize)
    subtitle_ascii = to_ascii(subtitle).lower()
    x_positions = []
    max_lengths = []
    # Kitap raporu - daha fazla sütun (Dolap, Raf eklenmiş -> 9 sütun)
    if 'kitap' in subtitle_ascii and len(headers) >= 9:
        # Sıra, ISBN, Kitap, Yazar, Yayınevi, Kategori, Dolap, Raf, Mevcut/Toplam
        x_positions = [20, 70, 130, 300, 430, 520, 600, 680, 760]
        max_lengths = [4, 13, 32, 22, 20, 12, 6, 6, 10]
    elif 'kitap' in subtitle_ascii and len(headers) == 8:
        # Sıra, ISBN, Kitap, Yazar, Yayınevi, Kategori, Raf, Mevcut/Toplam
        x_positions = [20, 70, 130, 300, 430, 520, 680, 760]
        max_lengths = [4, 13, 34, 22, 20, 12, 6, 10]
    # Kitap raporu - 7 sütun (landscape)
    elif 'kitap' in subtitle_ascii and len(headers) >= 7:
        x_positions = [30, 90, 170, 380, 500, 590, 700]
        max_lengths = [4, 13, 42, 24, 30, 16, 12]
    elif 'kitap' in subtitle_ascii and len(headers) >= 6:
        x_positions = [30, 90, 210, 400, 480, 540]
        max_lengths = [4, 13, 36, 22, 16, 12]
    # Üyeler raporu - 5 sütun (Öğrenci No ve E-posta kaldırıldı)
    elif ('uye' in subtitle_ascii or 'üye' in subtitle.lower()) and len(headers) >= 5:
        x_positions = [40, 220, 350, 480, 600]
        max_lengths = [4, 36, 14, 14, 14]
    # İşlemler raporu - 7 sütun (landscape)
    elif ('islem' in subtitle_ascii or 'işlem' in subtitle.lower()) and len(headers) >= 7:
        x_positions = [30, 120, 220, 480, 620, 720, 800]
        max_lengths = [4, 13, 34, 24, 14, 14, 10]
    elif ('islem' in subtitle_ascii or 'işlem' in subtitle.lower()) and len(headers) >= 6:
        x_positions = [40, 100, 320, 430, 510, 560]
        max_lengths = [4, 30, 22, 14, 14, 10]
    else:
        # Varsayılan dağılım
        if len(headers) == 7:
            x_positions = [30, 90, 180, 300, 400, 500, 560]
            max_lengths = [4, 13, 24, 18, 14, 14, 10]
        elif len(headers) == 6:
            x_positions = [50, 120, 200, 320, 420, 500]
            max_lengths = [6, 12, 18, 14, 12, 10]
        elif len(headers) == 5:
            x_positions = [50, 130, 230, 350, 470]
            max_lengths = [6, 18, 18, 16, 14]
        else:
            x_positions = [50, 150, 250, 350, 450]
            max_lengths = [16, 16, 16, 16, 16]
    
    # Draw headers
    for i, header in enumerate(headers[:len(x_positions)]):
        if i < len(x_positions):
            header_ascii = to_ascii(header)
            c.drawString(x_positions[i], y, header_ascii)
    
    # Draw line under headers
    c.line(40, y-5, width-40, y-5)
    
    # Table rows
    y -= 22
    c.setFont('Helvetica', 8)
    
    for row in rows:  # Tüm satırları yazdır, limit yok
        if y < 50:  # New page
            c.showPage()
            y = height - 50
            c.setFont('Helvetica', 8)
        
        for i, cell in enumerate(row[:len(x_positions)]):
            if i < len(x_positions):
                cell_ascii = to_ascii(str(cell))
                # Sütun bazlı truncation
                max_len = max_lengths[i] if i < len(max_lengths) else 15
                if len(cell_ascii) > max_len:
                    cell_ascii = cell_ascii[:max(3, max_len - 3)] + '...'
                c.drawString(x_positions[i], y, cell_ascii)
        y -= 13
    
    # Stats
    if y < 80:
        c.showPage()
        y = height - 50
    
    c.setFont('Helvetica-Bold', 8)
    stats_ascii = to_ascii(stats_text)
    c.drawString(50, y - 20, stats_ascii)
    
    c.save()
    buffer.seek(0)
    return buffer

def generate_books_list_pdf(books):
    """Generate books list PDF (ISBN, Yayınevi ve Mevcut/Toplam dahil)"""
    title = "CUMHURİYET ANADOLU LİSESİ KÜTÜPHANESİ"
    subtitle = "Kitaplar Listesi"
    # Dolap ve Raf sütunlarını ekledik
    headers = ['Sıra', 'ISBN', 'Kitap Adı', 'Yazar', 'Yayınevi', 'Kategori', 'Dolap', 'Raf', 'Mevcut/Toplam']
    
    # Dolap ve Raf'a göre sırala (dolap -> raf -> başlık)
    def safe_lower(value):
        return (str(value) if value is not None else '').strip().lower()

    sorted_books = sorted(
        books,
        key=lambda b: (
            safe_lower(getattr(b, 'cupboard', '')),
            safe_lower(getattr(b, 'shelf', '')),
            safe_lower(getattr(b, 'title', ''))
        )
    )

    rows = []
    for i, book in enumerate(sorted_books, 1):
        try:
            # Safe attribute access
            status = 'Mevcut' if getattr(book, 'durum', None) == 'mevcut' else 'Ödünç Verildi'
            title_text = getattr(book, 'title', 'Bilinmiyor')
            authors = getattr(book, 'authors', 'Bilinmiyor')
            publishers = getattr(book, 'publishers', None) or '-'
            category = getattr(book, 'category', None) or 'Belirtilmemiş'
            cupboard = getattr(book, 'cupboard', None) or '-'
            shelf = getattr(book, 'shelf', None) or '-'
            isbn = getattr(book, 'isbn', '-')
            quantity = getattr(book, 'quantity', 0) or 0
            borrowed = Transaction.query.filter_by(isbn=isbn, return_date=None).count() if isbn and isbn != '-' else 0
            stock_text = f"{max(0, quantity - borrowed)}/{quantity}"
            
            # Truncate if too long
            if len(title_text) > 30:
                title_text = title_text[:27] + '...'
            if len(authors) > 25:
                authors = authors[:22] + '...'
            if len(publishers) > 30:
                publishers = publishers[:27] + '...'
            
            rows.append([
                str(i),
                isbn,
                title_text,
                authors,
                publishers,
                category,
                cupboard,
                shelf,
                stock_text
            ])
        except Exception as e:
            print(f"Book row error: {e}")
            continue
    
    stats_text = f"Toplam Kitap Sayısı: {len(books)}"
    return create_simple_reportlab_pdf(title, subtitle, headers, rows, stats_text)

def generate_members_list_pdf(members):
    """Generate members list PDF (Öğrenci No ve E-posta sütunları kaldırıldı)"""
    title = "CUMHURİYET ANADOLU LİSESİ KÜTÜPHANESİ"
    subtitle = "Üyeler Listesi"
    # Öğrenci No ve E-posta istenmediği için kaldırıldı
    headers = ['Sıra', 'Ad Soyad', 'Sınıf', 'Numara', 'Üye Türü']
    
    # Sınıfa (ve sonra numaraya) göre sırala
    def safe_value(v):
        return (str(v) if v is not None else '').strip()
    def sort_key(m):
        return (safe_value(getattr(m, 'sinif', '')), safe_value(getattr(m, 'numara', '')), safe_value(getattr(m, 'ad_soyad', '')))
    sorted_members = sorted(members, key=sort_key)

    rows = []
    for i, member in enumerate(sorted_members, 1):
        try:
            # Safe attribute access
            ad_soyad = getattr(member, 'ad_soyad', 'Bilinmiyor')
            sinif = getattr(member, 'sinif', None) or '-'
            numara = getattr(member, 'numara', None) or '-'
            email = getattr(member, 'email', None) or '-'
            uye_turu = getattr(member, 'uye_turu', None) or 'Öğrenci'
            
            # Truncate if too long
            if len(ad_soyad) > 25:
                ad_soyad = ad_soyad[:22] + '...'
            if email != '-' and len(email) > 25:
                email = email[:22] + '...'
            
            rows.append([
                str(i),
                ad_soyad,
                sinif,
                numara,
                uye_turu
            ])
        except Exception as e:
            print(f"Member row error: {e}")
            continue
    
    stats_text = f"Toplam Üye Sayısı: {len(members)}"
    return create_simple_reportlab_pdf(title, subtitle, headers, rows, stats_text)

def generate_transactions_list_pdf(transactions):
    """Generate transactions list PDF (ISBN sütunu eklendi)"""
    title = "CUMHURİYET ANADOLU LİSESİ KÜTÜPHANESİ"
    subtitle = "İşlemler Listesi"
    headers = ['Sıra', 'ISBN', 'Kitap', 'Üye', 'Ödünç Tarihi', 'İade Tarihi', 'Durum']
    
    # Tarihlere göre sırala (Ödünç tarihi, en yeni en üstte)
    from datetime import datetime as _dt
    def parse_date(d):
        try:
            return _dt.strptime(d, '%Y-%m-%d') if d else _dt.min
        except:
            return _dt.min
    sorted_transactions = sorted(transactions, key=lambda t: parse_date(getattr(t, 'borrow_date', None)), reverse=True)

    rows = []
    for i, transaction in enumerate(sorted_transactions, 1):
        try:
            # Safe relationship access - handle missing book/member relationships
            isbn = getattr(transaction, 'isbn', '-') or '-'
            book_title = 'Bilinmiyor'
            member_name = 'Bilinmiyor'
            
            # Try to get book info
            if hasattr(transaction, 'book') and transaction.book:
                book_title = getattr(transaction.book, 'title', 'Bilinmiyor')
                if len(book_title) > 25:
                    book_title = book_title[:22] + '...'
            elif hasattr(transaction, 'isbn') and transaction.isbn:
                # If no book relationship, try to get from ISBN
                from models import Book
                book = Book.query.filter_by(isbn=transaction.isbn).first()
                if book:
                    book_title = getattr(book, 'title', 'Bilinmiyor')
                    if len(book_title) > 25:
                        book_title = book_title[:22] + '...'
                else:
                    book_title = f"ISBN: {transaction.isbn}"
            
            # Try to get member info
            if hasattr(transaction, 'member') and transaction.member:
                member_name = getattr(transaction.member, 'ad_soyad', 'Bilinmiyor')
                if len(member_name) > 20:
                    member_name = member_name[:17] + '...'
            elif hasattr(transaction, 'member_id') and transaction.member_id:
                # If no member relationship, try to get from member_id
                from models import Member
                member = Member.query.filter_by(id=transaction.member_id).first()
                if member:
                    member_name = getattr(member, 'ad_soyad', 'Bilinmiyor')
                    if len(member_name) > 20:
                        member_name = member_name[:17] + '...'
                else:
                    member_name = f"ID: {transaction.member_id}"
            
            # Get dates and status
            borrow_date = getattr(transaction, 'borrow_date', None) or '-'
            return_date = getattr(transaction, 'return_date', None) or '-'
            status = 'İade Edildi' if return_date != '-' else 'Ödünç'
            
            rows.append([
                str(i),
                isbn,
                book_title,
                member_name,
                borrow_date,
                return_date,
                status
            ])
        except Exception as e:
            print(f"Transaction row error: {e}")
            # Add error row to continue processing
            rows.append([
                str(i),
                'Hata',
                'Hata',
                '-',
                '-',
                'Hata'
            ])
            continue
    
    try:
        active_count = len([t for t in transactions if not getattr(t, 'return_date', None)])
        completed_count = len([t for t in transactions if getattr(t, 'return_date', None)])
    except:
        active_count = 0
        completed_count = len(transactions)
    
    stats_text = f"Toplam İşlem: {len(transactions)} | Aktif Ödünç: {active_count} | Tamamlanan: {completed_count}"
    return create_simple_reportlab_pdf(title, subtitle, headers, rows, stats_text)

def generate_books_qr_pdf(books):
    """Generate QR codes for books in PDF format"""
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    x, y = 20*mm, height-60*mm
    qr_size = 40*mm
    per_row = 4
    count = 0
    
    for book in books:
        qr_img = qrcode.make(book.isbn)
        c.drawInlineImage(qr_img, x, y, qr_size, qr_size)
        c.setFont('Helvetica', 8)
        c.drawString(x, y-8, f"{book.title[:30]}")
        c.drawString(x, y-16, f"ISBN: {book.isbn}")
        
        x += (qr_size + 10*mm)
        count += 1
        
        if count % per_row == 0:
            x = 20*mm
            y -= (qr_size + 20*mm)
            if y < 60*mm:
                c.showPage()
                x, y = 20*mm, height-60*mm
    
    c.save()
    buffer.seek(0)
    return buffer


    
    # Story list to hold content
    story = []
    
    # Subtitle style
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Heading2'],
        fontName=title_font,
        fontSize=14,
        spaceAfter=12,
        alignment=TA_CENTER,
        textColor=colors.black
    )
    
    # Normal style
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontName=normal_font,
        fontSize=10
    )
    
    # Title - UTF-8 encoding ile
    title_text = u"CUMHURİYET ANADOLU LİSESİ KÜTÜPHANESİ"
    title = Paragraph(title_text.encode('utf-8').decode('utf-8'), title_style)
    story.append(title)
    
    subtitle_text = u"Kitaplar Listesi"
    subtitle = Paragraph(subtitle_text.encode('utf-8').decode('utf-8'), subtitle_style)
    story.append(subtitle)
    
    # Add date
    date_str = f"Rapor Tarihi: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    story.append(Paragraph(date_str, normal_style))
    story.append(Spacer(1, 12))
    
    # Create table data - UTF-8 encoded
    table_headers = [u'Sıra', u'ISBN', u'Kitap Adı', u'Yazar', u'Kategori', u'Durum']
    table_data = [table_headers]
    
    for i, book in enumerate(books, 1):
        status = u'Mevcut' if book.durum == 'mevcut' else u'Ödünç Verildi'
        
        # Türkçe karakterleri düzgün encode et
        title = (book.title[:40] + '...') if len(book.title) > 40 else book.title
        authors = (book.authors[:30] + '...') if len(book.authors) > 30 else book.authors
        category = book.category or u'Belirtilmemiş'
        
        table_data.append([
            str(i),
            book.isbn or '-',
            title,
            authors,
            category,
            status
        ])
    
    # Create table
    table = Table(table_data, colWidths=[1*cm, 3*cm, 6*cm, 4*cm, 2.5*cm, 2.5*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), title_font),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, 1), (-1, -1), normal_font),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    story.append(table)
    
    # Add statistics
    story.append(Spacer(1, 20))
    stats_text = f"Toplam Kitap Sayısı: {len(books)}"
    story.append(Paragraph(stats_text, normal_style))
    
    doc.build(story)
    buffer.seek(0)
    return buffer

## duplicate generate_members_list_pdf removed; using the simplified ReportLab version above

## duplicate generate_transactions_list_pdf removed; using the simplified ReportLab version above

def generate_members_qr_pdf(members):
    """Generate QR codes for members in PDF format"""
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    x, y = 20*mm, height-60*mm
    qr_size = 40*mm
    per_row = 4
    count = 0
    
    for member in members:
        qr_img = qrcode.make(str(member.id))
        c.drawInlineImage(qr_img, x, y, qr_size, qr_size)
        c.setFont('Helvetica', 8)
        c.drawString(x, y-8, f"{member.ad_soyad[:30]}")
        c.drawString(x, y-16, f"No: {member.numara}")
        
        x += (qr_size + 10*mm)
        count += 1
        
        if count % per_row == 0:
            x = 20*mm
            y -= (qr_size + 20*mm)
            if y < 60*mm:
                c.showPage()
                x, y = 20*mm, height-60*mm
    
    c.save()
    buffer.seek(0)
    return buffer

def export_to_excel(data, sheet_name='Data'):
    """Export data to Excel format"""
    df = pd.DataFrame(data)
    temp = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
    df.to_excel(temp.name, sheet_name=sheet_name, index=False)
    temp.close()
    return temp.name

# Online Borrow Request Functions
def process_online_borrow_request(request_data):
    """Process online borrow request"""
    isbn = request_data.get('isbn')
    pickup_date = request_data.get('pickup_date')
    pickup_time = request_data.get('pickup_time')
    notes = request_data.get('notes', '')
    
    # Kitap kontrolü
    book = Book.query.get(isbn)
    if not book:
        return {'success': False, 'message': 'Kitap bulunamadı'}
    
    # Kullanılabilirlik kontrolü
    borrowed_count = Transaction.query.filter_by(isbn=isbn, return_date=None).count()
    if book.quantity <= borrowed_count:
        return {'success': False, 'message': 'Kitap şu anda mevcut değil'}
    
    # Üye kontrolü
    member = Member.query.filter_by(user_id=current_user.id).first()
    if not member:
        return {'success': False, 'message': 'Üye kaydınız bulunamadı'}
    
    # Ceza kontrolü
    if member.penalty_until and datetime.now() < member.penalty_until:
        return {'success': False, 'message': 'Ceza süreniz devam ediyor'}
    
    # Aktif ödünç alma sayısı kontrolü
    active_borrows = Transaction.query.filter_by(member_id=member.id, return_date=None).count()
    max_books = int(get_setting('max_books_per_member', '5'))
    if active_borrows >= max_books:
        return {'success': False, 'message': f'Maksimum {max_books} kitap ödünç alabilirsiniz'}
    
    # Online ödünç alma talebi oluştur
    online_request = OnlineBorrowRequest(
        isbn=isbn,
        user_id=current_user.id,
        member_id=member.id,
        pickup_date=pickup_date,
        pickup_time=pickup_time,
        notes=notes,
        status='pending'
    )
    
    db.session.add(online_request)
    db.session.commit()
    
    # E-posta bildirimi gönder
    send_email(current_user.email, 'online_borrow_request', {
        'member_name': current_user.username,
        'book_title': book.title,
        'pickup_date': pickup_date,
        'pickup_time': pickup_time,
        'request_id': online_request.id
    })
    
    # Admin'lere bildirim gönder
    admins = User.query.filter_by(role='admin').all()
    for admin in admins:
        send_email(admin.email, 'admin_online_borrow_notification', {
            'member_name': current_user.username,
            'book_title': book.title,
            'pickup_date': pickup_date,
            'pickup_time': pickup_time,
            'request_id': online_request.id
        })
    
    log_activity('online_borrow_request', f'Online ödünç alma talebi: {book.title}')
    
    return {
        'success': True, 
        'message': 'Ödünç alma talebiniz alındı. Onaylandığında e-posta ile bilgilendirileceksiniz.',
        'request_id': online_request.id
    }

def approve_online_borrow_request(request_id):
    """Approve online borrow request"""
    online_request = OnlineBorrowRequest.query.get(request_id)
    
    if not online_request or online_request.status != 'pending':
        return {'success': False, 'message': 'Talep bulunamadı veya zaten işlenmiş'}
    
    # Kitap ve üye kontrolü
    book = Book.query.get(online_request.isbn)
    member = Member.query.get(online_request.member_id)
    
    if not book or not member:
        return {'success': False, 'message': 'Kitap veya üye bulunamadı'}
    
    # Ödünç alma işlemini gerçekleştir
    result = process_borrow_transaction(book, member, 'online', f'Online rezervasyon - ID: {online_request.id}')
    
    if result.status_code == 200:
        # Talebi onayla
        online_request.status = 'approved'
        online_request.approved_at = datetime.utcnow()
        online_request.approved_by = current_user.username
        db.session.commit()
        
        # Kullanıcıya onay e-postası gönder
        user = User.query.get(online_request.user_id)
        send_email(user.email, 'online_borrow_approved', {
            'member_name': user.username,
            'book_title': book.title,
            'pickup_date': online_request.pickup_date,
            'pickup_time': online_request.pickup_time,
            'due_date': (datetime.now() + timedelta(days=int(get_setting('max_borrow_days', '14')))).strftime('%Y-%m-%d'),
            'request_id': online_request.id
        })
        
        log_activity('approve_online_borrow', f'Online ödünç alma onaylandı: {book.title}')
        
        return {'success': True, 'message': 'Ödünç alma talebi onaylandı'}
    
    return result

def reject_online_borrow_request(request_id, reason):
    """Reject online borrow request"""
    online_request = OnlineBorrowRequest.query.get(request_id)
    
    if not online_request or online_request.status != 'pending':
        return {'success': False, 'message': 'Talep bulunamadı veya zaten işlenmiş'}
    
    # Talebi reddet
    online_request.status = 'rejected'
    online_request.rejection_reason = reason
    online_request.approved_at = datetime.utcnow()
    online_request.approved_by = current_user.username
    
    db.session.commit()
    
    # Kullanıcıya red e-postası gönder
    user = User.query.get(online_request.user_id)
    book = Book.query.get(online_request.isbn)
    send_email(user.email, 'online_borrow_rejected', {
        'member_name': user.username,
        'book_title': book.title,
        'reason': reason,
        'request_id': online_request.id
    })
    
    log_activity('reject_online_borrow', f'Online ödünç alma reddedildi: {book.title}')
    
    return {'success': True, 'message': 'Ödünç alma talebi reddedildi ve kullanıcı bilgilendirildi'}

# Statistics and Reporting Functions
def get_inventory_summary():
    """Get inventory summary statistics"""
    total_books = db.session.query(db.func.sum(Book.quantity)).scalar() or 0
    distinct_books = Book.query.count()
    borrowed_books = Transaction.query.filter_by(return_date=None).count()
    available_books = total_books - borrowed_books
    
    # Kategori dağılımı
    category_data = db.session.query(
        Category.name, db.func.count(BookCategory.book_isbn)
    ).join(BookCategory).group_by(Category.name).all()
    
    category_labels = [c[0] for c in category_data]
    category_counts = [c[1] for c in category_data]
    
    # Popüler kitaplar
    popular_books = db.session.query(
        Book.title, db.func.count(Transaction.id).label('borrow_count')
    ).join(Transaction).group_by(Book.isbn).order_by(db.text('borrow_count DESC')).limit(10).all()
    
    # Aktif üyeler
    active_members = db.session.query(
        Member.ad_soyad.label('name'), db.func.count(Transaction.id).label('borrow_count')
    ).join(Transaction).group_by(Member.id).order_by(db.text('borrow_count DESC')).limit(10).all()
    
    return {
        'summary': {
            'total_books': total_books,
            'distinct_books': distinct_books,
            'borrowed_books': borrowed_books,
            'available_books': available_books
        },
        'category_labels': category_labels,
        'category_counts': category_counts,
        'popular_books': [{'title': b.title, 'borrow_count': b.borrow_count} for b in popular_books],
        'active_members': [{'name': m.name, 'borrow_count': m.borrow_count} for m in active_members]
    }

def get_member_statistics():
    """Get member statistics"""
    total_members = Member.query.count()
    active_members = Member.query.filter(Member.current_borrowed > 0).count()
    penalized_members = Member.query.filter(Member.penalty_until != None, Member.penalty_until > datetime.now()).count()
    
    # En çok ödünç alan üyeler
    most_active = db.session.query(
        Member.ad_soyad.label('name'), db.func.count(Transaction.id).label('borrow_count')
    ).join(Transaction).group_by(Member.id).order_by(db.text('borrow_count DESC')).limit(10).all()
    
    # Cezalı üyeler
    penalized = Member.query.filter(Member.penalty_until != None, Member.penalty_until > datetime.now()).all()
    
    # En çok gecikme yapan üyeler
    most_overdue = db.session.query(
        Member.ad_soyad.label('name'), db.func.count(Transaction.id).label('overdue_count')
    ).join(Transaction).filter(
        Transaction.return_date == None,
        Transaction.due_date < datetime.now().strftime('%Y-%m-%d')
    ).group_by(Member.id).order_by(db.text('overdue_count DESC')).limit(10).all()
    
    return {
        'summary': {
            'total_members': total_members,
            'active_members': active_members,
            'penalized_members': penalized_members
        },
        'most_active': [{'name': m.name, 'borrow_count': m.borrow_count} for m in most_active],
        'penalized': [{'name': m.ad_soyad, 'penalty_until': str(m.penalty_until)} for m in penalized],
        'most_overdue': [{'name': m.name, 'overdue_count': m.overdue_count} for m in most_overdue]
    }

# Search and Book Functions
def quick_search_books(query, limit=10):
    """Quick book search for online and QR operations"""
    if not query:
        return {'success': False, 'message': 'Arama terimi gerekli'}
    
    # Kitap arama
    books = Book.query.filter(
        db.or_(
            Book.title.contains(query),
            Book.authors.contains(query),
            Book.isbn.contains(query),
            Book.barcode.contains(query)
        )
    ).limit(limit).all()
    
    books_data = []
    for book in books:
        # Mevcut durumu kontrol et
        borrowed_count = Transaction.query.filter_by(isbn=book.isbn, return_date=None).count()
        available = book.quantity > borrowed_count
        
        # Kapak yolunu normalize et
        image_url = normalize_cover_url(book.image_path)
        
        books_data.append({
            'isbn': book.isbn,
            'title': book.title,
            'authors': book.authors,
            'quantity': book.quantity,
            'available': available,
            'borrowed_count': borrowed_count,
            'shelf': book.shelf,
            'cupboard': book.cupboard,
            'image_path': image_url,
            'total_borrow_count': book.total_borrow_count,
            'average_rating': book.average_rating
        })
    
    return {
        'success': True,
        'books': books_data,
        'total': len(books_data)
    }

def quick_search_members(query, limit=10):
    """Quick member search for online and QR operations"""
    if not query:
        return {'success': False, 'message': 'Arama terimi gerekli'}
    
    # Üye arama
    members = Member.query.filter(
        db.or_(
            Member.ad_soyad.contains(query),
            Member.numara.contains(query),
            Member.email.contains(query),
            Member.phone.contains(query)
        )
    ).limit(limit).all()
    
    members_data = []
    for member in members:
        # Aktif ödünç alma sayısını hesapla
        active_borrows = Transaction.query.filter_by(member_id=member.id, return_date=None).count()
        
        # Ceza durumunu kontrol et
        has_penalty = member.penalty_until and datetime.now() < member.penalty_until
        
        members_data.append({
            'id': member.id,
            'ad_soyad': member.ad_soyad,
            'sinif': member.sinif,
            'numara': member.numara,
            'email': member.email,
            'phone': member.phone,
            'uye_turu': member.uye_turu,
            'active_borrows': active_borrows,
            'total_borrowed': member.total_borrowed,
            'reliability_score': member.reliability_score,
            'has_penalty': has_penalty,
            'penalty_until': member.penalty_until.strftime('%d.%m.%Y') if member.penalty_until else None,
            'join_date': member.join_date.strftime('%d.%m.%Y') if member.join_date else None
        })
    
    return {
        'success': True,
        'members': members_data,
        'total': len(members_data)
    }

def generate_shelf_map_pdf(books):
    """Raf haritası PDF'i oluştur - yazdırılabilir raf/dolap planı + QR kodlu etiketler"""
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.pdfgen import canvas
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from io import BytesIO
    import qrcode
    from datetime import datetime
    
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    width, height = landscape(A4)
    
    # Başlık
    c.setFont('Helvetica-Bold', 16)
    title_text = "CUMHURİYET ANADOLU LİSESİ KÜTÜPHANESİ - RAF HARİTASI"
    title_width = c.stringWidth(title_text, 'Helvetica-Bold', 16)
    c.drawString((width - title_width) / 2, height - 40, title_text)
    
    # Raf/dolap kombinasyonlarını grupla
    shelf_map = {}
    for book in books:
        if book.shelf and book.cupboard:
            key = f"{book.shelf}-{book.cupboard}"
            if key not in shelf_map:
                shelf_map[key] = []
            shelf_map[key].append(book)
    
    # Grid çizimi - 8x6 grid (landscape'de daha geniş)
    start_x, start_y = 40, height - 100
    cell_width, cell_height = 90, 80
    cols, rows = 8, 6
    
    y_pos = start_y
    shelf_keys = sorted(shelf_map.keys())
    
    for row in range(rows):
        x_pos = start_x
        for col in range(cols):
            idx = row * cols + col
            if idx < len(shelf_keys):
                key = shelf_keys[idx]
                shelf, cupboard = key.split('-')
                cell_books = shelf_map[key]
                
                # Hücre çerçevesi
                c.setStrokeColor(colors.black)
                c.setLineWidth(1)
                c.rect(x_pos, y_pos, cell_width, cell_height)
                
                # Raf/dolap etiketi
                c.setFont('Helvetica-Bold', 8)
                label_text = f"Raf {shelf} / Dolap {cupboard}"
                label_width = c.stringWidth(label_text, 'Helvetica-Bold', 8)
                c.drawString(x_pos + (cell_width - label_width) / 2, y_pos + cell_height - 15, label_text)
                
                # Kitap sayısı
                c.setFont('Helvetica', 7)
                count_text = f"{len(cell_books)} kitap"
                count_width = c.stringWidth(count_text, 'Helvetica', 7)
                c.drawString(x_pos + (cell_width - count_width) / 2, y_pos + cell_height - 28, count_text)
                
                # İlk 3 kitabın ismini listele
                c.setFont('Helvetica', 6)
                for i, book in enumerate(cell_books[:3]):
                    book_title = (book.title[:20] + '...') if len(book.title) > 20 else book.title
                    c.drawString(x_pos + 2, y_pos + cell_height - 40 - (i * 8), book_title)
                
                if len(cell_books) > 3:
                    c.drawString(x_pos + 2, y_pos + cell_height - 64, f"... ve {len(cell_books) - 3} kitap daha")
                
                # QR kod (raf/dolap için)
                try:
                    qr_data = f"RAF:{shelf}|DOLAP:{cupboard}"
                    # Küçük QR kod simülasyonu (sağ üst köşe)
                    qr_size = 20
                    c.setStrokeColor(colors.black)
                    c.setFillColor(colors.black)
                    c.rect(x_pos + cell_width - qr_size - 2, y_pos + cell_height - qr_size - 2, qr_size, qr_size, fill=1)
                    c.setFillColor(colors.white)
                    c.rect(x_pos + cell_width - qr_size, y_pos + cell_height - qr_size, qr_size - 4, qr_size - 4, fill=1)
                except:
                    pass  # QR kod oluşturulamazsa devam et
            
            x_pos += cell_width + 5
        y_pos -= cell_height + 5
    
    # Alt bilgi
    c.setFont('Helvetica', 8)
    info_text = f"Toplam {len(shelf_keys)} raf/dolap kombinasyonu • {len(books)} kitap • Oluşturma: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    c.drawString(40, 30, info_text)
    
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

def generate_label_templates_pdf(items, template_type="qr_labels"):
    """Etiket şablonları PDF'i oluştur - A4 3x10 QR/raf etiketleri (kenar payı ayarlı)"""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from io import BytesIO
    from datetime import datetime
    
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    # A4 3x10 grid ayarları (kenar payı ile)
    margin_top, margin_bottom = 15*mm, 15*mm
    margin_left, margin_right = 10*mm, 10*mm
    
    usable_width = width - margin_left - margin_right
    usable_height = height - margin_top - margin_bottom
    
    cols, rows = 3, 10
    cell_width = usable_width / cols
    cell_height = usable_height / rows
    
    items_per_page = cols * rows
    total_pages = (len(items) + items_per_page - 1) // items_per_page
    
    for page in range(total_pages):
        if page > 0:
            c.showPage()
        
        # Sayfa başlığı
        c.setFont('Helvetica-Bold', 10)
        title = f"Etiket Şablonu - Sayfa {page + 1}/{total_pages}"
        title_width = c.stringWidth(title, 'Helvetica-Bold', 10)
        c.drawString((width - title_width) / 2, height - 10*mm, title)
        
        start_idx = page * items_per_page
        end_idx = min(start_idx + items_per_page, len(items))
        page_items = items[start_idx:end_idx]
        
        for idx, item in enumerate(page_items):
            row = idx // cols
            col = idx % cols
            
            x = margin_left + col * cell_width
            y = height - margin_top - (row + 1) * cell_height
            
            # Hücre çerçevesi (kesik çizgi)
            c.setStrokeColor(colors.grey)
            c.setDash(2, 2)
            c.rect(x, y, cell_width, cell_height)
            c.setDash()  # Düz çizgiye dön
            
            if template_type == "qr_labels":
                # QR kod etiketi
                # QR kod simülasyonu (sol üst)
                qr_size = cell_width * 0.4
                c.setStrokeColor(colors.black)
                c.setFillColor(colors.black)
                c.rect(x + 2*mm, y + cell_height - qr_size - 2*mm, qr_size, qr_size, fill=1)
                c.setFillColor(colors.white)
                c.rect(x + 3*mm, y + cell_height - qr_size - 1*mm, qr_size - 2*mm, qr_size - 2*mm, fill=1)
                
                # Metin bilgileri
                c.setFont('Helvetica-Bold', 8)
                c.setFillColor(colors.black)
                title_text = (item.get('title', '')[:25] + '...') if len(item.get('title', '')) > 25 else item.get('title', '')
                c.drawString(x + 2*mm, y + cell_height - qr_size - 8*mm, title_text)
                
                c.setFont('Helvetica', 7)
                c.drawString(x + 2*mm, y + cell_height - qr_size - 12*mm, f"ISBN: {item.get('isbn', '')}")
                
                if item.get('shelf') and item.get('cupboard'):
                    c.drawString(x + 2*mm, y + cell_height - qr_size - 16*mm, f"Raf {item.get('shelf')} / Dolap {item.get('cupboard')}")
            
            elif template_type == "shelf_labels":
                # Raf etiketi
                c.setFont('Helvetica-Bold', 12)
                c.setFillColor(colors.black)
                shelf_text = f"RAF {item.get('shelf', '')}"
                shelf_width = c.stringWidth(shelf_text, 'Helvetica-Bold', 12)
                c.drawString(x + (cell_width - shelf_width) / 2, y + cell_height - 15*mm, shelf_text)
                
                c.setFont('Helvetica-Bold', 10)
                cupboard_text = f"DOLAP {item.get('cupboard', '')}"
                cupboard_width = c.stringWidth(cupboard_text, 'Helvetica-Bold', 10)
                c.drawString(x + (cell_width - cupboard_width) / 2, y + cell_height - 25*mm, cupboard_text)
                
                # QR kod simülasyonu (raf/dolap için)
                qr_size = cell_width * 0.3
                c.setStrokeColor(colors.black)
                c.setFillColor(colors.black)
                c.rect(x + (cell_width - qr_size) / 2, y + 5*mm, qr_size, qr_size, fill=1)
                c.setFillColor(colors.white)
                c.rect(x + (cell_width - qr_size) / 2 + 1*mm, y + 6*mm, qr_size - 2*mm, qr_size - 2*mm, fill=1)
    
    c.save()
    buffer.seek(0)
    return buffer

def fuzzy_match_books(books, threshold=0.8):
    """Çift kayıt tespiti için kitapları fuzzy eşleme ile kontrol et"""
    from difflib import SequenceMatcher
    import re
    
    duplicates = []
    processed = set()
    
    def normalize_text(text):
        """Metin normalizasyonu"""
        if not text:
            return ""
        # Türkçe karakterleri normalize et
        text = text.lower()
        text = re.sub(r'[^\w\s]', '', text)  # Özel karakterleri kaldır
        text = re.sub(r'\s+', ' ', text).strip()  # Fazla boşlukları temizle
        return text
    
    def similarity(a, b):
        """İki metin arasındaki benzerlik oranı"""
        return SequenceMatcher(None, normalize_text(a), normalize_text(b)).ratio()
    
    for i, book1 in enumerate(books):
        if book1.isbn in processed:
            continue
            
        potential_duplicates = []
        
        for j, book2 in enumerate(books):
            if i >= j or book2.isbn in processed:
                continue
            
            # ISBN kontrolü (farklı formatlarda olabilir)
            isbn1_clean = re.sub(r'[^0-9X]', '', book1.isbn or '')
            isbn2_clean = re.sub(r'[^0-9X]', '', book2.isbn or '')
            
            if isbn1_clean == isbn2_clean and isbn1_clean:
                potential_duplicates.append({
                    'book': book2,
                    'match_type': 'ISBN',
                    'similarity': 1.0,
                    'reason': 'Aynı ISBN numarası'
                })
                continue
            
            # Başlık benzerliği
            title_sim = similarity(book1.title, book2.title)
            
            # Yazar benzerliği
            author_sim = similarity(book1.authors, book2.authors)
            
            # Yayınevi benzerliği
            publisher_sim = similarity(book1.publishers, book2.publishers)
            
            # Genel benzerlik skoru (ağırlıklı ortalama)
            overall_sim = (title_sim * 0.5 + author_sim * 0.3 + publisher_sim * 0.2)
            
            if overall_sim >= threshold:
                match_reason = []
                if title_sim >= 0.9:
                    match_reason.append(f'Başlık benzerliği: %{title_sim*100:.0f}')
                if author_sim >= 0.9:
                    match_reason.append(f'Yazar benzerliği: %{author_sim*100:.0f}')
                if publisher_sim >= 0.9:
                    match_reason.append(f'Yayınevi benzerliği: %{publisher_sim*100:.0f}')
                
                potential_duplicates.append({
                    'book': book2,
                    'match_type': 'Fuzzy',
                    'similarity': overall_sim,
                    'reason': ' | '.join(match_reason) or f'Genel benzerlik: %{overall_sim*100:.0f}'
                })
        
        if potential_duplicates:
            duplicates.append({
                'main_book': book1,
                'duplicates': potential_duplicates
            })
            
            # İşlenmiş olarak işaretle
            processed.add(book1.isbn)
            for dup in potential_duplicates:
                processed.add(dup['book'].isbn)
    
    return duplicates

def fuzzy_match_members(members, threshold=0.85):
    """Çift kayıt tespiti için üyeleri fuzzy eşleme ile kontrol et"""
    from difflib import SequenceMatcher
    import re
    
    duplicates = []
    processed = set()
    
    def normalize_name(name):
        """İsim normalizasyonu"""
        if not name:
            return ""
        # Türkçe karakterleri normalize et
        name = name.lower()
        name = re.sub(r'[^\w\s]', '', name)  # Özel karakterleri kaldır
        name = re.sub(r'\s+', ' ', name).strip()  # Fazla boşlukları temizle
        return name
    
    def similarity(a, b):
        """İki metin arasındaki benzerlik oranı"""
        return SequenceMatcher(None, normalize_name(a), normalize_name(b)).ratio()
    
    for i, member1 in enumerate(members):
        if member1.id in processed:
            continue
            
        potential_duplicates = []
        
        for j, member2 in enumerate(members):
            if i >= j or member2.id in processed:
                continue
            
            # Numara kontrolü
            if (member1.numara and member2.numara and 
                member1.numara == member2.numara):
                potential_duplicates.append({
                    'member': member2,
                    'match_type': 'Numara',
                    'similarity': 1.0,
                    'reason': 'Aynı öğrenci numarası'
                })
                continue
            
            # Email kontrolü
            if (member1.email and member2.email and 
                member1.email.lower() == member2.email.lower()):
                potential_duplicates.append({
                    'member': member2,
                    'match_type': 'Email',
                    'similarity': 1.0,
                    'reason': 'Aynı email adresi'
                })
                continue
            
            # İsim benzerliği
            name_sim = similarity(member1.ad_soyad, member2.ad_soyad)
            
            # Sınıf benzerliği
            class_match = (member1.sinif == member2.sinif) if (member1.sinif and member2.sinif) else 0
            
            # Telefon benzerliği
            phone_sim = 0
            if member1.phone and member2.phone:
                phone1_clean = re.sub(r'[^0-9]', '', member1.phone)
                phone2_clean = re.sub(r'[^0-9]', '', member2.phone)
                if phone1_clean and phone2_clean:
                    phone_sim = 1.0 if phone1_clean == phone2_clean else 0
            
            # Genel benzerlik skoru
            overall_sim = (name_sim * 0.6 + class_match * 0.2 + phone_sim * 0.2)
            
            if overall_sim >= threshold:
                match_reason = []
                if name_sim >= 0.9:
                    match_reason.append(f'İsim benzerliği: %{name_sim*100:.0f}')
                if class_match:
                    match_reason.append('Aynı sınıf')
                if phone_sim == 1.0:
                    match_reason.append('Aynı telefon')
                
                potential_duplicates.append({
                    'member': member2,
                    'match_type': 'Fuzzy',
                    'similarity': overall_sim,
                    'reason': ' | '.join(match_reason) or f'Genel benzerlik: %{overall_sim*100:.0f}'
                })
        
        if potential_duplicates:
            duplicates.append({
                'main_member': member1,
                'duplicates': potential_duplicates
            })
            
            # İşlenmiş olarak işaretle
            processed.add(member1.id)
            for dup in potential_duplicates:
                processed.add(dup['member'].id)
    
    return duplicates

def merge_duplicate_books(main_isbn, duplicate_isbn):
    """İki kitap kaydını birleştir"""
    try:
        from models import Book, Transaction
        
        main_book = Book.query.get(main_isbn)
        duplicate_book = Book.query.get(duplicate_isbn)
        
        if not main_book or not duplicate_book:
            return {'success': False, 'message': 'Kitap bulunamadı'}
        
        # Duplicate kitabın işlemlerini main kitaba aktar
        transactions = Transaction.query.filter_by(isbn=duplicate_isbn).all()
        for transaction in transactions:
            transaction.isbn = main_isbn
        
        # Duplicate kitabın bilgilerini main kitaba ekle (eksik olanları)
        if not main_book.authors and duplicate_book.authors:
            main_book.authors = duplicate_book.authors
        
        if not main_book.publishers and duplicate_book.publishers:
            main_book.publishers = duplicate_book.publishers
        
        if not main_book.category and duplicate_book.category:
            main_book.category = duplicate_book.category
        
        if not main_book.image_path and duplicate_book.image_path:
            main_book.image_path = duplicate_book.image_path
        
        # Adet sayısını birleştir
        main_book.quantity = (main_book.quantity or 0) + (duplicate_book.quantity or 0)
        
        # Duplicate kitabı sil
        db.session.delete(duplicate_book)
        db.session.commit()
        
        return {
            'success': True, 
            'message': f'Kitaplar başarıyla birleştirildi. Ana kitap: {main_book.title}'
        }
        
    except Exception as e:
        db.session.rollback()
        return {'success': False, 'message': f'Birleştirme hatası: {str(e)}'}

def merge_duplicate_members(main_id, duplicate_id):
    """İki üye kaydını birleştir"""
    try:
        from models import Member, Transaction
        
        main_member = Member.query.get(main_id)
        duplicate_member = Member.query.get(duplicate_id)
        
        if not main_member or not duplicate_member:
            return {'success': False, 'message': 'Üye bulunamadı'}
        
        # Duplicate üyenin işlemlerini main üyeye aktar
        transactions = Transaction.query.filter_by(member_id=duplicate_id).all()
        for transaction in transactions:
            transaction.member_id = main_id
        
        # Duplicate üyenin bilgilerini main üyeye ekle (eksik olanları)
        if not main_member.email and duplicate_member.email:
            main_member.email = duplicate_member.email
        
        if not main_member.phone and duplicate_member.phone:
            main_member.phone = duplicate_member.phone
        
        if not main_member.sinif and duplicate_member.sinif:
            main_member.sinif = duplicate_member.sinif
        
        # İstatistikleri birleştir
        main_member.total_borrowed = (main_member.total_borrowed or 0) + (duplicate_member.total_borrowed or 0)
        
        # Duplicate üyeyi sil
        db.session.delete(duplicate_member)
        db.session.commit()
        
        return {
            'success': True, 
            'message': f'Üyeler başarıyla birleştirildi. Ana üye: {main_member.ad_soyad}'
        }
        
    except Exception as e:
        db.session.rollback()
        return {'success': False, 'message': f'Birleştirme hatası: {str(e)}'}

# Performance Optimization - Caching and Pre-computation
import functools
import time

# Simple in-memory cache
_cache = {}
_cache_timestamps = {}

def cache_with_ttl(ttl_seconds=300):  # 5 dakika default TTL
    """TTL (Time To Live) ile cache decorator"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Cache key oluştur
            cache_key = f"{func.__name__}:{str(args)}:{str(sorted(kwargs.items()))}"
            
            # Cache kontrol et
            current_time = time.time()
            if (cache_key in _cache and 
                cache_key in _cache_timestamps and
                current_time - _cache_timestamps[cache_key] < ttl_seconds):
                return _cache[cache_key]
            
            # Cache miss - fonksiyonu çalıştır
            result = func(*args, **kwargs)
            
            # Cache'e kaydet
            _cache[cache_key] = result
            _cache_timestamps[cache_key] = current_time
            
            return result
        return wrapper
    return decorator

def clear_cache(pattern=None):
    """Cache'i temizle"""
    global _cache, _cache_timestamps
    
    if pattern:
        # Pattern ile eşleşen cache'leri temizle
        keys_to_remove = [key for key in _cache.keys() if pattern in key]
        for key in keys_to_remove:
            _cache.pop(key, None)
            _cache_timestamps.pop(key, None)
    else:
        # Tüm cache'i temizle
        _cache.clear()
        _cache_timestamps.clear()

@cache_with_ttl(600)  # 10 dakika cache
def get_popular_books_cached(limit=10):
    """Popüler kitapları cache'li olarak getir"""
    from models import Book, Transaction
    
    popular_books = db.session.query(
        Book.isbn,
        Book.title,
        Book.authors,
        Book.image_path,
        db.func.count(Transaction.id).label('borrow_count')
    ).join(Transaction, Book.isbn == Transaction.isbn)\
     .group_by(Book.isbn, Book.title, Book.authors, Book.image_path)\
     .order_by(db.text('borrow_count DESC'))\
     .limit(limit).all()
    
    return [{
        'isbn': book.isbn,
        'title': book.title,
        'authors': book.authors,
        'image_path': book.image_path,
        'borrow_count': book.borrow_count
    } for book in popular_books]

@cache_with_ttl(300)  # 5 dakika cache
def get_dashboard_stats_cached():
    """Dashboard istatistiklerini cache'li olarak getir"""
    from models import Book, Member, Transaction
    from datetime import datetime, timedelta
    
    # Temel istatistikler
    total_books = Book.query.count()
    total_members = Member.query.count()
    active_transactions = Transaction.query.filter_by(return_date=None).count()
    
    # Bu ayın işlemleri
    current_month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_transactions = Transaction.query.filter(
        Transaction.borrow_date >= current_month_start.strftime('%Y-%m-%d')
    ).count()
    
    # Geciken kitaplar
    today = datetime.now().strftime('%Y-%m-%d')
    overdue_books = Transaction.query.filter(
        Transaction.return_date == None,
        Transaction.due_date < today
    ).count()
    
    return {
        'total_books': total_books,
        'total_members': total_members,
        'active_transactions': active_transactions,
        'monthly_transactions': monthly_transactions,
        'overdue_books': overdue_books
    }

def precompute_reports():
    """Popüler raporları ön-hesapla"""
    try:
        from datetime import datetime
        
        # Dashboard stats'ı ön-hesapla
        get_dashboard_stats_cached()
        
        # Popüler kitapları ön-hesapla
        get_popular_books_cached()
        
        print(f"✅ Raporlar ön-hesaplandı: {datetime.now()}")
        
    except Exception as e:
        print(f"❌ Ön-hesaplama hatası: {str(e)}")

def invalidate_related_cache(operation_type, **kwargs):
    """İlgili cache'leri geçersiz kıl"""
    if operation_type in ['book_added', 'book_updated', 'book_deleted']:
        clear_cache('get_popular_books_cached')
        clear_cache('get_dashboard_stats_cached')
    
    elif operation_type in ['member_added', 'member_updated', 'member_deleted']:
        clear_cache('get_dashboard_stats_cached')
    
    elif operation_type in ['transaction_created', 'transaction_updated']:
        clear_cache('get_popular_books_cached')
        clear_cache('get_dashboard_stats_cached')
    
    elif operation_type == 'cache_clear_all':
        clear_cache()
