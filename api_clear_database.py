#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API endpoint for clearing database
Railway'de veritabanını temizlemek için API endpoint
"""

from flask import Blueprint, jsonify, request
from config import app, init_database
from models import db, User, Book, Member, Transaction, Category, Settings, Notification, EmailTemplate, Reservation, OnlineBorrowRequest

clear_db_bp = Blueprint('clear_db', __name__)

@clear_db_bp.route('/api/admin/clear-database', methods=['POST'])
def api_clear_database():
    """Admin - Clear entire database and recreate with default data"""
    try:
        # Security check - require confirmation
        data = request.json or {}
        confirm = data.get('confirm', False)
        secret = data.get('secret', '')
        
        # Secret key check (use SECRET_KEY from environment)
        import os
        expected_secret = os.environ.get('SECRET_KEY', '')
        
        if not confirm:
            return jsonify({
                'success': False, 
                'message': 'İşlem onaylanmadı. confirm: true gönderin.'
            }), 400
        
        if secret != expected_secret:
            return jsonify({
                'success': False, 
                'message': 'Geçersiz secret key'
            }), 403
        
        with app.app_context():
            # Count records before deletion
            book_count = Book.query.count()
            member_count = Member.query.count()
            transaction_count = Transaction.query.count()
            user_count = User.query.count() - 1  # Exclude admin user
            
            print(f"🗑️  Veritabanı temizleniyor...")
            print(f"   - {book_count} kitap")
            print(f"   - {member_count} üye")
            print(f"   - {transaction_count} işlem")
            print(f"   - {user_count} kullanıcı")
            
            # Drop all tables
            db.drop_all()
            print("✅ Tüm tablolar silindi")
            
            # Recreate tables
            db.create_all()
            print("✅ Tablolar yeniden oluşturuldu")
            
            # Add default data
            print("📝 Default veriler ekleniyor...")
            init_database()
            print("✅ Default veriler eklendi")
            
            return jsonify({
                'success': True,
                'message': 'Veritabanı başarıyla temizlendi',
                'deleted': {
                    'books': book_count,
                    'members': member_count,
                    'transactions': transaction_count,
                    'users': user_count
                }
            })
            
    except Exception as e:
        db.session.rollback()
        import traceback
        error_msg = str(e)
        traceback.print_exc()
        return jsonify({
            'success': False, 
            'message': f'Veritabanı temizleme hatası: {error_msg}'
        }), 500

