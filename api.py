from flask import request, jsonify, send_file
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
import tempfile
import os
import json
import secrets
import pandas as pd  # Excel işlemleri için gerekli
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
import qrcode

from config import app, get_setting
from models import db, User, Book, Member, Transaction, Category, BookCategory, Notification, SearchHistory, Review, Reservation, Fine, ActivityLog, Settings, EmailTemplate, OnlineBorrowRequest, QRCode
from utils import (log_activity, fetch_book_info_from_api, calculate_fine, 
                   send_email, add_notification, generate_qr_code, save_qr_code,
                   normalize_cover_url, download_cover_image,
                   normalize_text_tr, compute_relevance_score)
from routes import role_required

# Books API
@app.route('/api/books')
def api_get_books():
    """API endpoint to get all books"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '')
    category_filter = request.args.get('category', '')
    category_id = request.args.get('category_id', type=int)
    
    query = Book.query
    
    if search:
        query = query.filter(
            db.or_(
                Book.isbn.contains(search),
                Book.title.contains(search),
                Book.authors.contains(search),
                Book.category.contains(search)
            )
        )
    
    if category_id:
        # Kategori ID ile filtreleme (ilişki tablosu üzerinden)
        query = query.join(BookCategory, Book.isbn == BookCategory.book_isbn).filter(BookCategory.category_id == category_id)
    elif category_filter:
        # Eski alanla (tekil string) filtreleme geriye uyumluluk için
        query = query.filter(Book.category.contains(category_filter))
    
    books = query.paginate(page=page, per_page=per_page, error_out=False)
    
    books_data = []
    for book in books.items:
        borrowed_count = Transaction.query.filter_by(isbn=book.isbn, return_date=None).count()
        available = book.quantity - borrowed_count
        
        # Kapak yolunu normalize et
        image_url = normalize_cover_url(book.image_path)
        
        # Get categories (çoklu)
        categories = db.session.query(Category.name).join(BookCategory)\
            .filter(BookCategory.book_isbn == book.isbn).all()
        category_names = [cat[0] for cat in categories]
        
        books_data.append({
            'isbn': book.isbn,
            'title': book.title,
            'authors': book.authors,
            'publish_date': book.publish_date,
            'number_of_pages': book.number_of_pages,
            'publishers': book.publishers,
            'languages': book.languages,
            'quantity': book.quantity,
            'borrowed': borrowed_count,
            'available': available,
            'shelf': book.shelf,
            'cupboard': book.cupboard,
            'category': book.category,
            'categories': ', '.join(category_names),
            'image_path': image_url
        })
    
    return jsonify({
        'books': books_data,
        'total': books.total,
        'pages': books.pages,
        'current_page': page
    })

@app.route('/api/books/fetch', methods=['POST'])
def api_fetch_books():
    """Fetch book information from Open Library API"""
    isbns = request.json.get('isbns', [])
    results = []
    
    for isbn in isbns:
        book_info = fetch_book_info_from_api(isbn)
        if book_info:
            results.append(book_info)
        else:
            results.append({
                'isbn': isbn,
                'title': 'Bilgi Bulunamadı',
                'authors': 'Bilgi Bulunamadı',
                'error': True
            })
    
    return jsonify({'books': results})

@app.route('/api/books/fetch-bulk', methods=['POST'])
def api_fetch_books_bulk():
    """Bulk fetch book information for Excel auto-complete feature"""
    import time
    start_time = time.time()
    
    isbns = request.json.get('isbns', [])
    if not isbns:
        return jsonify({'success': False, 'message': 'ISBN listesi gerekli'}), 400
    
    if len(isbns) > 50:
        return jsonify({'success': False, 'message': 'Maksimum 50 ISBN işlenebilir'}), 400
    
    results = []
    success_count = 0
    error_count = 0
    
    for isbn in isbns:
        try:
            # ISBN'i temizle
            clean_isbn = str(isbn).strip().replace('-', '').replace(' ', '')
            
            if len(clean_isbn) < 10:
                results.append({
                    'isbn': isbn,
                    'title': 'Geçersiz ISBN',
                    'authors': 'Geçersiz ISBN',
                    'error': True
                })
                error_count += 1
                continue
            
            # API'den bilgi çek
            book_info = fetch_book_info_from_api(clean_isbn)
            if book_info:
                # Başarılı sonuç
                result = {
                    'isbn': clean_isbn,
                    'title': book_info.get('title', ''),
                    'authors': book_info.get('authors', ''),
                    'publishers': book_info.get('publishers', ''),
                    'publish_date': book_info.get('publish_date', ''),
                    'number_of_pages': book_info.get('number_of_pages', 0),
                    'languages': book_info.get('languages', 'Türkçe'),
                    'image_url': book_info.get('image_url', ''),
                    'description': book_info.get('description', ''),
                    'error': False
                }
                results.append(result)
                success_count += 1
            else:
                # Bilgi bulunamadı
                results.append({
                    'isbn': clean_isbn,
                    'title': 'Bilgi Bulunamadı',
                    'authors': 'Bilgi Bulunamadı',
                    'error': True
                })
                error_count += 1
                
        except Exception as e:
            results.append({
                'isbn': isbn,
                'title': f'Hata: {str(e)}',
                'authors': 'API Hatası',
                'error': True
            })
            error_count += 1
    
    end_time = time.time()
    processing_time = round(end_time - start_time, 2)
    
    return jsonify({
        'success': True,
        'books': results,
        'stats': {
            'total_processed': len(isbns),
            'successful': success_count,
            'failed': error_count,
            'processing_time_seconds': processing_time
        },
        'message': f'{success_count} kitap bilgisi bulundu, {error_count} hata'
    })

@app.route('/api/books/import-bulk', methods=['POST'])
def api_import_books_bulk():
    """Import auto-completed books directly to database"""
    import time
    from urllib.parse import urlparse
    import requests
    
    start_time = time.time()
    
    books_data = request.json.get('books', [])
    if not books_data:
        return jsonify({'success': False, 'message': 'Kitap verisi gerekli'}), 400
    
    if len(books_data) > 200:
        return jsonify({'success': False, 'message': 'Maksimum 200 kitap işlenebilir'}), 400
    
    success_count = 0
    updated_count = 0 
    error_count = 0
    errors = []
    
    try:
        for book_data in books_data:
            try:
                isbn = str(book_data.get('isbn', '')).strip()
                if not isbn or len(isbn) < 10:
                    error_count += 1
                    errors.append(f'Geçersiz ISBN: {isbn}')
                    continue
                
                # Kitap zaten mevcut mu?
                existing_book = Book.query.get(isbn)
                
                if existing_book:
                    # Güncelle
                    existing_book.title = book_data.get('title', existing_book.title)
                    existing_book.authors = book_data.get('authors', existing_book.authors)
                    existing_book.publishers = book_data.get('publishers', existing_book.publishers)
                    existing_book.publish_date = str(book_data.get('publish_date', existing_book.publish_date))
                    existing_book.languages = book_data.get('languages', existing_book.languages or 'Türkçe')
                    existing_book.description = book_data.get('description', existing_book.description)
                    
                    # Sayısal değerler
                    try:
                        existing_book.number_of_pages = int(book_data.get('number_of_pages', existing_book.number_of_pages or 0))
                    except:
                        pass
                    
                    # Resim URL'si varsa kaydet
                    image_url = book_data.get('image_url')
                    if image_url and not existing_book.image_path:
                        try:
                            downloaded = download_cover_image(image_url, isbn)
                            if downloaded:
                                existing_book.image_path = downloaded
                        except Exception as img_error:
                            print(f"Resim indirme hatası {isbn}: {img_error}")
                    
                    updated_count += 1
                else:
                    # Yeni kitap ekle
                    book = Book(
                        isbn=isbn,
                        title=book_data.get('title', ''),
                        authors=book_data.get('authors', ''),
                        publishers=book_data.get('publishers', ''),
                        publish_date=str(book_data.get('publish_date', '')),
                        languages=book_data.get('languages', 'Türkçe'),
                        description=book_data.get('description', ''),
                        quantity=1,  # Varsayılan miktar
                        shelf='',    # Boş raf
                        cupboard=''  # Boş dolap
                    )
                    
                    # Sayısal değerler
                    try:
                        book.number_of_pages = int(book_data.get('number_of_pages', 0))
                    except:
                        book.number_of_pages = 0
                    
                    # Resim URL'si varsa kaydet
                    image_url = book_data.get('image_url')
                    if image_url:
                        try:
                            downloaded = download_cover_image(image_url, isbn)
                            if downloaded:
                                book.image_path = downloaded
                        except Exception as img_error:
                            print(f"Resim indirme hatası {isbn}: {img_error}")
                    
                    db.session.add(book)
                    success_count += 1
                    
            except Exception as e:
                error_count += 1
                errors.append(f'Kitap işleme hatası: {str(e)}')
                continue
        
        # Değişiklikleri kaydet
        db.session.commit()
        
        end_time = time.time()
        processing_time = round(end_time - start_time, 2)
        
        message = f'{success_count} yeni kitap eklendi, {updated_count} kitap güncellendi'
        if error_count > 0:
            message += f', {error_count} hata'
        
        return jsonify({
            'success': True,
            'message': message,
            'stats': {
                'added': success_count,
                'updated': updated_count,
                'errors': error_count,
                'processing_time_seconds': processing_time
            },
            'errors': errors[:10]  # İlk 10 hatayı döndür
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Veritabanı hatası: {str(e)}'
        }), 500

@app.route('/api/books/download-missing-covers', methods=['POST'])
def api_download_missing_covers():
    """Download missing book covers for existing books"""
    import requests
    from utils import fetch_book_info_from_api
    
    # Only process books without covers
    books_without_covers = Book.query.filter(
        db.or_(Book.image_path.is_(None), Book.image_path == '')
    ).all()
    
    if not books_without_covers:
        return jsonify({
            'success': True,
            'message': 'Tüm kitaplarda kapak resmi mevcut',
            'processed': 0
        })
    
    # Limit to prevent overload
    limit = min(len(books_without_covers), 20)
    books_to_process = books_without_covers[:limit]
    
    success_count = 0
    errors = []
    
    for book in books_to_process:
        try:
            # Get book info with image URL
            book_info = fetch_book_info_from_api(book.isbn)
            
            if book_info and book_info.get('image_url'):
                image_url = book_info['image_url']
                
                # Download image
                downloaded = download_cover_image(image_url, book.isbn)
                if downloaded:
                    book.image_path = downloaded
                    success_count += 1
                
        except Exception as e:
            errors.append(f"{book.isbn}: {str(e)}")
            continue
    
    # Save changes
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Veritabanı güncelleme hatası: {str(e)}'
        }), 500
    
    return jsonify({
        'success': True,
        'message': f'{success_count} kitap için kapak resmi indirildi',
        'processed': len(books_to_process),
        'successful': success_count,
        'errors': len(errors),
        'error_details': errors[:5]  # İlk 5 hatayı göster
    })

@app.route('/api/books/add', methods=['POST'])
def api_add_book():
    """Add a new book to the database (eksik alanlara toleranslı)"""
    from sqlalchemy.exc import IntegrityError
    data = request.json or {}

    try:
        isbn = (data.get('isbn') or '').strip()
        if not isbn:
            return jsonify({'success': False, 'message': 'ISBN gerekli'}), 400

        # Mevcutsa güncelleme gibi davran (eksik alanlar korunur)
        existing = Book.query.get(isbn)
        if existing:
            # Adet sayısını artır
            old_quantity = existing.quantity or 1
            new_quantity = old_quantity + (int(data.get('quantity') or 1))
            existing.quantity = new_quantity
            
            # Diğer alanları güncelle (eğer boşsa)
            if not existing.title and data.get('title'):
                existing.title = data.get('title')
            if not existing.authors and data.get('authors'):
                existing.authors = data.get('authors')
            if not existing.publish_date and data.get('publish_date'):
                existing.publish_date = data.get('publish_date')
            try:
                if not existing.number_of_pages:
                    existing.number_of_pages = int(data.get('number_of_pages', 0))
            except Exception:
                pass
            if not existing.publishers and data.get('publishers'):
                existing.publishers = data.get('publishers')
            if not existing.languages and data.get('languages'):
                existing.languages = data.get('languages')
            if not existing.shelf and data.get('shelf'):
                existing.shelf = data.get('shelf')
            if not existing.cupboard and data.get('cupboard'):
                existing.cupboard = data.get('cupboard')
            if not existing.category and data.get('category'):
                existing.category = data.get('category')
            # image_url verilmişse indirmeyi dene ve filename olarak kaydet
            if data.get('image_url') and not existing.image_path:
                try:
                    downloaded = download_cover_image(data.get('image_url'), isbn)
                    if downloaded:
                        existing.image_path = downloaded
                except Exception as e:
                    print(f"Kapak indirme hatası (güncelleme): {e}")
            
            db.session.commit()
            return jsonify({
                'success': True,
                'message': 'Kitap zaten mevcut, adet güncellendi',
                'warning': f"ISBN {isbn} zaten kayıtlı. Eski adet: {old_quantity}, Yeni adet: {new_quantity}"
            })

        # Yeni kayıt
        book = Book(
            isbn=isbn,
            title=data.get('title', ''),
            authors=data.get('authors', ''),
            publish_date=data.get('publish_date', ''),
            number_of_pages=int(data.get('number_of_pages') or 0),
            publishers=data.get('publishers', ''),
            languages=data.get('languages', ''),
            quantity=int(data.get('quantity') or 1),
            shelf=data.get('shelf', ''),
            cupboard=data.get('cupboard', ''),
            image_path='',  # Başlangıçta boş, sonra download edilecek
            category=data.get('category', '')
        )
        
        # Eğer image_url verilmişse indirmeyi dene ve filename olarak kaydet
        try:
            if data.get('image_url'):
                downloaded = download_cover_image(data.get('image_url'), isbn)
                if downloaded:
                    book.image_path = downloaded
        except Exception as e:
            print(f"Kapak indirme hatası (yeni kitap): {e}")
        
        db.session.add(book)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Kitap başarıyla eklendi'})
        
    except IntegrityError as e:
        db.session.rollback()
        if 'UNIQUE constraint' in str(e) or 'isbn' in str(e.orig).lower():
            return jsonify({
                'success': False,
                'message': f'UNIQUE constraint failed: Bu ISBN ({isbn}) zaten kayıtlı',
                'error': 'Duplicate ISBN'
            }), 400
        return jsonify({'success': False, 'message': f'Veritabanı kısıtlama hatası: {str(e)}'}), 400
    except Exception as e:
        db.session.rollback()
        print(f"Kitap ekleme hatası: {e}")
        return jsonify({'success': False, 'message': str(e)}), 400

@app.route('/api/books/<isbn>/upload-cover', methods=['POST'])
def api_upload_book_cover(isbn):
    """Manuel kapak yükleme. Form-Data: field name 'cover'"""
    book = Book.query.get(isbn)
    if not book:
        return jsonify({'success': False, 'message': 'Kitap bulunamadı'}), 404

    if 'cover' not in request.files:
        return jsonify({'success': False, 'message': 'Kapak dosyası gerekli (cover)'}), 400

    file = request.files['cover']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'Dosya seçilmedi'}), 400

    try:
        filename = secure_filename(f"{isbn}.jpg")
        save_dir = os.path.join(app.root_path, 'static', 'book_covers')
        os.makedirs(save_dir, exist_ok=True)
        save_path = os.path.join(save_dir, filename)
        file.save(save_path)

        book.image_path = filename
        db.session.commit()

        return jsonify({'success': True, 'message': 'Kapak resmi yüklendi', 'image_path': f'/static/book_covers/{filename}'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Yükleme hatası: {str(e)}'}), 500

@app.route('/api/books/<isbn>', methods=['PUT'])
def api_update_book(isbn):
    """Update book information"""
    book = Book.query.get_or_404(isbn)
    data = request.json
    
    book.title = data.get('title', book.title)
    book.authors = data.get('authors', book.authors)
    book.publish_date = data.get('publish_date', book.publish_date)
    book.number_of_pages = data.get('number_of_pages', book.number_of_pages)
    book.publishers = data.get('publishers', book.publishers)
    book.languages = data.get('languages', book.languages)
    book.quantity = data.get('quantity', book.quantity)
    book.shelf = data.get('shelf', book.shelf)
    book.cupboard = data.get('cupboard', book.cupboard)
    book.category = data.get('category', book.category)
    
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Kitap güncellendi'})

@app.route('/api/books/<isbn>', methods=['GET'])
def api_get_book(isbn):
    """Get single book information"""
    book = Book.query.get_or_404(isbn)
    
    return jsonify({
        'isbn': book.isbn,
        'title': book.title,
        'authors': book.authors,
        'publish_date': book.publish_date,
        'number_of_pages': book.number_of_pages,
        'publishers': book.publishers,
        'languages': book.languages,
        'quantity': book.quantity,
        'shelf': book.shelf,
        'cupboard': book.cupboard,
        'image_path': normalize_cover_url(book.image_path)
    })

@app.route('/api/books/<isbn>', methods=['DELETE'])
def api_delete_book(isbn):
    """Delete a book"""
    book = Book.query.get_or_404(isbn)
    
    # Check if book is borrowed
    if Transaction.query.filter_by(isbn=isbn, return_date=None).first():
        return jsonify({'success': False, 'message': 'Ödünç verilmiş kitap silinemez'}), 400
    
    # Delete related records
    BookCategory.query.filter_by(book_isbn=isbn).delete()
    Transaction.query.filter_by(isbn=isbn).delete()
    Notification.query.filter_by(related_isbn=isbn).delete()
    
    db.session.delete(book)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Kitap silindi'})

@app.route('/api/books/<isbn>/review', methods=['POST'])
# Authentication removed for EXE compatibility
def add_review(isbn):
    """Add or update book review"""
    book = Book.query.get_or_404(isbn)
    
    rating = request.json.get('rating')
    comment = request.json.get('comment', '')
    
    if not rating or rating < 1 or rating > 5:
        return jsonify({'success': False, 'message': 'Geçersiz puan'}), 400
    
    # Use default user_id for EXE compatibility
    user_id = 1  # Default user ID for EXE
    
    # Check if user already reviewed
    review = Review.query.filter_by(isbn=isbn, user_id=user_id).first()
    
    if review:
        # Update existing review
        review.rating = rating
        review.comment = comment
        review.updated_at = datetime.utcnow()
    else:
        # Create new review
        review = Review(
            isbn=isbn,
            user_id=user_id,
            rating=rating,
            comment=comment
        )
        db.session.add(review)
        book.review_count += 1
    
    # Update book average rating
    all_reviews = Review.query.filter_by(isbn=isbn).all()
    total_rating = sum(r.rating for r in all_reviews)
    book.average_rating = total_rating / len(all_reviews) if all_reviews else 0
    
    db.session.commit()
    
    log_activity('add_review', f'Reviewed book: {book.title} ({rating} stars)')
    
    return jsonify({'success': True, 'message': 'Değerlendirmeniz kaydedildi'})

@app.route('/api/books/<isbn>/reserve', methods=['POST'])
# Authentication removed for EXE compatibility
def reserve_book(isbn):
    """Reserve a book"""
    book = Book.query.get_or_404(isbn)
    
    # Check if book is available
    borrowed_count = Transaction.query.filter_by(isbn=isbn, return_date=None).count()
    if book.quantity > borrowed_count:
        return jsonify({'success': False, 'message': 'Kitap zaten mevcut, direkt ödünç alabilirsiniz'}), 400
    
    # Use default user_id for EXE compatibility
    user_id = 1  # Default user ID for EXE
    
    # Check if user already has an active reservation
    existing = Reservation.query.filter_by(
        isbn=isbn, user_id=user_id, status='active'
    ).first()
    
    if existing:
        return jsonify({'success': False, 'message': 'Bu kitap için zaten rezervasyonunuz var'}), 400
    
    # Get first member for EXE compatibility
    member = Member.query.first()
    if not member:
        return jsonify({'success': False, 'message': 'Üye kaydınız bulunamadı'}), 404
    
    # Calculate queue position
    last_reservation = Reservation.query.filter_by(isbn=isbn, status='active')\
        .order_by(Reservation.queue_position.desc()).first()
    queue_position = (last_reservation.queue_position + 1) if last_reservation else 1
    
    # Create reservation
    reservation = Reservation(
        isbn=isbn,
        user_id=user_id,
        member_id=member.id,
        queue_position=queue_position,
        expiry_date=datetime.utcnow() + timedelta(days=int(get_setting('reservation_expiry_days', '3')))
    )
    db.session.add(reservation)
    db.session.commit()
    
    # Skip email for EXE compatibility
    # send_email(current_user.email, 'reservation_confirmation', {
    #     'member_name': current_user.username,
    #     'book_title': book.title,
    #     'queue_position': queue_position
    # })
    
    log_activity('reserve_book', f'Reserved book: {book.title}')
    
    return jsonify({
        'success': True,
        'message': f'Rezervasyonunuz alındı. Sıranız: {queue_position}'
    })

@app.route('/api/books/<isbn>/availability')
def api_book_availability(isbn):
    """Check book availability"""
    book = Book.query.get_or_404(isbn)
    borrowed_count = Transaction.query.filter_by(isbn=isbn, return_date=None).count()
    available_count = book.quantity - borrowed_count
    
    return jsonify({
        'available': available_count > 0,
        'title': book.title,
        'total_count': book.quantity,
        'available_count': available_count,
        'borrowed_count': borrowed_count
    })

@app.route('/api/books/<isbn>/categories', methods=['GET', 'POST'])
def api_book_categories(isbn):
    """Get or update book categories"""
    if request.method == 'GET':
        categories = db.session.query(Category).join(BookCategory)\
            .filter(BookCategory.book_isbn == isbn).all()
        
        categories_data = []
        for cat in categories:
            categories_data.append({
                'id': cat.id,
                'name': cat.name
            })
        
        return jsonify({'categories': categories_data})
    
    else:  # POST
        # Delete existing categories
        BookCategory.query.filter_by(book_isbn=isbn).delete()
        
        # Add new categories
        category_ids = request.json.get('category_ids', [])
        for cat_id in category_ids:
            book_cat = BookCategory(book_isbn=isbn, category_id=cat_id)
            db.session.add(book_cat)
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Kategoriler güncellendi'})

@app.route('/api/books/<isbn>/details')
def api_get_book_details(isbn):
    """Kitap detaylarını döndür"""
    try:
        book = Book.query.get(isbn)
        if not book:
            return jsonify({'success': False, 'message': 'Kitap bulunamadı'})
        
        # Get category name
        category = db.session.query(Category).join(BookCategory, Category.id == BookCategory.category_id)\
            .filter(BookCategory.book_isbn == isbn).first()
        category_name = category.name if category else 'Genel'
        
        # Kapak yolunu normalize et
        image_url = normalize_cover_url(book.image_path)
        
        return jsonify({
            'success': True,
            'book': {
                'isbn': book.isbn,
                'title': book.title,
                'authors': book.authors,
                'image_path': image_url,
                'quantity': book.quantity,
                'borrowed_count': book.total_borrow_count,
                'category_name': category_name,
                'description': book.description,
                'publishers': book.publishers,
                'publish_date': book.publish_date
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# Members API
@app.route('/api/members')
def api_get_members():
    """API endpoint to get all members"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '')
    
    query = Member.query
    
    if search:
        query = query.filter(
            db.or_(
                Member.ad_soyad.contains(search),
                Member.numara.contains(search),
                Member.uye_turu.contains(search)
            )
        )
    
    members = query.paginate(page=page, per_page=per_page, error_out=False)
    
    members_data = []
    for member in members.items:
        members_data.append({
            'id': member.id,
            'ad_soyad': member.ad_soyad,
            'sinif': member.sinif,
            'numara': member.numara,
            'email': member.email,
            'phone': member.phone,
            'uye_turu': member.uye_turu
        })
    
    return jsonify({
        'members': members_data,
        'total': members.total,
        'pages': members.pages,
        'current_page': page
    })

@app.route('/api/members', methods=['POST'])
def api_add_member():
    """Add a new member (eksik alanlara toleranslı)"""
    data = request.json or {}

    try:
        member = Member(
            ad_soyad=data.get('ad_soyad', ''),
            sinif=data.get('sinif', ''),
            numara=data.get('numara', ''),
            email=data.get('email', ''),
            phone=data.get('phone', ''),
            address=data.get('address', ''),
            uye_turu=data.get('uye_turu', 'Öğrenci')
        )
        db.session.add(member)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Üye başarıyla eklendi'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400

@app.route('/api/members/<int:id>', methods=['PUT'])
def api_update_member(id):
    """Update member information (eksik alanlara toleranslı)"""
    member = Member.query.get_or_404(id)
    data = request.json or {}

    member.ad_soyad = data.get('ad_soyad', member.ad_soyad)
    member.sinif = data.get('sinif', member.sinif)
    member.numara = data.get('numara', member.numara)
    member.email = data.get('email', member.email)
    member.phone = data.get('phone', member.phone)
    member.address = data.get('address', member.address)
    member.uye_turu = data.get('uye_turu', member.uye_turu)

    db.session.commit()

    return jsonify({'success': True, 'message': 'Üye güncellendi'})

@app.route('/api/members/<int:id>', methods=['DELETE'])
def api_delete_member(id):
    """Delete a member"""
    member = Member.query.get_or_404(id)
    
    # Check if member has unreturned books
    if Transaction.query.filter_by(member_id=id, return_date=None).first():
        return jsonify({'success': False, 'message': 'İade edilmemiş kitabı olan üye silinemez'}), 400
    
    db.session.delete(member)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Üye silindi'})

@app.route('/api/members/by-school-no/<school_no>')
def api_member_by_school_no(school_no):
    """Get member information by school number"""
    member = Member.query.filter_by(numara=school_no).first()
    if member:
        return jsonify({
            'success': True,
            'member': {
                'id': member.id,
                'ad_soyad': member.ad_soyad,
                'sinif': member.sinif,
                'numara': member.numara,
                'email': member.email,
                'uye_turu': member.uye_turu
            }
        })
    return jsonify({'success': False, 'message': 'Member not found'}), 404

@app.route('/api/members/<int:id>')
def api_get_member(id):
    """Get member details"""
    member = Member.query.get_or_404(id)
    
    return jsonify({
        'id': member.id,
        'ad_soyad': member.ad_soyad,
        'sinif': member.sinif,
        'numara': member.numara,
        'email': member.email,
        'uye_turu': member.uye_turu,
        'phone': member.phone,
        'address': member.address,
        'join_date': member.join_date.isoformat() if member.join_date else None,
        'total_borrowed': member.total_borrowed,
        'current_borrowed': member.current_borrowed,
        'reliability_score': member.reliability_score
    })

@app.route('/api/members/<int:id>/borrows')
def api_member_borrows(id):
    """Get member's active borrows"""
    borrows = db.session.query(Transaction, Book)\
        .join(Book, Transaction.isbn == Book.isbn)\
        .filter(Transaction.member_id == id, Transaction.return_date == None)\
        .all()
    
    borrows_data = []
    for trans, book in borrows:
        borrows_data.append({
            'id': trans.id,
            'isbn': trans.isbn,
            'book_title': book.title,
            'borrow_date': trans.borrow_date,
            'due_date': trans.due_date
        })
    
    return jsonify({'borrows': borrows_data})

@app.route('/api/members/<int:member_id>/details')
def api_member_details(member_id):
    """Üye detaylarını getir - online ve QR kod işlemleri için"""
    member = Member.query.get(member_id)
    if not member:
        return jsonify({'success': False, 'message': 'Üye bulunamadı'}), 404
    
    # Aktif ödünç alınan kitaplar
    active_transactions = db.session.query(Transaction, Book)\
        .join(Book, Transaction.isbn == Book.isbn)\
        .filter(Transaction.member_id == member_id, Transaction.return_date == None)\
        .all()
    
    active_books = []
    for transaction, book in active_transactions:
        due_date = datetime.strptime(transaction.due_date, '%Y-%m-%d')
        days_remaining = (due_date.date() - datetime.now().date()).days
        is_overdue = days_remaining < 0
        
        active_books.append({
            'transaction_id': transaction.id,
            'isbn': book.isbn,
            'title': book.title,
            'authors': book.authors,
            'borrow_date': transaction.borrow_date,
            'due_date': transaction.due_date,
            'days_remaining': days_remaining,
            'is_overdue': is_overdue,
            'fine_amount': abs(days_remaining) * float(get_setting('daily_fine_amount', '1.0')) if is_overdue else 0
        })
    
    # Son işlemler
    recent_transactions = db.session.query(Transaction, Book)\
        .join(Book, Transaction.isbn == Book.isbn)\
        .filter(Transaction.member_id == member_id)\
        .order_by(Transaction.borrow_date.desc())\
        .limit(10).all()
    
    recent_activity = []
    for transaction, book in recent_transactions:
        recent_activity.append({
            'book_title': book.title,
            'borrow_date': transaction.borrow_date,
            'return_date': transaction.return_date,
            'status': 'Aktif' if not transaction.return_date else 'İade edildi'
        })
    
    # Ceza durumu
    has_penalty = member.penalty_until and datetime.now() < member.penalty_until
    
    return jsonify({
        'success': True,
        'member': {
            'id': member.id,
            'ad_soyad': member.ad_soyad,
            'sinif': member.sinif,
            'numara': member.numara,
            'email': member.email,
            'phone': member.phone,
            'uye_turu': member.uye_turu,
            'address': member.address,
            'join_date': member.join_date.strftime('%d.%m.%Y') if member.join_date else None,
            'total_borrowed': member.total_borrowed,
            'current_borrowed': member.current_borrowed,
            'reliability_score': member.reliability_score,
            'has_penalty': has_penalty,
            'penalty_until': member.penalty_until.strftime('%d.%m.%Y') if member.penalty_until else None
        },
        'active_books': active_books,
        'recent_activity': recent_activity
    })

# Transactions API
@app.route('/api/transactions')
def api_get_transactions():
    """API endpoint to get all transactions - ARAMA DESTEKLİ"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status', 'all')  # all, active, returned
    search = request.args.get('search', '').strip()  # Arama terimi
    
    query = db.session.query(Transaction, Book, Member)\
        .join(Book, Transaction.isbn == Book.isbn)\
        .join(Member, Transaction.member_id == Member.id)
    
    # Durum filtresi
    if status == 'active':
        query = query.filter(Transaction.return_date == None)
    elif status == 'returned':
        query = query.filter(Transaction.return_date != None)
    
    # Arama filtresi
    if search:
        search_filter = db.or_(
            Book.title.contains(search),
            Book.isbn.contains(search),
            Member.ad_soyad.contains(search),
            Member.numara.contains(search)
        )
        query = query.filter(search_filter)
    
    transactions = query.order_by(Transaction.id.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    max_renew = int(get_setting('max_renew_count', '2'))
    transactions_data = []
    for trans, book, member in transactions.items:
        can_renew = (trans.return_date is None and trans.renew_count < max_renew)
        # Gecikme hesabı: hem 'YYYY-MM-DD' hem de 'YYYY-MM-DD HH:MM:SS' destekle
        is_overdue = False
        try:
            if trans.return_date is None and trans.due_date:
                due_dt = None
                try:
                    due_dt = datetime.strptime(trans.due_date, '%Y-%m-%d %H:%M:%S')
                except Exception:
                    try:
                        due_dt = datetime.strptime(trans.due_date, '%Y-%m-%d')
                    except Exception:
                        due_dt = None
                if due_dt:
                    is_overdue = due_dt.date() < datetime.now().date()
        except Exception:
            is_overdue = False
        transactions_data.append({
            'id': trans.id,
            'isbn': trans.isbn,
            'book_title': book.title,
            'member_id': trans.member_id,
            'member_name': member.ad_soyad,
            'borrow_date': trans.borrow_date,
            'due_date': trans.due_date,
            'return_date': trans.return_date,
            'is_overdue': is_overdue,
            'can_renew': can_renew
        })
    
    return jsonify({
        'transactions': transactions_data,
        'total': transactions.total,
        'pages': transactions.pages,
        'current_page': page
    })

@app.route('/api/transactions/borrow', methods=['POST'])
def api_borrow_book():
    """Borrow a book"""
    data = request.json
    isbn = data.get('isbn')
    school_no = data.get('school_no')
    due_date = data.get('due_date')
    
    # Find member by school number
    member = Member.query.filter_by(numara=school_no).first()
    if not member:
        return jsonify({'success': False, 'message': 'Üye bulunamadı'}), 404
    
    # Ceza kontrolü
    now = datetime.now()
    if member.penalty_until:
        try:
            penalty_dt = member.penalty_until
            if isinstance(penalty_dt, str):
                penalty_dt = datetime.fromisoformat(penalty_dt)
        except:
            penalty_dt = now
        if penalty_dt and now < penalty_dt:
            return jsonify({'success': False, 'message': f"Bu üye {penalty_dt.strftime('%d.%m.%Y')} tarihine kadar ödünç alamaz (cezalı)."}), 403
    
    # Check book availability
    book = Book.query.get(isbn)
    if not book:
        return jsonify({'success': False, 'message': 'Kitap bulunamadı'}), 404
    
    borrowed_count = Transaction.query.filter_by(isbn=isbn, return_date=None).count()
    if book.quantity <= borrowed_count:
        return jsonify({'success': False, 'message': 'Kitap mevcut değil'}), 400
    
    # Create transaction (saat/dakika ile kaydet) ve due_date boşsa hesapla
    if not due_date:
        loan_days = int(get_setting('max_borrow_days', '14'))
        computed_due = datetime.now() + timedelta(days=loan_days)
        due_date_final = computed_due.strftime('%Y-%m-%d %H:%M:%S')
    else:
        due_date_final = due_date if len(due_date) > 10 else f"{due_date} 23:59:59"

    transaction = Transaction(
        isbn=isbn,
        member_id=member.id,
        borrow_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        due_date=due_date_final
    )
    
    # Update book statistics
    book.last_borrowed_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    book.total_borrow_count += 1
    
    db.session.add(transaction)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Kitap ödünç verildi'})

@app.route('/api/transactions/return', methods=['POST'])
def api_return_book():
    """Return a book"""
    data = request.json
    isbn = data.get('isbn')
    school_no = data.get('school_no')
    
    # Find member
    member = Member.query.filter_by(numara=school_no).first()
    if not member:
        return jsonify({'success': False, 'message': 'Üye bulunamadı'}), 404
    
    # Find active transaction
    transaction = Transaction.query.filter_by(
        isbn=isbn,
        member_id=member.id,
        return_date=None
    ).first()
    
    if not transaction:
        return jsonify({'success': False, 'message': 'Aktif ödünç işlemi bulunamadı'}), 404
    
    # Update transaction - saat/dakika ile
    transaction.return_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # İade sonrası kitap/üye istatistiklerini güncelle (güvenli)
    try:
        book = Book.query.get(transaction.isbn)
        member = Member.query.get(transaction.member_id)
        if member and (member.current_borrowed or 0) > 0:
            member.current_borrowed -= 1
        # book.status güncellemesi utils.process_return_transaction içinde de yapılıyor; burada tekrar etmiyoruz
    except Exception:
        pass
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Kitap iade alındı'})

@app.route('/api/transactions/overdue')
def api_get_overdue():
    """Get overdue transactions"""
    overdue = db.session.query(Transaction, Book, Member)\
        .join(Book, Transaction.isbn == Book.isbn)\
        .join(Member, Transaction.member_id == Member.id)\
        .filter(Transaction.return_date == None)\
        .filter(Transaction.due_date < datetime.now().strftime("%Y-%m-%d"))\
        .order_by(Transaction.due_date).all()
    
    overdue_data = []
    for trans, book, member in overdue:
        overdue_data.append({
            'id': trans.id,
            'isbn': trans.isbn,
            'book_title': book.title,
            'member_name': member.ad_soyad,
            'due_date': trans.due_date,
            'days_overdue': (datetime.now() - datetime.strptime(trans.due_date, "%Y-%m-%d")).days
        })
    
    return jsonify({'overdue': overdue_data})

@app.route('/api/transactions/<int:id>/renew', methods=['POST'])
# Authentication removed for EXE compatibility
def api_renew_transaction(id):
    """Renew a book loan"""
    transaction = Transaction.query.get_or_404(id)
    
    # Skip permission check for EXE compatibility
    has_permission = True
    
    # Check if already returned
    if transaction.return_date:
        return jsonify({'success': False, 'message': 'Bu kitap zaten iade edilmiş'}), 400
    
    # Check renew limit
    max_renew = int(get_setting('max_renew_count', '2'))
    if transaction.renew_count >= max_renew:
        return jsonify({'success': False, 'message': 'Maksimum yenileme sayısına ulaştınız'}), 400
    
    # Extend due date by original loan period
    loan_days = int(get_setting('max_borrow_days', '14'))
    # due_date hem tarih hem tarih-saat formatında olabilir
    try:
        current_due = datetime.strptime(transaction.due_date, '%Y-%m-%d %H:%M:%S')
    except Exception:
        current_due = datetime.strptime(transaction.due_date, '%Y-%m-%d')
    new_due = current_due + timedelta(days=loan_days)
    
    transaction.due_date = new_due.strftime('%Y-%m-%d %H:%M:%S')
    transaction.renew_count += 1
    
    db.session.commit()
    
    log_activity('renew_book', f'Renewed loan for transaction {id}')
    
    return jsonify({
        'success': True,
        'message': f'Süre {loan_days} gün uzatıldı. Yeni teslim tarihi: {transaction.due_date}'
    })

@app.route('/api/transactions/<int:id>/quick-return', methods=['POST'])
# Authentication removed for EXE compatibility
def api_quick_return(id):
    """Quick return a book"""
    transaction = Transaction.query.get_or_404(id)
    if transaction.return_date:
        return jsonify({'success': False, 'message': 'Kitap zaten iade edilmiş'}), 400
    
    transaction.return_date = datetime.now().strftime('%Y-%m-%d')
    
    # Calculate fine if overdue
    fine_amount = calculate_fine(transaction.due_date, transaction.return_date)
    if fine_amount > 0:
        transaction.fine_amount = fine_amount
        # Ceza uygula: 1 ay kitap alamama
        member = Member.query.get(transaction.member_id)
        if member:
            now = datetime.now()
            penalty_until = now + timedelta(days=30)
            if not member.penalty_until or (member.penalty_until and now > member.penalty_until):
                member.penalty_until = penalty_until
            else:
                # Ceza üstüne ekle
                member.penalty_until += timedelta(days=30)
        
        # Create fine record
        fine = Fine(
            user_id=current_user.id,
            member_id=transaction.member_id,
            transaction_id=transaction.id,
            amount=fine_amount,
            reason='late_return'
        )
        db.session.add(fine)
    
    db.session.commit()
    log_activity('quick_return', f'Quick returned book - Transaction ID: {id}')
    
    return jsonify({'success': True, 'message': 'Kitap iade alındı'})

@app.route('/api/transactions/stats')
def api_transaction_stats():
    """Get transaction statistics"""
    today = datetime.now().strftime('%Y-%m-%d')
    
    active = Transaction.query.filter_by(return_date=None).count()
    today_due = Transaction.query.filter(
        Transaction.return_date == None,
        Transaction.due_date == today
    ).count()
    overdue = Transaction.query.filter(
        Transaction.return_date == None,
        Transaction.due_date < today
    ).count()
    today_transactions = Transaction.query.filter(
        db.or_(
            Transaction.borrow_date == today,
            Transaction.return_date == today
        )
    ).count()
    
    return jsonify({
        'active': active,
        'today_due': today_due,
        'overdue': overdue,
        'today_transactions': today_transactions
    })

@app.route('/api/transactions/check')
def api_check_transaction():
    """Check transaction by ISBN and school number"""
    isbn = request.args.get('isbn')
    school_no = request.args.get('school_no')
    
    member = Member.query.filter_by(numara=school_no).first()
    if not member:
        return jsonify({'error': 'Member not found'}), 404
    
    transaction = Transaction.query.filter_by(
        isbn=isbn,
        member_id=member.id,
        return_date=None
    ).first()
    
    if not transaction:
        return jsonify({'error': 'Transaction not found'}), 404
    
    due_date = datetime.strptime(transaction.due_date, '%Y-%m-%d')
    today = datetime.now()
    days_overdue = max(0, (today - due_date).days)
    
    return jsonify({
        'transaction': {
            'id': transaction.id,
            'borrow_date': transaction.borrow_date,
            'due_date': transaction.due_date,
            'days_overdue': days_overdue
        }
    })

@app.route('/api/transactions/<int:id>', methods=['DELETE'])
# Authentication removed for EXE compatibility
def api_delete_transaction(id):
    """Admin - Delete single transaction"""
    try:
        transaction = Transaction.query.get_or_404(id)
        
        # Get info before deleting for logging
        book = Book.query.get(transaction.isbn)
        member = Member.query.get(transaction.member_id)
        
        book_title = book.title if book else f"ISBN: {transaction.isbn}"
        member_name = member.ad_soyad if member else f"ID: {transaction.member_id}"
        
        db.session.delete(transaction)
        db.session.commit()
        
        log_activity('delete_transaction', f'İşlem silindi: {book_title} - {member_name}')
        
        return jsonify({'success': True, 'message': 'İşlem başarıyla silindi'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Silme hatası: {str(e)}'}), 500

@app.route('/api/transactions/bulk-delete', methods=['POST'])
# Authentication removed for EXE compatibility
def api_bulk_delete_transactions():
    """Admin - Delete multiple transactions"""
    try:
        data = request.json
        transaction_ids = data.get('transaction_ids', [])
        
        if not transaction_ids:
            return jsonify({'success': False, 'message': 'Silinecek işlem seçilmedi'}), 400
        
        if len(transaction_ids) > 100:
            return jsonify({'success': False, 'message': 'Maksimum 100 işlem silinebilir'}), 400
        
        # Get transactions info for logging
        transactions = Transaction.query.filter(Transaction.id.in_(transaction_ids)).all()
        
        if not transactions:
            return jsonify({'success': False, 'message': 'Silinecek işlem bulunamadı'}), 404
        
        deleted_info = []
        for trans in transactions:
            book = Book.query.get(trans.isbn)
            member = Member.query.get(trans.member_id)
            book_title = book.title if book else f"ISBN: {trans.isbn}"
            member_name = member.ad_soyad if member else f"ID: {trans.member_id}"
            deleted_info.append(f"{book_title} - {member_name}")
        
        # Delete transactions
        deleted_count = Transaction.query.filter(Transaction.id.in_(transaction_ids)).delete(synchronize_session=False)
        db.session.commit()
        
        log_activity('bulk_delete_transactions', f'{deleted_count} işlem toplu silindi: {", ".join(deleted_info[:5])}{"..." if len(deleted_info) > 5 else ""}')
        
        return jsonify({
            'success': True, 
            'message': f'{deleted_count} işlem başarıyla silindi',
            'deleted_count': deleted_count
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Toplu silme hatası: {str(e)}'}), 500

@app.route('/api/transactions/delete-all-returned', methods=['POST'])
# Authentication removed for EXE compatibility
def api_delete_all_returned_transactions():
    """Admin - Delete all returned transactions"""
    try:
        confirm = request.json.get('confirm', False)
        if not confirm:
            return jsonify({'success': False, 'message': 'İşlem onaylanmadı'}), 400
        
        # Count returned transactions
        returned_count = Transaction.query.filter(Transaction.return_date.isnot(None)).count()
        
        if returned_count == 0:
            return jsonify({'success': False, 'message': 'İade edilmiş işlem bulunamadı'})
        
        # Delete all returned transactions
        Transaction.query.filter(Transaction.return_date.isnot(None)).delete()
        db.session.commit()
        
        log_activity('delete_all_returned', f'{returned_count} iade edilmiş işlem silindi')
        
        return jsonify({
            'success': True,
            'message': f'{returned_count} iade edilmiş işlem silindi',
            'deleted_count': returned_count
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Silme hatası: {str(e)}'}), 500

# Categories API - removed duplicate function

# Other API endpoints continue here...
# Export/Import APIs
@app.route('/api/export/books', methods=['GET'])
def api_export_books():
    """Export books to Excel"""
    books = Book.query.all()
    
    data = []
    for book in books:
        data.append({
            'ISBN': book.isbn,
            'Başlık': book.title,
            'Yazar': book.authors,
            'Yayın Yılı': book.publish_date,
            'Sayfa Sayısı': book.number_of_pages,
            'Yayınevi': book.publishers,
            'Diller': book.languages,
            'Adet': book.quantity,
            'Raf': book.shelf,
            'Dolap': book.cupboard,
            'Kategori': book.category
        })
    
    df = pd.DataFrame(data)
    
    # Create temporary file
    temp = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
    df.to_excel(temp.name, index=False)
    temp.close()
    
    return send_file(temp.name, as_attachment=True, download_name='kitaplar.xlsx')

@app.route('/api/import/books', methods=['POST'])
def api_import_books():
    """Import books from Excel - BULK OPTİMİZE EDİLMİŞ"""
    import time
    start_time = time.time()
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Dosya bulunamadı'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'Dosya seçilmedi'}), 400
    
    if not file or not file.filename.endswith(('.xlsx', '.xls')):
        return jsonify({'success': False, 'message': 'Geçersiz dosya formatı'}), 400
    
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    try:
        df = pd.read_excel(filepath)
        total_rows = len(df)
        
        # Sütun eşleme
        column_mappings = {
            'isbn': ['ISBN', 'isbn', 'Isbn', 'kitap_no', 'book_id'],
            'title': ['Başlık', 'title', 'Title', 'baslik', 'kitap_adi'],
            'authors': ['Yazar', 'authors', 'Authors', 'author', 'yazar'],
            'publish_date': ['Yayın Yılı', 'publish_date', 'yayin_yili', 'year'],
            'number_of_pages': ['Sayfa Sayısı', 'pages', 'sayfa', 'page_count'],
            'publishers': ['Yayınevi', 'publishers', 'publisher', 'yayinevi'],
            'languages': ['Diller', 'languages', 'language', 'dil'],
            'quantity': ['Adet', 'quantity', 'miktar', 'count'],
            'shelf': ['Raf', 'shelf', 'raf_no'],
            'cupboard': ['Dolap', 'cupboard', 'dolap_no'],
            'category': ['Kategori', 'category', 'kategori', 'tur']
        }
        
        # Sütun eşlemesi yap
        mapped_columns = {}
        for system_col, possible_names in column_mappings.items():
            for col_name in df.columns:
                if col_name.strip() in possible_names:
                    mapped_columns[system_col] = col_name
                    break
        
        # En az ISBN ve Başlık olmalı
        if 'isbn' not in mapped_columns or 'title' not in mapped_columns:
            missing = [col for col in ['isbn', 'title'] if col not in mapped_columns]
            return jsonify({
                'success': False,
                'message': f'Gerekli sütunlar bulunamadı: {", ".join(missing)}\\nBulunan sütunlar: {", ".join(df.columns)}'
            }), 400
        
        # BULK PROCESSING
        BATCH_SIZE = 200
        COMMIT_FREQUENCY = 50
        
        stats = {
            'added_count': 0,
            'updated_count': 0,
            'error_count': 0,
            'skipped_count': 0
        }
        
        # Mevcut ISBN'leri çek
        existing_isbns = {isbn[0] for isbn in db.session.query(Book.isbn).all()}
        
        batch_books = []
        errors = []
        
        for batch_start in range(0, total_rows, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, total_rows)
            
            for index in range(batch_start, batch_end):
                row = df.iloc[index]
                
                try:
                    isbn = str(row.get(mapped_columns['isbn'], '')).strip()
                    title = str(row.get(mapped_columns.get('title'), '')).strip()
                    
                    if not isbn or not title:
                        stats['skipped_count'] += 1
                        continue
                    
                    # Kitap mevcut mu kontrol et
                    if isbn in existing_isbns:
                        # Güncelle
                        book = Book.query.get(isbn)
                        stats['updated_count'] += 1
                    else:
                        # Yeni ekle
                        book = Book(isbn=isbn)
                        existing_isbns.add(isbn)
                        stats['added_count'] += 1
                    
                    # Verileri ata
                    book.title = title
                    book.authors = str(row.get(mapped_columns.get('authors', ''), '')).strip()
                    book.publish_date = str(row.get(mapped_columns.get('publish_date', ''), ''))
                    
                    # Sayısal değerler
                    try:
                        book.number_of_pages = int(row.get(mapped_columns.get('number_of_pages', ''), 0) or 0)
                        book.quantity = int(row.get(mapped_columns.get('quantity', ''), 1) or 1)
                    except:
                        book.number_of_pages = 0
                        book.quantity = 1
                    
                    book.publishers = str(row.get(mapped_columns.get('publishers', ''), '')).strip()
                    book.languages = str(row.get(mapped_columns.get('languages', ''), '')).strip()
                    book.shelf = str(row.get(mapped_columns.get('shelf', ''), '')).strip()
                    book.cupboard = str(row.get(mapped_columns.get('cupboard', ''), '')).strip()
                    book.category = str(row.get(mapped_columns.get('category', ''), '')).strip()
                    
                    batch_books.append(book)
                    
                    # Belirli aralıklarla commit
                    if len(batch_books) >= COMMIT_FREQUENCY:
                        db.session.add_all(batch_books)
                        db.session.commit()
                        batch_books = []
                        
                except Exception as e:
                    stats['error_count'] += 1
                    if len(errors) < 20:
                        errors.append(f"Satır {index+2}: {str(e)}")
        
        # Kalan kayıtları commit et
        if batch_books:
            db.session.add_all(batch_books)
            db.session.commit()
        
        os.remove(filepath)
        
        # Performans metrikleri
        processing_time = time.time() - start_time
        total_processed = stats['added_count'] + stats['updated_count']
        records_per_second = int(total_processed / processing_time) if processing_time > 0 else 0
        
        message = f"🚀 {stats['added_count']} kitap eklendi, {stats['updated_count']} güncellendi"
        message += f"\\n⚡ İşlem süresi: {processing_time:.2f}s ({records_per_second} kayıt/saniye)"
        
        if stats['skipped_count'] > 0:
            message += f"\\n📋 {stats['skipped_count']} satır atlandı"
        if stats['error_count'] > 0:
            message += f"\\n❌ {stats['error_count']} satırda hata"
        
        result = {
            'success': True,
            'message': message,
            'details': {
                'stats': stats,
                'mapped_columns': mapped_columns,
                'processing_time': processing_time,
                'records_per_second': records_per_second,
                'errors': errors
            }
        }
        
        return jsonify(result)
        
    except Exception as e:
        try:
            os.remove(filepath)
        except:
            pass
        return jsonify({'success': False, 'message': f'Excel işleme hatası: {str(e)}'}), 400

# Category Management APIs
@app.route('/api/categories', methods=['GET'])
def api_get_categories():
    """Get all categories"""
    categories = Category.query.all()
    return jsonify({
        'categories': [{'id': c.id, 'name': c.name, 'description': c.description} for c in categories]
    })

@app.route('/api/categories', methods=['POST'])
def api_add_category():
    """Add new category"""
    data = request.json
    try:
        category = Category(name=data['name'], description=data.get('description', ''))
        db.session.add(category)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Kategori eklendi'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400

@app.route('/api/categories/<int:category_id>', methods=['DELETE'])
def api_delete_category(category_id):
    """Delete category"""
    category = Category.query.get_or_404(category_id)
    db.session.delete(category)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Kategori silindi'})

# Profile and User APIs
@app.route('/profile/update', methods=['POST'])
# Authentication removed for EXE compatibility
def update_profile():
    """Update user profile"""
    data = request.json
    
    # Use first user for EXE compatibility
    user = User.query.first()
    if not user:
        return jsonify({'success': False, 'message': 'Kullanıcı bulunamadı'}), 404
    
    # Update user info
    if 'email' in data:
        # Check if email already exists
        existing = User.query.filter(
            User.email == data['email'],
            User.id != user.id
        ).first()
        if existing:
            return jsonify({'success': False, 'message': 'Bu e-posta adresi zaten kullanılıyor'}), 400
        user.email = data['email']
    
    if 'theme' in data:
        user.theme = data['theme']
    
    if 'language' in data:
        user.language = data['language']
    
    # Update member info if exists
    member = Member.query.first()
    if member:
        if 'phone' in data:
            member.phone = data['phone']
        if 'address' in data:
            member.address = data['address']
    
    db.session.commit()
    
    log_activity('update_profile', 'Profile updated')
    
    return jsonify({'success': True, 'message': 'Profiliniz güncellendi'})

@app.route('/api/user/theme', methods=['POST'])
# Authentication removed for EXE compatibility
def api_update_theme():
    """Update user theme preference"""
    theme = request.form.get('theme', 'light')
    if theme not in ['light', 'dark']:
        theme = 'light'
    
    # Use first user for EXE compatibility
    user = User.query.first()
    if user:
        user.theme = theme
        db.session.commit()
    
    return jsonify({'success': True})

# Advanced Search API
@app.route('/api/search/advanced', methods=['POST'])
def api_advanced_search():
    """Advanced book search"""
    criteria = request.json or {}
    
    query = Book.query
    
    # Eşleşme türleri: title_match_type: exact|startswith|contains
    title_match_type = (criteria.get('title_match_type') or 'contains').lower()
    author_match_type = (criteria.get('author_match_type') or 'contains').lower()
    
    def apply_match(column, value, match_type='contains'):
        if not value:
            return None
        if match_type == 'exact':
            return column == value
        if match_type == 'startswith':
            return column.like(f"{value}%")
        return column.contains(value)
    
    if criteria.get('title'):
        cond = apply_match(Book.title, criteria['title'], title_match_type)
        if cond is not None:
            query = query.filter(cond)
    if criteria.get('author'):
        cond = apply_match(Book.authors, criteria['author'], author_match_type)
        if cond is not None:
            query = query.filter(cond)
    if criteria.get('publisher'):
        query = query.filter(Book.publishers.contains(criteria['publisher']))
    if criteria.get('languages'):
        query = query.filter(Book.languages.contains(criteria['languages']))
    if criteria.get('isbn'):
        query = query.filter(Book.isbn.contains(criteria['isbn']))
    if criteria.get('description'):
        query = query.filter(Book.description.contains(criteria['description']))
    if criteria.get('barcode'):
        query = query.filter(Book.barcode.contains(criteria['barcode']))
    if criteria.get('edition'):
        query = query.filter(Book.edition.contains(criteria['edition']))
    if criteria.get('pages_min'):
        try:
            query = query.filter(Book.number_of_pages >= int(criteria['pages_min']))
        except Exception:
            pass
    if criteria.get('pages_max'):
        try:
            query = query.filter(Book.number_of_pages <= int(criteria['pages_max']))
        except Exception:
            pass
    if criteria.get('quantity_min'):
        try:
            query = query.filter(Book.quantity >= int(criteria['quantity_min']))
        except Exception:
            pass
    if criteria.get('quantity_max'):
        try:
            query = query.filter(Book.quantity <= int(criteria['quantity_max']))
        except Exception:
            pass
    if criteria.get('shelf'):
        query = query.filter(Book.shelf.contains(criteria['shelf']))
    if criteria.get('cupboard'):
        query = query.filter(Book.cupboard.contains(criteria['cupboard']))
    if criteria.get('year_from'):
        query = query.filter(Book.publish_date >= str(criteria['year_from']))
    if criteria.get('year_to'):
        query = query.filter(Book.publish_date <= str(criteria['year_to']))
    
    # Çoklu kategori ID desteği
    category_ids = criteria.get('category_ids') or []
    if isinstance(category_ids, list) and len(category_ids) > 0:
        query = query.join(BookCategory).filter(BookCategory.category_id.in_(category_ids))
    elif criteria.get('category'):
        # Geriye uyumluluk: isim ile arama
        query = query.join(BookCategory).join(Category).filter(Category.name == criteria['category'])

    # Sadece mevcut kitaplar
    available_only = criteria.get('available_only') is True
    
    # Ön sıralama (hafif)
    sort_by = criteria.get('sort_by', 'title')
    sort_dir = criteria.get('sort_dir', 'desc')
    sort_map = {
        'title': Book.title,
        'authors': Book.authors,
        'publish_date': Book.publish_date,
        'quantity': Book.quantity,
        'total_borrow_count': Book.total_borrow_count,
        'average_rating': Book.average_rating
    }
    order_col = sort_map.get(sort_by, Book.title)
    if sort_dir == 'asc':
        query = query.order_by(order_col.asc())
    else:
        query = query.order_by(order_col.desc())

    books = query.limit(400).all()
    
    # Save search to history
    search_term = json.dumps(criteria, ensure_ascii=False)
    search_history = SearchHistory(
        search_term=search_term,
        search_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        result_count=len(books)
    )
    db.session.add(search_history)
    db.session.commit()
    
    # Alaka puanı ile sıralama
    scored = []
    q_title = criteria.get('title') or criteria.get('q') or ''
    for book in books:
        borrowed_count = Transaction.query.filter_by(isbn=book.isbn, return_date=None).count()
        available = (book.quantity or 0) - borrowed_count
        if available_only and available <= 0:
            continue
        relevance = compute_relevance_score(q_title or '', book.title, book.authors, book.publishers)
        # ISBN tam eşleşme ek puan
        if criteria.get('isbn') and str(book.isbn).strip() == str(criteria['isbn']).strip():
            relevance += 150
        scored.append((relevance, {
            'isbn': book.isbn,
            'title': book.title,
            'authors': book.authors,
            'publish_date': book.publish_date,
            'publishers': book.publishers,
            'quantity': book.quantity,
            'available': available
        }))
    scored.sort(key=lambda x: x[0], reverse=True)
    books_data = [item for _, item in scored[:200]]
    
    return jsonify({'books': books_data})

# Smart Search API (canlı öneriler)
@app.route('/api/search/smart', methods=['POST'])
def api_search_smart():
    try:
        data = request.get_json(force=True) or {}
        query_text = (data.get('query') or '').strip()
        include_ai = bool(data.get('include_ai_suggestions', False))
        max_results = int(data.get('max_results') or 10)

        if len(query_text) < 2:
            return jsonify({'suggestions': [], 'ai_suggestions': []})

        suggestions = []

        # Book suggestions
        books = Book.query.filter(
            db.or_(
                Book.title.ilike(f"%{query_text}%"),
                Book.authors.ilike(f"%{query_text}%"),
                Book.isbn.contains(query_text)
            )
        ).limit(max_results).all()

        # Optional: category name lookup per book
        for book in books:
            borrowed_count = Transaction.query.filter_by(isbn=book.isbn, return_date=None).count()
            available = (book.quantity or 0) - borrowed_count
            # Try to resolve a category name if possible
            category_name = book.category
            try:
                category_obj = db.session.query(Category).join(BookCategory, Category.id == BookCategory.category_id) \
                    .filter(BookCategory.book_isbn == book.isbn).first()
                if category_obj:
                    category_name = category_obj.name
            except Exception:
                pass

            suggestions.append({
                'type': 'book',
                'title': book.title,
                'authors': book.authors,
                'isbn': book.isbn,
                'available': available > 0,
                'category': category_name
            })

        # Author suggestions (grouped by authors field)
        try:
            author_rows = db.session.query(Book.authors.label('name'), db.func.count(Book.isbn).label('book_count')) \
                .filter(Book.authors.ilike(f"%{query_text}%")) \
                .group_by(Book.authors) \
                .order_by(db.text('book_count DESC')) \
                .limit(max_results).all()
            for row in author_rows:
                if not row.name:
                    continue
                suggestions.append({
                    'type': 'author',
                    'name': row.name,
                    'book_count': int(row.book_count or 0)
                })
        except Exception:
            pass

        # Category suggestions
        try:
            category_rows = db.session.query(Category.name.label('name'), db.func.count(BookCategory.book_isbn).label('book_count')) \
                .join(BookCategory, Category.id == BookCategory.category_id) \
                .filter(Category.name.ilike(f"%{query_text}%")) \
                .group_by(Category.id) \
                .order_by(db.text('book_count DESC')) \
                .limit(max_results).all()
            for row in category_rows:
                suggestions.append({
                    'type': 'category',
                    'name': row.name,
                    'book_count': int(row.book_count or 0)
                })
        except Exception:
            pass

        # AI suggestions (opsiyonel, şu an kapalı)
        ai_suggestions = []
        if include_ai:
            # AI motoru devre dışıysa boş döneriz
            ai_suggestions = []

        # Sınırla ve döndür
        # Öncelik: kitaplar -> yazarlar -> kategoriler
        def sort_key(item):
            order = {'book': 0, 'author': 1, 'category': 2}
            return order.get(item.get('type'), 3)

        suggestions_sorted = sorted(suggestions, key=sort_key)[:max_results]

        return jsonify({
            'suggestions': suggestions_sorted,
            'ai_suggestions': ai_suggestions
        })
    except Exception as e:
        return jsonify({'suggestions': [], 'ai_suggestions': [], 'error': str(e)}), 400

@app.route('/api/books/complete-info', methods=['POST'])
def api_complete_book_info():
    """Complete missing book information using ISBN"""
    data = request.json
    isbn = data.get('isbn')
    
    if not isbn:
        return jsonify({'success': False, 'message': 'ISBN gerekli'}), 400
    
    # Kitabı veritabanından bul
    book = Book.query.filter_by(isbn=isbn).first()
    if not book:
        return jsonify({'success': False, 'message': 'Kitap bulunamadı'}), 404
    
    try:
        # API'den bilgi çek
        from utils import fetch_book_info_from_api
        book_info = fetch_book_info_from_api(isbn)
        
        if not book_info:
            return jsonify({'success': False, 'message': 'ISBN için bilgi bulunamadı'}), 404
        
        # Eksik bilgileri tamamla - DÜZELTİLDİ
        updated_fields = []
        
        # Yardımcı fonksiyon - boş veya geçersiz değer kontrolü
        def is_empty_or_invalid(value):
            if not value:
                return True
            if isinstance(value, str):
                clean_value = value.strip().lower()
                return clean_value == '' or clean_value == 'nan' or clean_value == 'n/a' or clean_value == 'null' or clean_value == 'none'
            return False
        
        # Başlık kontrolü
        if is_empty_or_invalid(book.title) and book_info.get('title'):
            book.title = book_info['title']
            updated_fields.append('Başlık')
        
        # Yazar kontrolü  
        if is_empty_or_invalid(book.authors) and book_info.get('authors'):
            book.authors = book_info['authors']
            updated_fields.append('Yazar')
        
        # Yayınevi kontrolü
        if is_empty_or_invalid(book.publishers) and book_info.get('publishers'):
            if book_info['publishers'] != 'N/A':
                book.publishers = book_info['publishers']
                updated_fields.append('Yayınevi')
        
        # Yayın yılı kontrolü
        if is_empty_or_invalid(book.publish_date) and book_info.get('publish_date'):
            book.publish_date = book_info['publish_date']
            updated_fields.append('Yayın Yılı')
        
        # Sayfa sayısı kontrolü
        if (not book.number_of_pages or book.number_of_pages == 0) and book_info.get('number_of_pages'):
            if book_info['number_of_pages'] > 0:
                book.number_of_pages = book_info['number_of_pages']
                updated_fields.append('Sayfa Sayısı')
        
        # Dil kontrolü
        if is_empty_or_invalid(book.languages) and book_info.get('languages'):
            book.languages = book_info['languages']
            updated_fields.append('Dil')
        
        # Kapak resmi tamamla
        if (not book.image_path or book.image_path.strip() == '') and book_info.get('image_url'):
            import requests
            import os
            
            try:
                image_filename = f"{book.isbn}.jpg"
                image_path = os.path.join('static', 'book_covers', image_filename)
                full_image_path = os.path.join(app.root_path, image_path)
                
                # Create directory if not exists
                os.makedirs(os.path.dirname(full_image_path), exist_ok=True)
                
                # SSL certificate verification disabled for PyInstaller executable compatibility
                import sys
                if hasattr(sys, 'frozen'):
                    # Running as PyInstaller executable
                    response = requests.get(book_info['image_url'], verify=False, timeout=10)
                else:
                    # Running normally
                    response = requests.get(book_info['image_url'], timeout=10)
                if response.status_code == 200:
                    with open(full_image_path, 'wb') as f:
                        f.write(response.content)
                    
                    book.image_path = image_filename
                    updated_fields.append('Kapak Resmi')
            except Exception as e:
                print(f"Cover download error for {isbn}: {e}")
        
        if updated_fields:
            db.session.commit()
            message = f"Tamamlanan alanlar: {', '.join(updated_fields)}"
            return jsonify({'success': True, 'message': message, 'updated_fields': updated_fields})
        else:
            return jsonify({'success': True, 'message': 'Tüm bilgiler zaten mevcut', 'updated_fields': []})
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Bilgi tamamlama hatası: {str(e)}'}), 500

@app.route('/api/books/complete-all-info', methods=['POST'])
def api_complete_all_books_info():
    """Complete missing book information in batches of 20"""
    data = request.json or {}
    offset = data.get('offset', 0)
    limit = 20  # Process 20 books at a time
    
    try:
        # Get books with missing information
        books_query = Book.query.filter(
            db.or_(
                Book.title == None,
                Book.title == '',
                Book.title == 'nan',
                Book.authors == None,
                Book.authors == '',
                Book.authors == 'nan',
                Book.publishers == None,
                Book.publishers == '',
                Book.publishers == 'nan',
                Book.publish_date == None,
                Book.publish_date == '',
                Book.number_of_pages == None,
                Book.number_of_pages == 0,
                Book.image_path == None,
                Book.image_path == ''
            )
        )
        
        # Get total count for progress tracking
        total_count = books_query.count()
        
        # Get batch of books
        books = books_query.offset(offset).limit(limit).all()
        
        if not books:
            return jsonify({
                'success': True,
                'message': 'Tüm kitaplar tamamlandı',
                'completed': True,
                'processed': 0,
                'total': total_count,
                'offset': offset
            })
        
        success_count = 0
        error_count = 0
        updated_books = []
        errors = []
        
        for book in books:
            try:
                # Fetch book info from API
                book_info = fetch_book_info_from_api(book.isbn)
                
                if not book_info:
                    error_count += 1
                    continue
                
                updated_fields = []
                
                # Helper function to check if value is empty or invalid
                def is_empty_or_invalid(value):
                    if not value:
                        return True
                    if isinstance(value, str):
                        clean_value = value.strip().lower()
                        return clean_value == '' or clean_value == 'nan' or clean_value == 'n/a' or clean_value == 'null' or clean_value == 'none'
                    return False
                
                # Update title
                if is_empty_or_invalid(book.title) and book_info.get('title'):
                    book.title = book_info['title']
                    updated_fields.append('title')
                
                # Update authors
                if is_empty_or_invalid(book.authors) and book_info.get('authors'):
                    book.authors = book_info['authors']
                    updated_fields.append('authors')
                
                # Update publishers
                if is_empty_or_invalid(book.publishers) and book_info.get('publishers'):
                    if book_info['publishers'] != 'N/A':
                        book.publishers = book_info['publishers']
                        updated_fields.append('publishers')
                
                # Update publish date
                if is_empty_or_invalid(book.publish_date) and book_info.get('publish_date'):
                    book.publish_date = book_info['publish_date']
                    updated_fields.append('publish_date')
                
                # Update page count
                if (not book.number_of_pages or book.number_of_pages == 0) and book_info.get('number_of_pages'):
                    if book_info['number_of_pages'] > 0:
                        book.number_of_pages = book_info['number_of_pages']
                        updated_fields.append('pages')
                
                # Update language
                if is_empty_or_invalid(book.languages) and book_info.get('languages'):
                    book.languages = book_info['languages']
                    updated_fields.append('languages')
                
                # Download cover image
                if (not book.image_path or book.image_path.strip() == '') and book_info.get('image_url'):
                    try:
                        downloaded = download_cover_image(book_info['image_url'], book.isbn)
                        if downloaded:
                            book.image_path = downloaded
                            updated_fields.append('image')
                    except Exception:
                        pass
                
                if updated_fields:
                    success_count += 1
                    updated_books.append({
                        'isbn': book.isbn,
                        'title': book.title,
                        'updated_fields': updated_fields
                    })
                    
            except Exception as e:
                error_count += 1
                errors.append(f"{book.isbn}: {str(e)}")
                continue
        
        # Commit changes
        db.session.commit()
        
        # Calculate progress
        processed_total = offset + len(books)
        has_more = processed_total < total_count
        
        return jsonify({
            'success': True,
            'message': f'{success_count} kitap güncellendi, {error_count} hata',
            'processed': len(books),
            'successful': success_count,
            'errors': error_count,
            'total': total_count,
            'offset': offset,
            'next_offset': offset + limit,
            'has_more': has_more,
            'completed': not has_more,
            'updated_books': updated_books[:10],  # First 10 for preview
            'error_details': errors[:5]  # First 5 errors
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'İşlem hatası: {str(e)}'
        }), 500

@app.route('/api/books/fetch-from-isbn', methods=['POST'])
def api_fetch_book_from_isbn():
    """Fetch book details from ISBN using Google Books API for new book form"""
    data = request.json
    isbn = data.get('isbn', '').strip()
    
    if not isbn:
        return jsonify({'success': False, 'message': 'ISBN gerekli'}), 400
    
    # Check if book already exists
    existing_book = Book.query.filter_by(isbn=isbn).first()
    if existing_book:
        return jsonify({
            'success': False,
            'message': 'Bu ISBN numarasına sahip kitap zaten mevcut',
            'existing': True
        }), 400
    
    try:
        # Fetch book info from API
        book_info = fetch_book_info_from_api(isbn)
        
        if not book_info:
            return jsonify({'success': False, 'message': 'ISBN için bilgi bulunamadı'}), 404
        
        # Process language and categories if available
        language_map = {
            'en': 'İngilizce',
            'tr': 'Türkçe',
            'de': 'Almanca',
            'fr': 'Fransızca',
            'es': 'İspanyolca',
            'it': 'İtalyanca',
            'ru': 'Rusça',
            'ar': 'Arapça',
            'ja': 'Japonca',
            'zh': 'Çince'
        }
        
        # Map language code to Turkish
        if book_info.get('languages'):
            lang_code = book_info['languages'].lower()[:2]
            book_info['languages'] = language_map.get(lang_code, book_info['languages'])
        
        return jsonify({
            'success': True,
            'book': {
                'isbn': isbn,
                'title': book_info.get('title', ''),
                'authors': book_info.get('authors', ''),
                'publishers': book_info.get('publishers', ''),
                'publish_date': book_info.get('publish_date', ''),
                'number_of_pages': book_info.get('number_of_pages', 0),
                'languages': book_info.get('languages', 'Türkçe'),
                'description': book_info.get('description', ''),
                'image_url': book_info.get('image_url', ''),
                'category': book_info.get('category', '')
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'API hatası: {str(e)}'}), 500

@app.route('/api/books/get-all-isbns', methods=['GET'])
def api_get_all_isbns():
    """Get all book ISBNs for batch processing"""
    try:
        # Tüm kitapların ISBN'lerini al
        books = Book.query.with_entities(Book.isbn).all()
        isbns = [book.isbn for book in books if book.isbn]
        
        return jsonify({
            'success': True,
            'isbns': isbns,
            'count': len(isbns)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'ISBN listesi alınamadı: {str(e)}'
        }), 500

@app.route('/api/books/verify-and-update-batch', methods=['POST'])
def api_verify_and_update_batch():
    """Verify and update book information in batch - FORCE UPDATE ALL FIELDS"""
    data = request.json or {}
    isbns = data.get('isbns', [])
    force_update = data.get('force_update', True)  # Zorla güncelle
    verify_all_fields = data.get('verify_all_fields', True)  # Tüm alanları kontrol et
    include_covers = data.get('include_covers', True)
    
    if not isbns:
        return jsonify({'success': False, 'message': 'ISBN listesi gerekli'}), 400
    
    results = []
    
    for isbn in isbns:
        try:
            # Mevcut kitabı bul
            book = Book.query.get(isbn)
            if not book:
                results.append({
                    'isbn': isbn,
                    'error': 'Kitap bulunamadı',
                    'updated': False
                })
                continue
            
            # API'den güncel bilgileri al
            book_info = fetch_book_info_from_api(isbn)
            
            if not book_info:
                results.append({
                    'isbn': isbn,
                    'error': 'API bilgisi bulunamadı',
                    'updated': False
                })
                continue
            
            # Değişiklikleri takip et
            changes = []
            was_updated = False
            
            # Helper function - değeri kontrol et ve güncelle
            def update_field(field_name, api_value, display_name):
                nonlocal was_updated
                current_value = getattr(book, field_name)
                
                # API'den gelen değer varsa ve mevcut değerden farklıysa
                if api_value and api_value != 'N/A':
                    # Force update modunda VEYA alan boşsa/geçersizse güncelle
                    should_update = False
                    
                    if force_update:
                        # Zorla güncelleme modunda farklıysa güncelle
                        if str(current_value) != str(api_value):
                            should_update = True
                    else:
                        # Normal modda sadece boş/geçersiz alanları güncelle
                        if not current_value or str(current_value).strip().lower() in ['', 'nan', 'n/a', 'null', 'none']:
                            should_update = True
                    
                    if should_update:
                        setattr(book, field_name, api_value)
                        changes.append(f"{display_name}: {current_value} → {api_value}")
                        was_updated = True
            
            # TÜM ALANLARI KONTROL ET VE GÜNCELLE
            update_field('title', book_info.get('title'), 'Başlık')
            update_field('authors', book_info.get('authors'), 'Yazarlar')
            update_field('publishers', book_info.get('publishers'), 'Yayınevi')
            update_field('publish_date', book_info.get('publish_date'), 'Yayın Tarihi')
            update_field('languages', book_info.get('languages'), 'Diller')
            
            # Sayfa sayısı özel kontrolü
            api_pages = book_info.get('number_of_pages', 0)
            if api_pages and api_pages > 0:
                if force_update or not book.number_of_pages or book.number_of_pages == 0:
                    if book.number_of_pages != api_pages:
                        old_pages = book.number_of_pages
                        book.number_of_pages = api_pages
                        changes.append(f"Sayfa Sayısı: {old_pages} → {api_pages}")
                        was_updated = True
            
            # Kapak resmi güncelleme
            if include_covers and book_info.get('image_url'):
                if force_update or not book.image_path or book.image_path.strip() == '':
                    try:
                        downloaded = download_cover_image(book_info['image_url'], isbn)
                        if downloaded:
                            old_image = book.image_path
                            book.image_path = downloaded
                            changes.append(f"Kapak resmi güncellendi")
                            was_updated = True
                    except Exception as img_error:
                        print(f"Kapak indirme hatası {isbn}: {img_error}")
            
            # Sonuçları kaydet
            if was_updated:
                db.session.commit()
                results.append({
                    'isbn': isbn,
                    'title': book.title,
                    'updated': True,
                    'changes': ', '.join(changes[:3]) + ('...' if len(changes) > 3 else ''),
                    'change_count': len(changes)
                })
            else:
                results.append({
                    'isbn': isbn,
                    'title': book.title,
                    'verified': True,
                    'updated': False,
                    'message': 'Değişiklik gerekmedi'
                })
                
        except Exception as e:
            results.append({
                'isbn': isbn,
                'error': f'İşlem hatası: {str(e)}',
                'updated': False
            })
            # Hata durumunda rollback
            db.session.rollback()
    
    # Özet istatistikleri hesapla
    updated_count = sum(1 for r in results if r.get('updated'))
    verified_count = sum(1 for r in results if r.get('verified'))
    error_count = sum(1 for r in results if r.get('error'))
    
    return jsonify({
        'success': True,
        'results': results,
        'summary': {
            'total': len(results),
            'updated': updated_count,
            'verified': verified_count,
            'errors': error_count
        },
        'message': f'{updated_count} kitap güncellendi, {verified_count} doğrulandı, {error_count} hata'
    })

@app.route('/api/shelf-map')
def api_shelf_map():
    """Raf/Dolap haritası için kitap verilerini döndür"""
    try:
        books = Book.query.filter(
            db.and_(
                Book.shelf.isnot(None),
                Book.cupboard.isnot(None),
                Book.shelf != '',
                Book.cupboard != ''
            )
        ).order_by(Book.cupboard, Book.shelf).all()
        
        books_data = []
        for book in books:
            # Kapak yolunu normalize et
            image_url = normalize_cover_url(book.image_path) if book.image_path else '/static/img/no_cover.png'
            
            books_data.append({
                'title': book.title,
                'isbn': book.isbn,
                'authors': book.authors,
                'shelf': book.shelf or "Diğer",
                'cupboard': book.cupboard or "Diğer",
                'image_url': image_url
            })

        return jsonify({
            'success': True,
            'books': books_data
        })
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# Add the missing /api/add_book endpoint that frontend is using
@app.route('/api/add_book', methods=['POST'])
def api_add_book_frontend():
    """Add a new book to the library with UNIQUE constraint handling - Frontend endpoint"""
    from sqlalchemy.exc import IntegrityError
    
    # Skip authentication check for EXE compatibility
    # This allows the endpoint to work in PyInstaller builds
    
    # Get JSON data from request
    data = request.get_json()
    
    # Validate required fields
    required_fields = ['isbn', 'title', 'authors']
    for field in required_fields:
        if field not in data or not data[field]:
            return jsonify({'error': f'{field} is required'}), 400
    
    # Check if book with same ISBN already exists
    existing_book = Book.query.filter_by(isbn=data['isbn']).first()
    if existing_book:
        # Update quantity instead of creating duplicate
        old_quantity = existing_book.quantity or 1
        new_quantity = old_quantity + data.get('quantity', 1)
        existing_book.quantity = new_quantity
        
        # Update empty fields if provided
        if not existing_book.title and data.get('title'):
            existing_book.title = data.get('title')
        if not existing_book.authors and data.get('authors'):
            existing_book.authors = data.get('authors')
        if not existing_book.publishers and data.get('publishers'):
            existing_book.publishers = data.get('publishers')
        if not existing_book.shelf and data.get('shelf'):
            existing_book.shelf = data.get('shelf')
        if not existing_book.cupboard and data.get('cupboard'):
            existing_book.cupboard = data.get('cupboard')
        if not existing_book.category and data.get('category'):
            existing_book.category = data.get('category')
        
        try:
            db.session.commit()
            return jsonify({
                'success': True,
                'message': 'Kitap zaten mevcut, adet güncellendi',
                'warning': f"ISBN {data['isbn']} zaten kayıtlı. Eski adet: {old_quantity}, Yeni adet: {new_quantity}",
                'book': {
                    'id': existing_book.id,
                    'isbn': existing_book.isbn,
                    'title': existing_book.title,
                    'authors': existing_book.authors,
                    'quantity': existing_book.quantity
                }
            }), 200
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': 'Adet güncellenirken hata oluştu'}), 500
    
    # Create new book with all fields
    new_book = Book(
        isbn=data['isbn'],
        title=data['title'],
        authors=data['authors'],
        publish_date=data.get('publish_date', ''),
        number_of_pages=data.get('number_of_pages', 0),
        publishers=data.get('publishers', ''),
        languages=data.get('languages', ''),
        quantity=data.get('quantity', 1),
        shelf=data.get('shelf', ''),
        cupboard=data.get('cupboard', ''),
        image_path=data.get('image_path', ''),
        cover_image=data.get('cover_image'),
        category=data.get('category', ''),
        edition=data.get('edition', ''),
        description=data.get('description', ''),
        average_rating=data.get('average_rating', 0.0),
        review_count=data.get('review_count', 0),
        total_borrow_count=0,
        last_borrowed_date=None,
        qr_code=data.get('qr_code'),
        barcode=data.get('barcode')
    )
    
    # Add to database
    try:
        db.session.add(new_book)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Kitap başarıyla eklendi',
            'book': {
                'id': new_book.id,
                'isbn': new_book.isbn,
                'title': new_book.title,
                'authors': new_book.authors,
                'quantity': new_book.quantity
            }
        }), 201
        
    except IntegrityError as e:
        db.session.rollback()
        
        # Check if it's ISBN duplicate
        if 'UNIQUE constraint' in str(e) or 'isbn' in str(e.orig).lower():
            return jsonify({
                'error': f"ISBN {data['isbn']} zaten kayıtlı",
                'message': 'Bu ISBN numarasına sahip bir kitap zaten mevcut'
            }), 409
        else:
            return jsonify({'error': 'Veritabanı kısıtlama hatası'}), 409
            
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Kitap eklenirken hata oluştu: {str(e)}'}), 500
