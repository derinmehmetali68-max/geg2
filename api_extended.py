from flask import request, jsonify, send_file
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
import tempfile
import os
import json
import secrets
from io import BytesIO
# from logging_system import library_logger, log_performance  # Removed - module doesn't exist
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
import qrcode
import shutil
import subprocess
import sys
from uuid import uuid4

from config import app, get_setting
from models import db, User, Book, Member, Transaction, Category, BookCategory, Notification, SearchHistory, Review, Reservation, Fine, ActivityLog, Settings, EmailTemplate, OnlineBorrowRequest, QRCode, KioskRequest
from utils import (log_activity, send_email, add_notification, generate_qr_code, 
                   save_qr_code, process_borrow_transaction, process_return_transaction,
                   generate_books_qr_pdf, generate_members_qr_pdf, export_to_excel,
                   process_online_borrow_request, approve_online_borrow_request,
                   reject_online_borrow_request, get_inventory_summary, get_member_statistics,
                   quick_search_books, quick_search_members, generate_user_qr, verify_qr_code, use_qr_code,
                   generate_books_list_pdf, generate_members_list_pdf, generate_transactions_list_pdf,
                   normalize_cover_url, fuzzy_match_books, fuzzy_match_members, 
                   merge_duplicate_books, merge_duplicate_members, generate_shelf_map_pdf, 
                   generate_label_templates_pdf)
from routes import role_required

# Notifications API
@app.route('/api/notifications')
def api_get_notifications():
    """Get all notifications"""
    unread_only = request.args.get('unread_only', 'false') == 'true'
    
    query = Notification.query
    if unread_only:
        query = query.filter_by(is_read=0)
    
    notifications = query.order_by(Notification.created_date.desc()).all()
    
    notifications_data = []
    for notif in notifications:
        notifications_data.append({
            'id': notif.id,
            'type': notif.type,
            'message': notif.message,
            'created_date': notif.created_date,
            'is_read': notif.is_read,
            'related_isbn': notif.related_isbn
        })
    
    return jsonify({'notifications': notifications_data})

@app.route('/api/notifications/<int:id>/read', methods=['POST'])
def api_mark_notification_read(id):
    """Mark notification as read"""
    notification = Notification.query.get_or_404(id)
    notification.is_read = 1
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/api/notifications/mark-all-read', methods=['POST'])
# Authentication removed for EXE compatibility
def api_mark_all_notifications_read():
    """Mark all notifications as read"""
    Notification.query.filter_by(is_read=0).update({'is_read': 1})
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/notifications/<int:id>', methods=['DELETE'])
# Authentication removed for EXE compatibility
def api_delete_notification(id):
    """Delete a notification"""
    notification = Notification.query.get_or_404(id)
    db.session.delete(notification)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/notifications/clear-all', methods=['DELETE'])
# Authentication removed for EXE compatibility
def api_clear_all_notifications():
    """Clear all notifications"""
    Notification.query.delete()
    db.session.commit()
    return jsonify({'success': True})

# Reservations API
@app.route('/api/reservations/<int:id>/cancel', methods=['POST'])
# Authentication removed for EXE compatibility
def api_cancel_reservation(id):
    """Cancel a reservation"""
    reservation = Reservation.query.get_or_404(id)
    
    # Skip user ownership check for EXE compatibility
    # if reservation.user_id != current_user.id:
    #     return jsonify({'success': False, 'message': 'Bu rezervasyon size ait değil'}), 403
    
    # Check if already cancelled
    if reservation.status != 'active':
        return jsonify({'success': False, 'message': 'Bu rezervasyon zaten aktif değil'}), 400
    
    # Cancel reservation
    reservation.status = 'cancelled'
    
    # Update queue positions for other reservations
    other_reservations = Reservation.query.filter(
        Reservation.isbn == reservation.isbn,
        Reservation.status == 'active',
        Reservation.queue_position > reservation.queue_position
    ).all()
    
    for res in other_reservations:
        res.queue_position -= 1
    
    db.session.commit()
    
    log_activity('cancel_reservation', f'Cancelled reservation {id}')
    
    return jsonify({'success': True, 'message': 'Rezervasyon iptal edildi'})

# Fines API
@app.route('/api/fines/<int:id>/pay', methods=['POST'])
# Authentication removed for EXE compatibility
def api_pay_fine(id):
    """Pay a fine"""
    fine = Fine.query.get_or_404(id)
    
    # Skip user ownership check for EXE compatibility
    # if fine.user_id != current_user.id:
    #     return jsonify({'success': False, 'message': 'Bu ceza size ait değil'}), 403
    
    if fine.status == 'paid':
        return jsonify({'success': False, 'message': 'Bu ceza zaten ödenmiş'}), 400
    
    fine.status = 'paid'
    fine.paid_date = datetime.utcnow()
    db.session.commit()
    
    log_activity('pay_fine', f'Paid fine {id}')
    
    return jsonify({'success': True, 'message': 'Ceza ödendi'})

# Settings API
@app.route('/api/settings', methods=['POST'])
# Authentication removed for EXE compatibility
def api_update_settings():
    """Update system settings"""
    for key, value in request.json.items():
        setting = Settings.query.filter_by(key=key).first()
        if setting:
            setting.value = value
            setting.updated_at = datetime.utcnow()
        else:
            setting = Settings(key=key, value=value)
            db.session.add(setting)
    
    db.session.commit()
    log_activity('update_settings', 'System settings updated')
    
    return jsonify({'success': True, 'message': 'Ayarlar güncellendi'})

# Users Management API
@app.route('/api/users/<int:id>/toggle-active', methods=['POST'])
# Authentication removed for EXE compatibility
def api_toggle_user_active(id):
    """Toggle user active status"""
    user = User.query.get_or_404(id)
    
    # Skip self-check for EXE compatibility
    # if user.id == current_user.id:
    #     return jsonify({'success': False, 'message': 'Kendi hesabınızı devre dışı bırakamazsınız'}), 400
    
    user.is_active = not user.is_active
    db.session.commit()
    
    log_activity('toggle_user', f'Toggled user {user.username} active status to {user.is_active}')
    
    return jsonify({'success': True, 'is_active': user.is_active})

@app.route('/api/users', methods=['POST'])
# Authentication removed for EXE compatibility
def api_create_user():
    """Create new user"""
    data = request.json
    
    # Validate data
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'success': False, 'message': 'Bu kullanıcı adı zaten kullanılıyor'}), 400
    
    if User.query.filter_by(email=data['email']).first():
        return jsonify({'success': False, 'message': 'Bu e-posta adresi zaten kayıtlı'}), 400
    
    try:
        user = User(
            username=data['username'],
            email=data['email'],
            role=data.get('role', 'user')
        )
        user.set_password(data['password'])
        db.session.add(user)
        db.session.commit()
        
        log_activity('create_user', f'Created user: {user.username}')
        
        return jsonify({'success': True, 'message': 'Kullanıcı oluşturuldu'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/users/<int:id>', methods=['PUT'])
# Authentication removed for EXE compatibility
def api_update_user(id):
    """Update user information"""
    user = User.query.get_or_404(id)
    data = request.json
    
    # Update email if changed
    if 'email' in data and data['email'] != user.email:
        if User.query.filter(User.email == data['email'], User.id != id).first():
            return jsonify({'success': False, 'message': 'Bu e-posta adresi zaten kullanılıyor'}), 400
        user.email = data['email']
    
    # Update role
    if 'role' in data:
        user.role = data['role']
    
    # Update password if provided
    if 'password' in data and data['password']:
        user.set_password(data['password'])
    
    db.session.commit()
    log_activity('update_user', f'Updated user: {user.username}')
    
    return jsonify({'success': True, 'message': 'Kullanıcı güncellendi'})

@app.route('/api/users/<int:id>', methods=['DELETE'])
# Authentication removed for EXE compatibility
def api_delete_user(id):
    """Delete user"""
    user = User.query.get_or_404(id)
    
    # Skip self-check for EXE compatibility
    # if user.id == current_user.id:
    #     return jsonify({'success': False, 'message': 'Kendi hesabınızı silemezsiniz'}), 400
    
    username = user.username
    db.session.delete(user)
    db.session.commit()
    
    log_activity('delete_user', f'Deleted user: {username}')
    
    return jsonify({'success': True, 'message': 'Kullanıcı silindi'})

@app.route('/api/users/<int:id>/activity')
# Authentication removed for EXE compatibility
def api_user_activity(id):
    """Get user activity logs"""
    activities = ActivityLog.query.filter_by(user_id=id)\
        .order_by(ActivityLog.timestamp.desc()).limit(50).all()
    
    activities_data = []
    for activity in activities:
        activities_data.append({
            'timestamp': activity.timestamp.isoformat(),
            'action': activity.action,
            'details': activity.details,
            'ip_address': activity.ip_address
        })
    
    return jsonify({'activities': activities_data})

# Email Templates API
@app.route('/api/email-templates/<int:id>', methods=['PUT'])
# Authentication removed for EXE compatibility
def api_update_email_template(id):
    """Update email template"""
    template = EmailTemplate.query.get_or_404(id)
    data = request.json
    
    template.subject = data.get('subject', template.subject)
    template.body = data.get('body', template.body)
    template.is_active = data.get('is_active', template.is_active)
    
    db.session.commit()
    log_activity('update_email_template', f'Updated template: {template.name}')
    
    return jsonify({'success': True, 'message': 'E-posta şablonu güncellendi'})

# Backup and Restore API
@app.route('/api/backup/create', methods=['POST'])
# Authentication removed for EXE compatibility
def api_create_backup():
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
        
        return jsonify({
            'success': True,
            'message': 'Yedekleme başarıyla oluşturuldu',
            'filename': backup_filename
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/backup/download/<filename>')
# Authentication removed for EXE compatibility
def api_download_backup(filename):
    """Download backup file"""
    backup_dir = 'backups'
    filepath = os.path.join(backup_dir, filename)
    
    if os.path.exists(filepath) and filename.endswith('.db'):
        return send_file(filepath, as_attachment=True, download_name=filename)
    else:
        return jsonify({'error': 'Backup file not found'}), 404

@app.route('/api/backup/restore/<filename>', methods=['POST'])
# Authentication removed for EXE compatibility
def api_restore_backup(filename):
    """Restore database from backup"""
    try:
        backup_dir = 'backups'
        backup_path = os.path.join(backup_dir, filename)
        
        if not os.path.exists(backup_path) or not filename.endswith('.db'):
            return jsonify({'success': False, 'message': 'Yedek dosyası bulunamadı'}), 404
        
        # Veritabanı bağlantılarını kapat
        try:
            db.session.close()
            db.engine.dispose()
        except:
            pass
        
        # Mevcut veritabanını yedekle
        try:
            shutil.copy2('instance/books_info.db', f'instance/books_info_before_restore_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db')
        except:
            pass
        
        # Yedeği geri yükle
        shutil.copy2(backup_path, 'instance/books_info.db')
        
        log_activity('restore_backup', f'Restored from backup: {filename}')
        
        return jsonify({
            'success': True,
            'message': 'Veritabanı başarıyla geri yüklendi. Sayfayı yenileyin.'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Geri yükleme hatası: {str(e)}'}), 500

@app.route('/api/backup/delete/<filename>', methods=['POST', 'DELETE'])
# Authentication removed for EXE compatibility
def api_delete_backup(filename):
    """Delete backup file"""
    try:
        backup_dir = 'backups'
        filepath = os.path.join(backup_dir, filename)
        
        if os.path.exists(filepath) and filename.endswith('.db'):
            os.remove(filepath)
            log_activity('delete_backup', f'Deleted backup: {filename}')
            return jsonify({'success': True, 'message': 'Yedek silindi'})
        else:
            return jsonify({'success': False, 'message': 'Yedek dosyası bulunamadı'}), 404
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# Export/Import Additional APIs
@app.route('/api/export/members', methods=['GET'])
def api_export_members():
    """Export members to Excel"""
    # Excel export temporarily disabled - pandas dependency removed
    return jsonify({'success': False, 'message': 'Excel export özelliği geçici olarak devre dışı'}), 501

@app.route('/api/import/members', methods=['POST'])
# @log_performance  # Removed - decorator doesn't exist
def api_import_members():
    """Import members from Excel - Gelişmiş Versiyon"""
    # Excel import temporarily disabled - pandas dependency removed
    return jsonify({'success': False, 'message': 'Excel import özelliği geçici olarak devre dışı'}), 501

@app.route('/api/logs', methods=['GET'])
# Authentication removed for EXE compatibility
def api_get_logs():
    """Sistem loglarını getir"""
    
    # Skip role check for EXE compatibility
    # if current_user.role != 'admin':
    #     return jsonify({'success': False, 'message': 'Yetkisiz erişim'}), 403
    
    count = int(request.args.get('count', 100))
    level = request.args.get('level', None)
    
    # logs = library_logger.get_recent_logs(count=count, level=level)  # Removed - library_logger doesn't exist
    logs = []  # Return empty logs
    
    return jsonify({
        'success': True,
        'logs': logs,
        'total': len(logs)
    })

@app.route('/api/logs/download', methods=['GET'])
# Authentication removed for EXE compatibility
def api_download_logs():
    """Log dosyasını indir"""
    
    # Skip role check for EXE compatibility
    # if current_user.role != 'admin':
    #     return jsonify({'success': False, 'message': 'Yetkisiz erişim'}), 403
    
    log_type = request.args.get('type', 'system')  # system, errors, imports
    
    log_files = {
        'system': 'logs/system.log',
        'errors': 'logs/errors.log',
        'imports': 'logs/imports.log'
    }
    
    if log_type not in log_files:
        return jsonify({'success': False, 'message': 'Geçersiz log tipi'}), 400
    
    log_file = log_files[log_type]
    
    if not os.path.exists(log_file):
        return jsonify({'success': False, 'message': 'Log dosyası bulunamadı'}), 404
    
    return send_file(log_file, as_attachment=True, download_name=f'{log_type}_logs.log')

@app.route('/api/system/stats', methods=['GET'])
# Authentication removed for EXE compatibility
def api_system_stats():
    """Sistem istatistiklerini getir"""
    
    # Skip role check for EXE compatibility
    # if current_user.role != 'admin':
    #     return jsonify({'success': False, 'message': 'Yetkisiz erişim'}), 403
    
    # Veritabanı istatistikleri
    stats = {
        'database': {
            'total_books': Book.query.count(),
            'total_members': Member.query.count(),
            'total_transactions': Transaction.query.count(),
            'active_transactions': Transaction.query.filter_by(return_date=None).count()
        },
        'recent_logs': {
            'total': 0,  # library_logger not available
            'errors': 0,  # library_logger not available
            'warnings': 0  # library_logger not available
        },
        'file_sizes': {}
    }
    
    # Log dosyası boyutları
    log_files = ['logs/system.log', 'logs/errors.log', 'logs/imports.log']
    for log_file in log_files:
        if os.path.exists(log_file):
            size = os.path.getsize(log_file)
            stats['file_sizes'][log_file] = {
                'bytes': size,
                'mb': round(size / 1024 / 1024, 2)
            }
    
    return jsonify({
        'success': True,
        'stats': stats
    })

@app.route('/api/export/transactions', methods=['GET'])
def api_export_transactions():
    """Export transactions to Excel"""
    # Excel export temporarily disabled - pandas dependency removed
    return jsonify({'success': False, 'message': 'Excel export özelliği geçici olarak devre dışı'}), 501

# Bulk QR and PDF generation APIs
@app.route('/api/members/qr-bulk')
# Authentication removed for EXE compatibility
def api_members_qr_bulk():
    members = Member.query.all()
    buffer = generate_members_qr_pdf(members)
    return send_file(buffer, as_attachment=True, download_name='uyeler_qr.pdf', mimetype='application/pdf')

@app.route('/api/books/qr-bulk', methods=['GET', 'POST'])
# Authentication removed for EXE compatibility
def api_books_qr_bulk():
    if request.method == 'POST':
        isbns = request.form.get('isbns')
        if isbns:
            isbns = json.loads(isbns)
            books = Book.query.filter(Book.isbn.in_(isbns)).all()
        else:
            books = Book.query.all()
    else:
        books = Book.query.all()
    
    buffer = generate_books_qr_pdf(books)
    return send_file(buffer, as_attachment=True, download_name='kitaplar_qr.pdf', mimetype='application/pdf')

@app.route('/api/books/pdf-bulk', methods=['GET', 'POST'])
# Authentication removed for EXE compatibility
def api_books_pdf_bulk():
    if request.method == 'POST':
        isbns = request.form.get('isbns')
        if isbns:
            isbns = json.loads(isbns)
            books = Book.query.filter(Book.isbn.in_(isbns)).all()
        else:
            books = Book.query.all()
    else:
        books = Book.query.all()
    
    data = []
    for book in books:
        borrowed = Transaction.query.filter_by(isbn=book.isbn, return_date=None).count()
        data.append({
            'ISBN': book.isbn,
            'Kitap Adı': book.title,
            'Yazar': book.authors,
            'Yayınevi': book.publishers,
            'Mevcut/Toplam': f"{book.quantity - borrowed}/{book.quantity}"
        })
    
    temp_file = export_to_excel(data, 'Kitaplar')
    return send_file(temp_file, as_attachment=True, download_name='kitaplar_liste.xlsx', 
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/api/members/pdf-bulk', methods=['GET', 'POST'])
# Authentication removed for EXE compatibility
def api_members_pdf_bulk():
    if request.method == 'POST':
        ids = request.form.get('ids')
        if ids:
            ids = json.loads(ids)
            members = Member.query.filter(Member.id.in_(ids)).all()
        else:
            members = Member.query.all()
    else:
        members = Member.query.all()
    
    data = []
    for m in members:
        data.append({
            'Ad Soyad': m.ad_soyad,
            'Numara': m.numara,
            'Sınıf': m.sinif,
            'E-posta': m.email,
            'Üye Türü': m.uye_turu
        })
    
    temp_file = export_to_excel(data, 'Üyeler')
    return send_file(temp_file, as_attachment=True, download_name='uyeler_liste.xlsx', 
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

# Inventory APIs
@app.route('/api/inventory/summary')
# Authentication removed for EXE compatibility
def api_inventory_summary():
    summary = get_inventory_summary()
    return jsonify(summary)

@app.route('/api/inventory/pdf')
# Authentication removed for EXE compatibility
def api_inventory_pdf():
    # Excel export temporarily disabled - pandas dependency removed
    return jsonify({'success': False, 'message': 'Excel export özelliği geçici olarak devre dışı'}), 501

@app.route('/api/inventory/member-stats')
# Authentication removed for EXE compatibility
def api_inventory_member_stats():
    stats = get_member_statistics()
    return jsonify(stats)

@app.route('/api/inventory/members-pdf')
# Authentication removed for EXE compatibility
def api_inventory_members_pdf():
    # Excel export temporarily disabled - pandas dependency removed
    return jsonify({'success': False, 'message': 'Excel export özelliği geçici olarak devre dışı'}), 501

# Online Borrow APIs - Continue from line 880 onwards
# [Rest of the file content remains the same from line 880 to the end]
