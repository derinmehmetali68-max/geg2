from flask import request, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from models import db, User, Book, Member, Transaction, KioskRequest
from utils import log_activity, add_notification, process_borrow_transaction, process_return_transaction, get_setting
from routes import role_required
from uuid import uuid4
import logging

# Kiosk Session deposu - Global değişken
KIOSK_SESSIONS = {}

# Logger ayarla
logger = logging.getLogger(__name__)

def register_kiosk_routes(app):
    """Kiosk route'larını kaydet"""
    
    @app.route('/api/members/by-school-no/<school_number>')
    def kiosk_get_member_by_school_no(school_number):
        """Okul numarasına göre üye bilgilerini getir"""
        try:
            member = Member.query.filter_by(numara=school_number).first()
            if not member:
                return jsonify({'success': False, 'message': 'Üye bulunamadı'}), 404
            
            return jsonify({
                'success': True,
                'member': {
                    'id': member.id,
                    'ad_soyad': member.ad_soyad,
                    'name': member.ad_soyad,  # JavaScript uyumluluğu için
                    'school_number': member.numara,
                    'numara': member.numara,
                    'sinif': member.sinif,
                    'member_class': member.sinif,
                    'email': member.email,
                    'phone': member.phone,
                    'uye_turu': member.uye_turu,
                    'role': member.uye_turu  # JavaScript uyumluluğu için
                }
            })
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @app.route('/api/kiosk/verify-member/<member_qr>')
    def kiosk_api_verify_member(member_qr):
        """Kiosk modu: Üye QR kodu doğrulama"""
        try:
            # Önce üye numarasına göre ara (en yaygın durum)
            member = Member.query.filter_by(numara=member_qr).first()
            
            # Eğer üye numarasında bulunamadıysa, ID olarak dene
            if not member:
                try:
                    member_id = int(member_qr)
                    member = Member.query.get(member_id)
                except ValueError:
                    pass
            
            if not member:
                return jsonify({'success': False, 'message': 'Üye bulunamadı'}), 404
            
            # Ceza kontrolü
            if member.penalty_until and datetime.now() < member.penalty_until:
                return jsonify({
                    'success': False, 
                    'message': f'Ceza süreniz {member.penalty_until.strftime("%d.%m.%Y")} tarihine kadar devam ediyor'
                }), 403
            
            # Aktif ödünç sayısını hesapla
            active_borrows = Transaction.query.filter_by(member_id=member.id, return_date=None).count()
            
            return jsonify({
                'success': True,
                'member': {
                    'id': member.id,
                    'name': member.ad_soyad,
                    'number': member.numara,
                    'class': member.sinif or 'Belirtilmemiş',
                    'active_books': active_borrows,
                    'max_books': int(get_setting('max_books_per_member', '5'))
                }
            })
            
        except Exception as e:
            return jsonify({'success': False, 'message': f'Üye doğrulama hatası: {str(e)}'}), 500
    
    @app.route('/api/kiosk/start-session', methods=['POST'])
    def kiosk_start_session():
        """Kiosk: Üye doğrulandıktan sonra oturum token üret"""
        global KIOSK_SESSIONS
        try:
            data = request.json or {}
            member_id = data.get('member_id')
            if not member_id:
                return jsonify({'success': False, 'message': 'Üye bilgisi gerekli'}), 400
            
            # Token oluştur ve global değişkene ekle
            token = uuid4().hex
            KIOSK_SESSIONS[token] = int(member_id)
            
            print(f"[DEBUG] Session oluşturuldu - Token: {token}, Member ID: {member_id}")
            print(f"[DEBUG] Aktif sessionlar: {list(KIOSK_SESSIONS.keys())}")
            
            return jsonify({'success': True, 'token': token})
        except Exception as e:
            print(f"[ERROR] Session oluşturma hatası: {str(e)}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @app.route('/api/kiosk/validate-session')
    def kiosk_validate_session():
        """Session token doğrulama"""
        token = request.args.get('token')
        if token and token in KIOSK_SESSIONS:
            return jsonify({'success': True, 'member_id': KIOSK_SESSIONS[token]})
        return jsonify({'success': False}), 401
    
    @app.route('/api/kiosk/user-data/<int:member_id>')
    def kiosk_user_data(member_id):
        """Kiosk: Kullanıcı verilerini döndür"""
        try:
            session_token = request.args.get('session_token')
            
            # Basit session doğrulama
            if not session_token or KIOSK_SESSIONS.get(session_token) != member_id:
                return jsonify({'success': False, 'message': 'Geçersiz oturum'}), 401
                
            member = Member.query.get(member_id)
            if not member:
                return jsonify({'success': False, 'message': 'Üye bulunamadı'}), 404

            active_books = Transaction.query.filter_by(member_id=member_id, return_date=None).count()
            pending_requests = KioskRequest.query.filter_by(member_id=member_id, status='pending').count()

            return jsonify({
                'success': True,
                'user': {
                    'active_books': active_books,
                    'pending_requests': pending_requests,
                }
            })
        except Exception as e:
            return jsonify({'success': False, 'message': f'Kullanıcı verileri alınamadı: {str(e)}'}), 500
    
    @app.route('/api/kiosk/user-requests/<int:member_id>')
    def kiosk_user_requests(member_id):
        """Kiosk: Kullanıcının taleplerini döndür"""
        try:
            session_token = request.args.get('session_token')
            
            # Basit session doğrulama
            if not session_token or KIOSK_SESSIONS.get(session_token) != member_id:
                return jsonify({'success': False, 'message': 'Geçersiz oturum'}), 401
                
            requests = db.session.query(KioskRequest, Book)\
                .join(Book, KioskRequest.isbn == Book.isbn)\
                .filter(KioskRequest.member_id == member_id)\
                .order_by(KioskRequest.created_at.desc())\
                .limit(20).all()
            
            requests_data = []
            for req, book in requests:
                requests_data.append({
                    'id': req.id,
                    'book_title': book.title,
                    'book_authors': book.authors,
                    'status': req.status,
                    'created_at': req.created_at.strftime('%d.%m.%Y %H:%M'),
                })
                
            return jsonify({'success': True, 'requests': requests_data})
        except Exception as e:
            return jsonify({'success': False, 'message': f'Talep verileri alınamadı: {str(e)}'}), 500

    @app.route('/api/kiosk/user-request/<int:request_id>', methods=['DELETE'])
    def kiosk_user_delete_request(request_id):
        """Kiosk: Kullanıcı kendi talebini silsin (bekleyen/geçmiş)"""
        try:
            data = request.get_json() or {}
            session_token = data.get('session_token') or request.args.get('session_token')
            if not session_token or session_token not in KIOSK_SESSIONS:
                return jsonify({'success': False, 'message': 'Geçersiz oturum'}), 401
            member_id = KIOSK_SESSIONS.get(session_token)

            kiosk_request = KioskRequest.query.get(request_id)
            if not kiosk_request or kiosk_request.member_id != member_id:
                return jsonify({'success': False, 'message': 'Talep bulunamadı'}), 404

            # Silme - tüm durumlar için izin ver (kullanıcı talebini listeden kaldırmak istiyor)
            db.session.delete(kiosk_request)
            db.session.commit()
            log_activity('kiosk_request_user_deleted', f'Kullanıcı talebi sildi: ID {request_id}')
            return jsonify({'success': True, 'message': 'Talep silindi'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @app.route('/api/kiosk/request-borrow', methods=['POST'])
    def kiosk_request_borrow():
        """Kiosk: Ödünç alma talebi oluştur"""
        global KIOSK_SESSIONS
        try:
            data = request.json
            isbn = data.get('isbn')
            session_token = data.get('session_token')
            
            print(f"[DEBUG] Ödünç alma talebi - ISBN: {isbn}, Token: {session_token}")
            
            if not isbn or not session_token:
                return jsonify({'success': False, 'message': 'Eksik parametreler'}), 400
            
            # Session doğrulama
            print(f"[DEBUG] Mevcut sessionlar: {list(KIOSK_SESSIONS.keys())}")
            member_id = KIOSK_SESSIONS.get(session_token)
            
            if member_id is None:
                print(f"[ERROR] Session bulunamadı - Token: {session_token}")
                return jsonify({'success': False, 'message': 'Geçersiz oturum. Lütfen tekrar giriş yapın.'}), 401
            
            print(f"[DEBUG] Session doğrulandı - Member ID: {member_id}")
            
            # Kitap ve üye kontrolü
            book = Book.query.get(isbn)
            member = Member.query.get(member_id)
            
            if not book:
                return jsonify({'success': False, 'message': 'Kitap bulunamadı'}), 404
            
            if not member:
                return jsonify({'success': False, 'message': 'Üye bulunamadı'}), 404
            
            # Kitap müsaitlik kontrolü
            borrowed_count = Transaction.query.filter_by(isbn=isbn, return_date=None).count()
            if book.quantity <= borrowed_count:
                return jsonify({'success': False, 'message': 'Kitap şu anda mevcut değil'}), 400
            
            # Zaten bir talebi var mı kontrol et
            existing_request = KioskRequest.query.filter_by(
                member_id=member_id,
                isbn=isbn,
                request_type='borrow',
                status='pending'
            ).first()
            
            if existing_request:
                return jsonify({'success': False, 'message': 'Bu kitap için zaten bekleyen bir talebiniz var'}), 400
            
            # Yeni talep oluştur
            new_request = KioskRequest(
                member_id=member_id,
                isbn=isbn,
                request_type='borrow',
                status='pending',
                session_token=session_token,
                notes='Kiosk self-service talebi'
            )
            
            db.session.add(new_request)
            db.session.commit()
            
            # Aktivite logla
            log_activity('kiosk_request', f'Kiosk ödünç alma talebi: {book.title} - {member.ad_soyad}')
            
            return jsonify({
                'success': True,
                'message': 'Ödünç alma talebi başarıyla oluşturuldu',
                'request_id': new_request.id
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Talep oluşturma hatası: {str(e)}'}), 500
    
    @app.route('/api/kiosk/process-return', methods=['POST'])
    def kiosk_process_return():
        """Kiosk: İade işlemi"""
        global KIOSK_SESSIONS
        try:
            data = request.json
            isbn = data.get('isbn')
            session_token = data.get('session_token')
            direct_member_id = data.get('member_id')  # Direkt member_id de kabul et
            
            print(f"[DEBUG] İade işlemi - ISBN: {isbn}, Token: {session_token}, Direct Member ID: {direct_member_id}")
            
            if not isbn:
                return jsonify({'success': False, 'message': 'ISBN bilgisi eksik'}), 400
            
            # Member ID'yi belirle - önce direkt gelen member_id'yi kontrol et
            member_id = None
            
            if direct_member_id:
                # Direkt member_id geldiyse onu kullan
                member_id = int(direct_member_id)
                print(f"[DEBUG] Direkt member_id kullanılıyor: {member_id}")
                
                # Eğer session_token varsa, session'a da ekle (gelecek istekler için)
                if session_token and session_token.startswith('temp_'):
                    # Temp token'ı gerçek bir session'a dönüştür
                    real_token = str(uuid4().hex)
                    KIOSK_SESSIONS[real_token] = member_id
                    print(f"[DEBUG] Temp token gerçek session'a dönüştürüldü: {real_token}")
                elif session_token:
                    # Normal token varsa session'a ekle/güncelle
                    KIOSK_SESSIONS[session_token] = member_id
                    print(f"[DEBUG] Session güncellendi")
                    
            elif session_token:
                # Session token ile member_id'yi bul
                print(f"[DEBUG] Gelen session token: {session_token}")
                print(f"[DEBUG] Mevcut aktif sessionlar: {list(KIOSK_SESSIONS.keys())}")
                
                member_id = KIOSK_SESSIONS.get(session_token)
                
                if member_id is None:
                    print(f"[ERROR] Session bulunamadı! Token: {session_token}")
                    print(f"[ERROR] Mevcut sessionlar: {KIOSK_SESSIONS}")
                    
                    # Hata mesajı
                    error_msg = 'Oturum bulunamadı. '
                    if len(KIOSK_SESSIONS) == 0:
                        error_msg += 'Hiç aktif oturum yok. '
                    else:
                        error_msg += f'Aktif oturum sayısı: {len(KIOSK_SESSIONS)}. '
                    error_msg += 'Lütfen tekrar giriş yapın.'
                    
                    return jsonify({'success': False, 'message': error_msg}), 401
                    
                print(f"[DEBUG] Session'dan member_id bulundu: {member_id}")
            else:
                return jsonify({'success': False, 'message': 'Üye bilgisi veya oturum bilgisi eksik'}), 400
            
            print(f"[DEBUG] İşlem yapılacak Member ID: {member_id}")
            
            # Kitap ve üye kontrolü
            book = Book.query.get(isbn)
            member = Member.query.get(member_id)
            
            if not book:
                return jsonify({'success': False, 'message': 'Kitap bulunamadı'}), 404
            
            if not member:
                return jsonify({'success': False, 'message': 'Üye bulunamadı'}), 404
            
            # Aktif ödünç alma var mı kontrol et
            active_transaction = Transaction.query.filter_by(
                member_id=member_id,
                isbn=isbn,
                return_date=None
            ).first()
            
            if not active_transaction:
                # Belki farklı bir ISBN formatı ile deneniyor, tekrar kontrol et
                book = Book.query.get(isbn)
                if book:
                    # Aynı kitabın farklı transaction'larını kontrol et
                    active_transaction = Transaction.query.filter_by(
                        member_id=member_id,
                        isbn=book.isbn,
                        return_date=None
                    ).first()
                
                if not active_transaction:
                    # Bu üyenin tüm aktif ödünç kitaplarını listele (debug için)
                    active_books = Transaction.query.filter_by(
                        member_id=member_id,
                        return_date=None
                    ).all()
                    
                    if active_books:
                        book_list = [f"{t.book.title if t.book else 'Bilinmeyen'} (ISBN: {t.isbn})" for t in active_books]
                        return jsonify({
                            'success': False, 
                            'message': f'Bu kitabı ödünç almamışsınız. Üzerinizdeki kitaplar: {", ".join(book_list)}'
                        }), 400
                    else:
                        return jsonify({
                            'success': False, 
                            'message': 'Üzerinizde hiç ödünç kitap bulunmuyor'
                        }), 400
            
            # İade işlemini gerçekleştir
            result = process_return_transaction(active_transaction, 'Kiosk self-service iade', 'kiosk')
            
            if result['success']:
                # Kitap durumunu güncelle
                book.status = 'available'
                db.session.commit()
                
                # Bildirim oluştur
                add_notification('return', f'"{book.title}" kitabı iade edildi', book.isbn)
                
                # E-posta bildirimi gönder
                if member.email:
                    from utils import send_email
                    send_email(member.email, 'book_returned', {
                        'member_name': member.ad_soyad,
                        'book_title': book.title,
                        'return_date': active_transaction.return_date,
                        'fine_amount': 0,  # Ceza bilgisi process_return_transaction içinde hesaplanır
                        'days_overdue': 0
                    })
                
                return jsonify({
                    'success': True,
                    'message': 'Kitap başarıyla iade edildi',
                    'return_date': active_transaction.return_date
                })
            else:
                return jsonify(result), 400
            
        except Exception as e:
            return jsonify({'success': False, 'message': f'İade işlemi hatası: {str(e)}'}), 500
    
    @app.route('/api/advanced-kiosk/member-profile/<int:member_id>')
    def kiosk_advanced_member_profile(member_id):
        """Kiosk için üye profilini ve aktif kitapları döndür"""
        try:
            member = db.session.get(Member, member_id)
            if not member:
                return jsonify({'success': False, 'message': 'Üye bulunamadı'}), 404
            
            active_transactions = Transaction.query.filter_by(member_id=member_id, return_date=None).all()
            
            active_books = []
            for transaction in active_transactions:
                # Convert dates
                # due_date
                if isinstance(transaction.due_date, str):
                    try:
                        due_date_dt = datetime.strptime(transaction.due_date, '%Y-%m-%d').date()
                    except Exception:
                        due_date_dt = datetime.utcnow().date()
                else:
                    try:
                        due_date_dt = transaction.due_date
                        if hasattr(due_date_dt, 'date'):
                            due_date_dt = due_date_dt.date()
                    except Exception:
                        due_date_dt = datetime.utcnow().date()
                
                # borrow_date
                if isinstance(transaction.borrow_date, str):
                    try:
                        borrow_date_dt = datetime.strptime(transaction.borrow_date, '%Y-%m-%d')
                    except Exception:
                        borrow_date_dt = datetime.utcnow()
                else:
                    borrow_date_dt = transaction.borrow_date or datetime.utcnow()
                
                days_remaining = (due_date_dt - datetime.utcnow().date()).days
                is_overdue = days_remaining < 0
                
                book = transaction.book
                if book:
                    try:
                        from utils import normalize_cover_url
                        cover_path = normalize_cover_url(book.image_path)
                    except Exception:
                        cover_path = '/static/img/no_cover.png'
                else:
                    cover_path = '/static/img/no_cover.png'
                
                active_books.append({
                    'isbn': transaction.isbn,
                    'title': book.title if book else '',
                    'authors': book.authors if book else '',
                    'image_path': cover_path,
                    'borrow_date': borrow_date_dt.strftime('%Y-%m-%d'),
                    'due_date': due_date_dt.strftime('%Y-%m-%d'),
                    'days_remaining': days_remaining,
                    'is_overdue': is_overdue
                })
                
            # Split full name
            full_name = member.ad_soyad or ''
            parts = full_name.split()
            first_name = parts[0] if parts else ''
            last_name = ' '.join(parts[1:]) if len(parts) > 1 else ''
            
            member_data = {
                'id': member.id,
                'name': first_name or full_name,
                'surname': last_name,
                'school_number': member.numara,
                'email': member.email,
                'phone': member.phone,
                'role': member.uye_turu or 'Üye',
                'member_class': member.sinif,
                'profile_image': getattr(member, 'profile_image', None)
            }
            
            return jsonify({'success': True, 'member': member_data, 'active_books': active_books})
        except Exception as e:
            return jsonify({'success': False, 'message': f'Profil bilgileri alınamadı: {str(e)}'}), 500
    
    @app.route('/api/admin/kiosk-requests')
    # Authentication removed for EXE compatibility
    def kiosk_admin_get_requests():
        """Admin: Kiosk taleplerini listele"""
        try:
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 20, type=int)
            status = request.args.get('status', '')

            query = KioskRequest.query.order_by(KioskRequest.created_at.desc())
            
            if status:
                query = query.filter(KioskRequest.status == status)
                
            requests_paginated = query.paginate(page=page, per_page=per_page, error_out=False)
            requests = requests_paginated.items
            
            requests_data = []
            for req in requests:
                requests_data.append({
                    'id': req.id,
                    'member_name': req.member.ad_soyad if req.member else 'Bilinmeyen',
                    'member_number': req.member.numara if req.member else None,
                    'member_class': req.member.sinif if req.member else None,
                    'book_title': req.book.title if req.book else 'Bilinmeyen',
                    'book_authors': req.book.authors if req.book else None,
                    'isbn': req.isbn,
                    'request_type': req.request_type,
                    'status': req.status,
                    'created_at': req.created_at.strftime('%d.%m.%Y %H:%M'),
                    'approved_by': req.approver.username if req.approver else None,
                    'approved_at': req.approved_at.strftime('%d.%m.%Y %H:%M') if req.approved_at else None,
                    'notes': req.notes
                })

            return jsonify({
                'success': True,
                'requests': requests_data,
                'total': requests_paginated.total,
                'pages': requests_paginated.pages,
                'current_page': requests_paginated.page
            })
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @app.route('/api/admin/kiosk-request/<int:request_id>', methods=['DELETE'])
    # Authentication removed for EXE compatibility
    def kiosk_admin_delete_request(request_id):
        """Admin: Kiosk talebini sil"""
        try:
            kiosk_request = KioskRequest.query.get(request_id)
            if not kiosk_request:
                return jsonify({'success': False, 'message': 'Talep bulunamadı'}), 404

            db.session.delete(kiosk_request)
            db.session.commit()

            log_activity('kiosk_request_deleted', f'Kiosk talebi silindi: ID {request_id}')
            return jsonify({'success': True, 'message': 'Talep silindi'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500

    @app.route('/api/admin/kiosk-request/<int:request_id>', methods=['PUT'])
    # Authentication removed for EXE compatibility
    def kiosk_admin_update_request(request_id):
        """Admin: Kiosk talebini güncelle (durum/not)"""
        try:
            kiosk_request = KioskRequest.query.get(request_id)
            if not kiosk_request:
                return jsonify({'success': False, 'message': 'Talep bulunamadı'}), 404

            data = request.json or {}
            new_status = data.get('status')
            new_notes = data.get('notes')

            if new_status in ['pending', 'approved', 'rejected', 'completed']:
                kiosk_request.status = new_status
            if new_notes is not None:
                kiosk_request.notes = new_notes

            db.session.commit()
            log_activity('kiosk_request_updated', f'Kiosk talebi güncellendi: ID {request_id}')
            return jsonify({'success': True, 'message': 'Talep güncellendi'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500

    @app.route('/api/admin/kiosk-request/<int:request_id>/approve', methods=['POST'])
    # Authentication removed for EXE compatibility
    def kiosk_admin_approve_request(request_id):
        """Admin: Kiosk talebini onayla"""
        try:
            kiosk_request = KioskRequest.query.get(request_id)
            if not kiosk_request:
                return jsonify({'success': False, 'message': 'Talep bulunamadı'}), 404

            if kiosk_request.status != 'pending':
                return jsonify({'success': False, 'message': 'Bu talep zaten işlenmiş'}), 400

            # Ödünç alma işlemini gerçekleştir
            if kiosk_request.request_type == 'borrow':
                # Güvenlik: İlişkiler eksikse yeniden yükle
                if not kiosk_request.book:
                    kiosk_request.book = Book.query.get(kiosk_request.isbn)
                if not kiosk_request.member:
                    kiosk_request.member = Member.query.get(kiosk_request.member_id)

                if not kiosk_request.book or not kiosk_request.member:
                    return jsonify({'success': False, 'message': 'Kitap veya üye kaydı bulunamadı'}), 404

                res = process_borrow_transaction(kiosk_request.book, kiosk_request.member, 'kiosk-approved', 'Kiosk talebi admin tarafından onaylandı')
                # Response tuple/objesi ayrımı
                if isinstance(res, tuple):
                    resp_obj, status_code = res
                else:
                    resp_obj, status_code = res, 200
                payload = None
                try:
                    payload = resp_obj.get_json()
                except Exception:
                    payload = None
                if not payload or not payload.get('success'):
                    # Orijinal yanıt/Status ile döndür (hata mesajı korunur)
                    return resp_obj, status_code

            # Başarılı ise talebi tamamlandı yap
            kiosk_request.status = 'completed'
            kiosk_request.approved_by = 1  # Use default user ID for EXE
            kiosk_request.approved_at = datetime.utcnow()
            db.session.commit()

            log_activity('kiosk_request_approved', f'Kiosk talebi onaylandı: ID {request_id}')
            # Sistem genel bildirim tablosuna bilgi notu düş
            try:
                add_notification('kiosk_approved', f'Kiosk talebi onaylandı: "{kiosk_request.book.title}"')
            except Exception:
                pass

            return jsonify({'success': True, 'message': 'Talep onaylandı ve işlem gerçekleştirildi'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @app.route('/api/admin/kiosk-request/<int:request_id>/reject', methods=['POST'])
    # Authentication removed for EXE compatibility
    def kiosk_admin_reject_request(request_id):
        """Admin: Kiosk talebini reddet"""
        try:
            data = request.json or {}
            reason = data.get('reason', 'Sebep belirtilmedi.')

            kiosk_request = KioskRequest.query.get(request_id)
            if not kiosk_request:
                return jsonify({'success': False, 'message': 'Talep bulunamadı'}), 404
            
            if kiosk_request.status != 'pending':
                return jsonify({'success': False, 'message': 'Bu talep zaten işlenmiş'}), 400

            kiosk_request.status = 'rejected'
            kiosk_request.approved_by = 1  # Use default user ID for EXE
            kiosk_request.approved_at = datetime.utcnow()
            kiosk_request.notes = f"Reddedildi: {reason}"
            db.session.commit()
            
            log_activity('kiosk_request_rejected', f'Kiosk talebi reddedildi: ID {request_id}')
            try:
                add_notification('kiosk_rejected', f'Kiosk talebi reddedildi: "{kiosk_request.book.title}" • {reason}')
            except Exception:
                pass
            
            return jsonify({'success': True, 'message': 'Talep reddedildi'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500
    
    print("✅ Kiosk API route'ları kaydedildi!")
