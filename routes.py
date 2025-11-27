from flask import render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta
from functools import wraps
import re
import os

from config import app, get_setting
from models import db, User, Book, Member, Transaction, Category, BookCategory, Notification, SearchHistory, Review, Reservation, Fine, ActivityLog, Settings, EmailTemplate, OnlineBorrowRequest, QRCode
from utils import log_activity, save_qr_code, send_email, normalize_text_tr, compute_relevance_score

# Role required decorator
def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or not current_user.has_role(role):
                flash('Bu işlem için yetkiniz yok.', 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Authentication Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember', False)
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password) and user.is_active:
            login_user(user, remember=remember)
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            log_activity('login', f'User {username} logged in')
            
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('Geçersiz kullanıcı adı veya şifre', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    if current_user.is_authenticated:
        log_activity('logout', f'User {current_user.username} logged out')
        logout_user()
    return redirect(url_for('index'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validation
        if User.query.filter_by(username=username).first():
            flash('Bu kullanıcı adı zaten kullanılıyor', 'danger')
        elif User.query.filter_by(email=email).first():
            flash('Bu e-posta adresi zaten kayıtlı', 'danger')
        elif password != confirm_password:
            flash('Şifreler eşleşmiyor', 'danger')
        elif len(password) < 6:
            flash('Şifre en az 6 karakter olmalıdır', 'danger')
        else:
            user = User(
                username=username,
                email=email,
                role='user'
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            
            log_activity('register', f'New user registered: {username}')
            
            # Send welcome email
            send_email(email, 'welcome', {
                'member_name': username,
                'member_id': user.id,
                'join_date': datetime.now().strftime('%d.%m.%Y')
            })
            
            flash('Kayıt başarılı! Giriş yapabilirsiniz.', 'success')
            return redirect(url_for('login'))
    
    return render_template('register.html')

# Main Routes
@app.route('/')
def index():
    """Home page with statistics"""
    total_books = db.session.query(db.func.sum(Book.quantity)).scalar() or 0
    distinct_books = Book.query.count()
    total_members = Member.query.count()
    borrowed_books = Transaction.query.filter_by(return_date=None).count()
    available_books = total_books - borrowed_books
    
    # Additional statistics
    today_transactions = Transaction.query.filter(
        db.func.date(Transaction.borrow_date) == datetime.now().date()
    ).count()
    
    overdue_books = db.session.query(Transaction).filter(
        Transaction.return_date == None,
        Transaction.due_date < datetime.now().strftime("%Y-%m-%d")
    ).count()
    
    active_reservations = Reservation.query.filter_by(status='active').count()
    total_users = User.query.filter_by(is_active=True).count()
    
    # Popular books
    popular_books = db.session.query(
        Book.isbn, Book.title, Book.authors, Book.total_borrow_count
    ).order_by(Book.total_borrow_count.desc()).limit(5).all()
    
    # Recent activities
    recent_activities = ActivityLog.query.order_by(
        ActivityLog.timestamp.desc()
    ).limit(10).all()
    
    return render_template('index.html',
                         total_books=total_books,
                         distinct_books=distinct_books,
                         available_books=available_books,
                         total_members=total_members,
                         today_transactions=today_transactions,
                         overdue_books=overdue_books,
                         active_reservations=active_reservations,
                         total_users=total_users,
                         popular_books=popular_books,
                         recent_activities=recent_activities)

@app.route('/books')
def books():
    """Books page"""
    categories = Category.query.all()
    return render_template('books.html', categories=categories)

@app.route('/test')
def test():
    """Test page for debugging"""
    return render_template('test.html')

@app.route('/book/<isbn>')
def book_detail(isbn):
    """Book detail page with reviews and QR code"""
    book = Book.query.get_or_404(isbn)
    
    # Get book categories
    categories = db.session.query(Category.name).join(BookCategory)\
        .filter(BookCategory.book_isbn == isbn).all()
    categories = [cat[0] for cat in categories]
    
    # Get availability info
    borrowed_count = Transaction.query.filter_by(isbn=isbn, return_date=None).count()
    available_count = book.quantity - borrowed_count
    
    # Get reviews
    reviews = Review.query.filter_by(isbn=isbn)\
        .order_by(Review.created_at.desc()).all()
    
    # Generate or get QR code
    if not book.qr_code:
        book.qr_code = save_qr_code(isbn)
        db.session.commit()
    
    # Check if user has already reviewed
    user_review = None
    if current_user.is_authenticated:
        user_review = Review.query.filter_by(
            isbn=isbn, user_id=current_user.id
        ).first()
    
    # Check if user can borrow (has active membership)
    can_borrow = False
    if current_user.is_authenticated:
        member = Member.query.filter_by(user_id=current_user.id).first()
        if member:
            # Check if user hasn't exceeded max books
            active_borrows = Transaction.query.filter_by(
                member_id=member.id, return_date=None
            ).count()
            max_books = int(get_setting('max_books_per_member', '5'))
            can_borrow = active_borrows < max_books and available_count > 0
    
    log_activity('view_book', f'Viewed book: {book.title}')
    
    return render_template('book_detail.html',
                         book=book,
                         categories=categories,
                         available_count=available_count,
                         borrowed_count=borrowed_count,
                         reviews=reviews,
                         user_review=user_review,
                         can_borrow=can_borrow)

@app.route('/dashboard')
def dashboard():
    """Admin dashboard with statistics"""
    # Basic stats
    stats = {
        'total_books': db.session.query(db.func.sum(Book.quantity)).scalar() or 0,
        'distinct_books': Book.query.count(),
        'active_members': Member.query.count(),
        'new_members_month': Member.query.filter(
            Member.join_date >= datetime.now() - timedelta(days=30)
        ).count(),
        'borrowed_books': Transaction.query.filter_by(return_date=None).count(),
        'overdue_books': Transaction.query.filter(
            Transaction.return_date == None,
            Transaction.due_date < datetime.now().strftime("%Y-%m-%d")
        ).count(),
        'monthly_transactions': Transaction.query.filter(
            Transaction.borrow_date >= (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        ).count(),
        'daily_average': 0
    }
    
    stats['daily_average'] = round(stats['monthly_transactions'] / 30, 1)
    
    # Monthly chart data
    monthly_data = []
    for i in range(11, -1, -1):
        month_start = (datetime.now() - timedelta(days=i*30)).strftime("%Y-%m")
        borrows = Transaction.query.filter(
            Transaction.borrow_date.like(f"{month_start}%")
        ).count()
        returns = Transaction.query.filter(
            Transaction.return_date.like(f"{month_start}%")
        ).count()
        monthly_data.append({
            'month': month_start,
            'borrows': borrows,
            'returns': returns
        })
    
    monthly_labels = [d['month'] for d in monthly_data]
    monthly_borrows = [d['borrows'] for d in monthly_data]
    monthly_returns = [d['returns'] for d in monthly_data]
    
    # Category distribution
    category_data = db.session.query(
        Category.name, db.func.count(BookCategory.book_isbn)
    ).join(BookCategory).group_by(Category.name).all()
    
    category_labels = [c[0] for c in category_data]
    category_counts = [c[1] for c in category_data]
    
    # Popular books
    popular_books = db.session.query(
        Book.isbn, Book.title, Book.authors, Book.average_rating,
        db.func.count(Transaction.id).label('borrow_count')
    ).join(Transaction).filter(
        Transaction.borrow_date >= (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    ).group_by(Book.isbn).order_by(db.text('borrow_count DESC')).limit(10).all()
    
    # None rating'leri 0'a çevir
    popular_books_fixed = []
    for b in popular_books:
        popular_books_fixed.append(type('BookObj', (), {
            'isbn': b.isbn,
            'title': b.title,
            'authors': b.authors,
            'rating': b.average_rating if b.average_rating is not None else 0,
            'borrow_count': b.borrow_count
        }))
    
    # Active members
    active_members = db.session.query(
        Member.id, Member.ad_soyad.label('name'), Member.sinif.label('class'),
        Member.reliability_score.label('reliability'),
        db.func.count(Transaction.id).label('borrow_count')
    ).join(Transaction).filter(
        Transaction.borrow_date >= (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    ).group_by(Member.id).order_by(db.text('borrow_count DESC')).limit(10).all()
    
    # Recent activities
    recent_activities = []
    activities = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(20).all()
    
    for activity in activities:
        time_diff = datetime.utcnow() - activity.timestamp
        if time_diff.days > 0:
            time_ago = f"{time_diff.days} gün önce"
        elif time_diff.seconds > 3600:
            time_ago = f"{time_diff.seconds // 3600} saat önce"
        elif time_diff.seconds > 60:
            time_ago = f"{time_diff.seconds // 60} dakika önce"
        else:
            time_ago = "Az önce"
        
        icon = 'circle'
        if 'login' in activity.action:
            icon = 'box-arrow-in-right'
        elif 'book' in activity.action:
            icon = 'book'
        elif 'member' in activity.action:
            icon = 'person'
        elif 'borrow' in activity.action or 'return' in activity.action:
            icon = 'arrow-left-right'
        
        recent_activities.append({
            'action': activity.action,
            'details': activity.details,
            'user': User.query.get(activity.user_id).username if activity.user_id else 'System',
            'time_ago': time_ago,
            'icon': icon
        })
    
    return render_template('dashboard.html',
                         stats=stats,
                         monthly_labels=monthly_labels,
                         monthly_borrows=monthly_borrows,
                         monthly_returns=monthly_returns,
                         category_labels=category_labels,
                         category_data=category_counts,
                         popular_books=popular_books_fixed,
                         active_members=active_members,
                         recent_activities=recent_activities)

@app.route('/profile')
def profile():
    """User profile page"""
    user_id = current_user.id if current_user.is_authenticated else 1
    member = Member.query.filter_by(user_id=user_id).first()
    
    # Get user statistics
    stats = {
        'total_borrowed': 0,
        'current_borrowed': 0,
        'total_reviews': 0,
        'total_reservations': 0,
        'total_fines': 0,
        'unpaid_fines': 0
    }
    
    if member:
        stats['total_borrowed'] = Transaction.query.filter_by(member_id=member.id).count()
        stats['current_borrowed'] = Transaction.query.filter_by(
            member_id=member.id, return_date=None
        ).count()
    
    stats['total_reviews'] = Review.query.filter_by(user_id=user_id).count()
    stats['total_reservations'] = Reservation.query.filter_by(user_id=user_id).count()
    
    fines = Fine.query.filter_by(user_id=user_id).all()
    stats['total_fines'] = sum(f.amount for f in fines)
    stats['unpaid_fines'] = sum(f.amount for f in fines if f.status == 'unpaid')
    
    # Recent activity
    recent_activity = ActivityLog.query.filter_by(user_id=user_id)\
        .order_by(ActivityLog.timestamp.desc()).limit(10).all()
    
    return render_template('profile.html',
                         member=member,
                         stats=stats,
                         recent_activity=recent_activity)

@app.route('/my-books')
def my_books():
    """User's borrowed books"""
    user_id = current_user.id if current_user.is_authenticated else 1
    member = Member.query.filter_by(user_id=user_id).first()
    if not member:
        flash('Henüz üyelik kaydınız oluşturulmamış', 'warning')
        return redirect(url_for('profile'))
    
    # Current books with enhanced data
    current_books_query = db.session.query(Transaction, Book).join(Book)\
        .filter(Transaction.member_id == member.id, Transaction.return_date == None)\
        .order_by(Transaction.due_date).all()
    
    # Process current books with additional calculations
    current_books_data = []
    for transaction, book in current_books_query:
        # Calculate days left
        due_date = datetime.strptime(transaction.due_date, '%Y-%m-%d')
        today = datetime.now()
        days_left = (due_date.date() - today.date()).days
        
        # Check if can renew
        max_renew = int(get_setting('max_renew_count', '2'))
        can_renew = transaction.renew_count < max_renew and not transaction.return_date
        
        current_books_data.append({
            'transaction': transaction,
            'book': book,
            'days_left': days_left,
            'can_renew': can_renew,
            'is_overdue': days_left < 0
        })
    
    # History
    history = db.session.query(Transaction, Book).join(Book)\
        .filter(Transaction.member_id == member.id, Transaction.return_date != None)\
        .order_by(Transaction.return_date.desc()).limit(20).all()
    
    return render_template('my_books.html',
                         current_books=current_books_data,
                         history=history)

@app.route('/my-reservations')
def my_reservations():
    """User's book reservations"""
    user_id = current_user.id if current_user.is_authenticated else 1
    reservations = db.session.query(Reservation, Book).join(Book)\
        .filter(Reservation.user_id == user_id)\
        .order_by(Reservation.reservation_date.desc()).all()
    
    return render_template('my_reservations.html', reservations=reservations)

@app.route('/my-fines')
def my_fines():
    """User's fines"""
    user_id = current_user.id if current_user.is_authenticated else 1
    fines = db.session.query(Fine, Transaction, Book)\
        .join(Transaction, Fine.transaction_id == Transaction.id)\
        .join(Book, Transaction.isbn == Book.isbn)\
        .filter(Fine.user_id == user_id)\
        .order_by(Fine.created_date.desc()).all()
    
    total_unpaid = sum(f[0].amount for f in fines if f[0].status == 'unpaid')
    
    return render_template('my_fines.html', 
                         fines=fines,
                         total_unpaid=total_unpaid)

@app.route('/search')
def search():
    """Global search page"""
    query = request.args.get('q', '')
    search_type = request.args.get('type', 'all')
    page = request.args.get('page', 1, type=int)
    title_only = request.args.get('title_only', '0') == '1'
    
    def normalize_isbn(isbn):
        return re.sub(r'[^0-9Xx]', '', isbn or '')
    
    results = {
        'books': [],
        'members': [],
        'total': 0
    }
    
    if query:
        # Log search
        if current_user.is_authenticated:
            search_log = SearchHistory(
                search_term=query,
                search_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                user_id=current_user.id
            )
            db.session.add(search_log)
        
        # Search books - geliştirilmiş alaka ve filtreleme
        if search_type in ['all', 'books']:
            norm_query = normalize_isbn(query)
            # Ön eleme (DB)
            base = Book.query
            like_q = f"%{query}%"
            isbn_like = f"%{norm_query}%" if norm_query else like_q
            if title_only:
                base = base.filter(Book.title.ilike(like_q))
            else:
                base = base.filter(
                    db.or_(
                        Book.title.ilike(like_q),
                        Book.authors.ilike(like_q),
                        db.func.replace(db.func.replace(Book.isbn, '-', ''), ' ', '').like(isbn_like),
                        Book.publishers.ilike(like_q)
                    )
                )
            candidates = base.limit(500).all()

            # Alaka puanı hesapla ve filtrele
            scored = []
            nq = normalize_text_tr(query)
            # Dinamik eşik: daha uzun sorgu -> daha yüksek eşik
            q_len = len(nq)
            if q_len >= 9:
                threshold = 65
            elif q_len >= 6:
                threshold = 55
            elif q_len >= 3:
                threshold = 45
            else:
                threshold = 0

            # Token bazlı zorlama: tüm temel token'lar başlıkta geçsin (2+ karakterli tokenlar)
            tokens = [t for t in nq.split(' ') if len(t) >= 2]

            for book in candidates:
                title_n = normalize_text_tr(book.title)
                # Token şartı (yalnızca title_only açıkken sıkı uygula)
                if title_only and tokens and not all(tok in title_n for tok in tokens):
                    continue

                score = compute_relevance_score(query, book.title, book.authors, book.publishers)
                # ISBN tam eşleşme bonusu
                if norm_query and normalize_isbn(book.isbn) == norm_query:
                    score += 200
                if score < threshold:
                    continue
                borrowed = Transaction.query.filter_by(isbn=book.isbn, return_date=None).count()
                available = (book.quantity or 0) - borrowed
                scored.append((score, book, available))

            scored.sort(key=lambda x: x[0], reverse=True)

            # Sayfalama (manuel)
            per_page = 20
            start = (page - 1) * per_page
            end = start + per_page
            page_items = scored[start:end]

            for _, book, available in page_items:
                results['books'].append({'book': book, 'available': available})

            results['total'] += len(scored)
        
        # Search members (only for admins/librarians)
        if search_type in ['all', 'members'] and current_user.is_authenticated \
           and current_user.role in ['admin', 'librarian']:
            members = Member.query.filter(
                db.or_(
                    Member.ad_soyad.contains(query),
                    Member.numara.contains(query),
                    Member.email.contains(query)
                )
            ).all()
            
            results['members'] = members
            results['total'] += len(members)
        
        # Update search history result count
        if current_user.is_authenticated:
            search_log.result_count = results['total']
            db.session.commit()
    
    # Kategorileri gelişmiş arama için ilet
    categories = Category.query.all()
    current_year = datetime.now().year

    return render_template('search.html',
                         query=query,
                         search_type=search_type,
                         results=results,
                         categories=categories,
                         current_year=current_year)

@app.route('/members')
def members():
    """Members page"""
    return render_template('members.html')

@app.route('/transactions')
def transactions():
    """Transactions page"""
    return render_template('transactions.html')

@app.route('/notifications')
def notifications():
    """Notifications page"""
    return render_template('notifications.html')

@app.route('/charts')
def charts():
    """Otomasyon grafikleri sayfası"""
    return render_template('charts.html')

@app.route('/reports')
def reports():
    """Reports page"""
    # Get date range from query params
    start_date = request.args.get('start_date', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date', datetime.now().strftime('%Y-%m-%d'))
    
    # Most borrowed books
    most_borrowed = db.session.query(
        Book.isbn, Book.title, Book.authors,
        db.func.count(Transaction.id).label('borrow_count')
    ).join(Transaction).filter(
        Transaction.borrow_date >= start_date,
        Transaction.borrow_date <= end_date
    ).group_by(Book.isbn).order_by(db.text('borrow_count DESC')).limit(10).all()
    
    # Most active members
    most_active = db.session.query(
        Member.id, Member.ad_soyad,
        db.func.count(Transaction.id).label('transaction_count')
    ).join(Transaction).filter(
        Transaction.borrow_date >= start_date,
        Transaction.borrow_date <= end_date
    ).group_by(Member.id).order_by(db.text('transaction_count DESC')).limit(10).all()
    
    # Category statistics
    category_stats = db.session.query(
        Category.name,
        db.func.count(db.distinct(Transaction.isbn)).label('book_count')
    ).join(BookCategory, Category.id == BookCategory.category_id)\
     .join(Book, BookCategory.book_isbn == Book.isbn)\
     .join(Transaction, Book.isbn == Transaction.isbn)\
     .filter(
        Transaction.borrow_date >= start_date,
        Transaction.borrow_date <= end_date
     ).group_by(Category.name).all()
    
    # Daily transactions
    daily_stats = db.session.query(
        db.func.date(Transaction.borrow_date).label('date'),
        db.func.count(Transaction.id).label('count')
    ).filter(
        Transaction.borrow_date >= start_date,
        Transaction.borrow_date <= end_date
    ).group_by(db.func.date(Transaction.borrow_date)).all()
    
    return render_template('reports.html',
                         start_date=start_date,
                         end_date=end_date,
                         most_borrowed=most_borrowed,
                         most_active=most_active,
                         category_stats=category_stats,
                         daily_stats=daily_stats)

@app.route('/settings')
def settings():
    """System settings page"""
    settings = Settings.query.all()
    email_templates = EmailTemplate.query.all()
    return render_template('settings.html', settings=settings, email_templates=email_templates)

@app.route('/users')
def users():
    """User management page"""
    users = User.query.all()
    return render_template('users.html', users=users)

@app.route('/backup')
def backup():
    """Database backup page"""
    backup_dir = 'backups'
    backups = []
    
    if os.path.exists(backup_dir):
        for filename in os.listdir(backup_dir):
            if filename.endswith('.db'):
                filepath = os.path.join(backup_dir, filename)
                backups.append({
                    'filename': filename,
                    'size': os.path.getsize(filepath),
                    'created': datetime.fromtimestamp(os.path.getctime(filepath))
                })
    
    backups.sort(key=lambda x: x['created'], reverse=True)
    return render_template('backup.html', backups=backups)

@app.route('/members/<int:id>')
def member_detail(id):
    member = Member.query.get_or_404(id)
    return render_template('member_detail.html', member=member)

@app.route('/inventory')
def inventory():
    return render_template('inventory.html')

@app.route('/shelf-map')
def shelf_map():
    return render_template('shelf_map.html')

@app.route('/kiosk-mode')
@app.route('/advanced-kiosk')
def kiosk_mode():
    """Gelişmiş Kiosk Sistemi - QR tarama + online ödünç + rezervasyon"""
    return render_template('advanced_kiosk.html')

@app.route('/kiosk-requests')
def kiosk_requests():
    """Admin: Kiosk Talepleri Yönetimi"""
    return render_template('kiosk_requests.html')



@app.route('/online-borrow')
def online_borrow():
    """Online & QR ödünç alma sayfası"""
    return render_template('online_borrow.html')

@app.route('/online-borrow-requests')
def online_borrow_requests():
    """Admin paneli - Online ödünç alma talepleri"""
    return render_template('online_borrow_requests.html')

@app.route('/my-online-requests')
def my_online_requests():
    """Kullanıcının kendi online talepleri"""
    return render_template('my_online_requests.html')

@app.route('/qr-borrow')
def qr_borrow():
    """QR kod ile ödünç alma sayfası"""
    return render_template('qr_borrow.html')

@app.route('/self-check')
def self_check():
    """Self-check cihazı arayüzü"""
    return render_template('self_check.html')

@app.route('/mobile-app')
def mobile_app():
    """Mobil uygulama bilgi sayfası"""
    return render_template('mobile_app.html')

@app.route('/mobile-qr-scanner')
def mobile_qr_scanner():
    """Mobil QR kod tarayıcı sayfası"""
    return render_template('mobile_qr_scanner.html')
