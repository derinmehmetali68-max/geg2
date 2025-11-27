from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

# Create db instance here to avoid circular imports
db = SQLAlchemy()

# Database Models
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200))
    role = db.Column(db.String(20), default='user')  # admin, librarian, user
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    theme = db.Column(db.String(20), default='light')
    language = db.Column(db.String(10), default='tr')
    
    # Relationships
    reviews = db.relationship('Review', backref='reviewer', lazy='dynamic')
    reservations = db.relationship('Reservation', backref='reserver', lazy='dynamic')
    fines = db.relationship('Fine', backref='user', lazy='dynamic')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def has_role(self, role):
        return self.role == role

class Book(db.Model):
    __tablename__ = 'books'
    isbn = db.Column(db.String(20), primary_key=True)
    title = db.Column(db.Text)
    authors = db.Column(db.Text)
    publish_date = db.Column(db.Text)
    number_of_pages = db.Column(db.Integer)
    publishers = db.Column(db.Text)
    languages = db.Column(db.Text)
    quantity = db.Column(db.Integer, default=1)
    shelf = db.Column(db.Text)
    cupboard = db.Column(db.Text)
    image_path = db.Column(db.Text)
    cover_image = db.Column(db.LargeBinary)
    last_borrowed_date = db.Column(db.Text)
    total_borrow_count = db.Column(db.Integer, default=0)
    qr_code = db.Column(db.Text)  # QR code path
    barcode = db.Column(db.String(50))
    edition = db.Column(db.String(50))
    description = db.Column(db.Text)
    average_rating = db.Column(db.Float, default=0.0)
    review_count = db.Column(db.Integer, default=0)
    category = db.Column(db.String(100))  # Kategori alanı eklendi
    
    # Relationships
    reviews = db.relationship('Review', backref='book', lazy='dynamic')
    reservations = db.relationship('Reservation', backref='book', lazy='dynamic')
    categories = db.relationship('Category', secondary='book_categories', backref='books')

class Member(db.Model):
    __tablename__ = 'members'
    id = db.Column(db.Integer, primary_key=True)
    ad_soyad = db.Column(db.Text)
    sinif = db.Column(db.Text)
    numara = db.Column(db.Text)
    email = db.Column(db.Text)
    uye_turu = db.Column(db.Text)
    notification_preferences = db.Column(db.Text)
    phone = db.Column(db.String(20))
    address = db.Column(db.Text)
    profile_image = db.Column(db.String(200))
    join_date = db.Column(db.DateTime, default=datetime.utcnow)
    total_borrowed = db.Column(db.Integer, default=0)
    current_borrowed = db.Column(db.Integer, default=0)
    reliability_score = db.Column(db.Float, default=100.0)  # 0-100
    penalty_until = db.Column(db.DateTime)  # Ceza bitiş tarihi
    
    # Relationships
    user = db.relationship('User', backref='member_profile', uselist=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True)
    isbn = db.Column(db.String(20), db.ForeignKey('books.isbn'))
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'))
    borrow_date = db.Column(db.Text)
    due_date = db.Column(db.Text)
    return_date = db.Column(db.Text)
    renew_count = db.Column(db.Integer, default=0)
    fine_amount = db.Column(db.Float, default=0.0)
    condition_on_borrow = db.Column(db.String(50), default='good')  # good, fair, poor
    condition_on_return = db.Column(db.String(50))
    notes = db.Column(db.Text)
    
    # Relationships
    book = db.relationship('Book', backref='transactions')
    member = db.relationship('Member', backref='transactions')

class KioskRequest(db.Model):
    __tablename__ = 'kiosk_requests'
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'))
    isbn = db.Column(db.String(20), db.ForeignKey('books.isbn'))
    request_type = db.Column(db.String(20))  # 'borrow', 'return'
    status = db.Column(db.String(20), default='pending')  # 'pending', 'approved', 'rejected', 'completed'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved_at = db.Column(db.DateTime)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    notes = db.Column(db.Text)
    session_token = db.Column(db.String(255))
    
    # Relationships
    member = db.relationship('Member', backref='kiosk_requests')
    book = db.relationship('Book', backref='kiosk_requests')
    approver = db.relationship('User', backref='approved_requests')

class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, unique=True)
    description = db.Column(db.Text)

class BookCategory(db.Model):
    __tablename__ = 'book_categories'
    book_isbn = db.Column(db.String(20), db.ForeignKey('books.isbn'), primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), primary_key=True)

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.Text)
    message = db.Column(db.Text)
    created_date = db.Column(db.Text)
    is_read = db.Column(db.Integer, default=0)
    related_isbn = db.Column(db.String(20), db.ForeignKey('books.isbn'))

class SearchHistory(db.Model):
    __tablename__ = 'search_history'
    id = db.Column(db.Integer, primary_key=True)
    search_term = db.Column(db.Text)
    search_date = db.Column(db.Text)
    result_count = db.Column(db.Integer)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

class Review(db.Model):
    __tablename__ = 'reviews'
    id = db.Column(db.Integer, primary_key=True)
    isbn = db.Column(db.String(20), db.ForeignKey('books.isbn'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    rating = db.Column(db.Integer)  # 1-5
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    helpful_count = db.Column(db.Integer, default=0)
    
class Reservation(db.Model):
    __tablename__ = 'reservations'
    id = db.Column(db.Integer, primary_key=True)
    isbn = db.Column(db.String(20), db.ForeignKey('books.isbn'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'))
    reservation_date = db.Column(db.DateTime, default=datetime.utcnow)
    expiry_date = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='active')  # active, fulfilled, cancelled, expired
    queue_position = db.Column(db.Integer)
    notification_sent = db.Column(db.Boolean, default=False)
    
class Fine(db.Model):
    __tablename__ = 'fines'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'))
    transaction_id = db.Column(db.Integer, db.ForeignKey('transactions.id'))
    amount = db.Column(db.Float)
    reason = db.Column(db.String(100))  # late_return, damaged, lost
    created_date = db.Column(db.DateTime, default=datetime.utcnow)
    paid_date = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='unpaid')  # unpaid, paid, waived
    
class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    action = db.Column(db.String(100))
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
class Settings(db.Model):
    __tablename__ = 'settings'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True)
    value = db.Column(db.Text)
    description = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class EmailTemplate(db.Model):
    __tablename__ = 'email_templates'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True)
    subject = db.Column(db.String(200))
    body = db.Column(db.Text)
    variables = db.Column(db.Text)  # JSON list of available variables
    is_active = db.Column(db.Boolean, default=True)

class OnlineBorrowRequest(db.Model):
    __tablename__ = 'online_borrow_requests'
    id = db.Column(db.Integer, primary_key=True)
    isbn = db.Column(db.String(20), db.ForeignKey('books.isbn'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'))
    pickup_date = db.Column(db.String(20))  # YYYY-MM-DD formatında
    pickup_time = db.Column(db.String(10))  # HH:MM formatında
    notes = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected, cancelled
    rejection_reason = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved_at = db.Column(db.DateTime)
    approved_by = db.Column(db.String(80))
    
    # Relationships
    book = db.relationship('Book', backref='online_requests')
    user = db.relationship('User', backref='online_requests')
    member = db.relationship('Member', backref='online_requests')

class QRCode(db.Model):
    __tablename__ = 'qrcodes'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    token = db.Column(db.String(64), unique=True)
    expiry_time = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='active')  # active, used, expired
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    used_at = db.Column(db.DateTime)
    
    # Relationships
    user = db.relationship('User', backref='qr_codes')
