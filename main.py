import sys
import os
import requests
import pandas as pd
import sqlite3
import tempfile
from datetime import datetime, timedelta

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QMessageBox, QFileDialog,
    QLineEdit, QProgressBar, QDialog, QFormLayout, QDialogButtonBox, QSpinBox,
    QTabWidget, QToolBar, QAction, QAbstractScrollArea, QComboBox, QGroupBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QPixmap

###############################################################################
# Bildirim Sistemi
###############################################################################
class NotificationSystem:
    def __init__(self, db_connection):
        self.conn = db_connection
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_notifications)
        self.timer.start(3600000)  # Her saat başı kontrol et

    def add_notification(self, type, message, related_isbn=None):
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO notifications (type, message, created_date, related_isbn)
                VALUES (?, ?, ?, ?)
            """, (type, message, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), related_isbn))
            self.conn.commit()
        except Exception as e:
            print(f"Bildirim ekleme hatası: {e}")

    def check_notifications(self):
        try:
            cursor = self.conn.cursor()
            # İade tarihi yaklaşan kitapları kontrol et
            cursor.execute("""
                SELECT t.id, t.isbn, t.member_id, t.due_date, b.title, m.ad_soyad
                FROM transactions t
                JOIN books b ON t.isbn = b.isbn
                JOIN members m ON t.member_id = m.id
                WHERE t.return_date IS NULL
                AND t.due_date <= date('now', '+3 days')
                AND t.due_date >= date('now')
            """)
            upcoming_returns = cursor.fetchall()
            
            for return_info in upcoming_returns:
                trans_id, isbn, member_id, due_date, title, member_name = return_info
                message = f"'{title}' kitabı {member_name} tarafından {due_date} tarihine kadar iade edilmelidir."
                self.add_notification("return_reminder", message, isbn)

            # Geciken kitapları kontrol et
            cursor.execute("""
                SELECT t.id, t.isbn, t.member_id, t.due_date, b.title, m.ad_soyad
                FROM transactions t
                JOIN books b ON t.isbn = b.isbn
                JOIN members m ON t.member_id = m.id
                WHERE t.return_date IS NULL
                AND t.due_date < date('now')
            """)
            overdue_books = cursor.fetchall()
            
            for overdue in overdue_books:
                trans_id, isbn, member_id, due_date, title, member_name = overdue
                message = f"'{title}' kitabı {member_name} tarafından {due_date} tarihinden beri gecikmiştir."
                self.add_notification("overdue", message, isbn)

        except Exception as e:
            print(f"Bildirim kontrolü hatası: {e}")

    def get_unread_notifications(self):
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM notifications
                WHERE is_read = 0
                ORDER BY created_date DESC
            """)
            return cursor.fetchall()
        except Exception as e:
            print(f"Bildirim okuma hatası: {e}")
            return []

    def mark_as_read(self, notification_id):
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE notifications
                SET is_read = 1
                WHERE id = ?
            """, (notification_id,))
            self.conn.commit()
        except Exception as e:
            print(f"Bildirim güncelleme hatası: {e}")

class NotificationDialog(QDialog):
    def __init__(self, notifications, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bildirimler")
        self.notifications = notifications
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        if not self.notifications:
            label = QLabel("Yeni bildirim yok.")
            layout.addWidget(label)
        else:
            for notif in self.notifications:
                notif_id, type, message, created_date, is_read, related_isbn = notif
                group = QGroupBox(f"{created_date}")
                group_layout = QVBoxLayout()
                
                message_label = QLabel(message)
                message_label.setWordWrap(True)
                group_layout.addWidget(message_label)
                
                if related_isbn:
                    view_button = QPushButton("Kitabı Görüntüle")
                    view_button.clicked.connect(lambda checked, isbn=related_isbn: self.view_book(isbn))
                    group_layout.addWidget(view_button)
                
                group.setLayout(group_layout)
                layout.addWidget(group)
        
        close_button = QPushButton("Kapat")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)
        
        self.setLayout(layout)
        self.resize(400, 300)

    def view_book(self, isbn):
        try:
            cursor = self.parent().conn.cursor()
            cursor.execute("SELECT * FROM books WHERE isbn = ?", (isbn,))
            book_data = cursor.fetchone()
            if book_data:
                book_info = {
                    "ISBN": book_data[0],
                    "Başlık": book_data[1],
                    "Yazar": book_data[2],
                    "Yayın Yılı": book_data[3],
                    "Sayfa Sayısı": book_data[4],
                    "Yayınevi": book_data[5],
                    "Diller": book_data[6],
                    "Raf": book_data[8],
                    "Dolap": book_data[9],
                    "Resim": book_data[10]
                }
                dialog = LibraryDialog(book_info, self)
                dialog.exec_()
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Kitap bilgisi görüntüleme hatası: {e}")

###############################################################################
# Gelişmiş Arama Diyalogu
###############################################################################
class AdvancedSearchDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gelişmiş Arama")
        self.init_ui()

    def init_ui(self):
        layout = QFormLayout(self)

        # Arama kriterleri
        self.title_input = QLineEdit()
        self.author_input = QLineEdit()
        self.publisher_input = QLineEdit()
        self.year_from = QSpinBox()
        self.year_to = QSpinBox()
        self.year_from.setRange(1800, 2100)
        self.year_to.setRange(1800, 2100)
        self.year_from.setValue(1800)
        self.year_to.setValue(2100)

        # Kategori seçimi
        self.category_combo = QComboBox()
        try:
            # parent() çağrısı ISBNApp örneğini verir, bu da conn'e erişim sağlar
            if self.parent() and hasattr(self.parent(), 'conn'):
                cursor = self.parent().conn.cursor()
                cursor.execute("SELECT name FROM categories ORDER BY name")
                categories = cursor.fetchall()
                self.category_combo.addItem("Tüm Kategoriler", None)
                for category in categories:
                    self.category_combo.addItem(category[0], category[0])
            else:
                print("Kategori yükleme için veritabanı bağlantısı kurulamadı.")
        except Exception as e:
            print(f"Kategori yükleme hatası: {e}")

        # Arama geçmişi
        self.history_combo = QComboBox()
        try:
            if self.parent() and hasattr(self.parent(), 'conn'):
                cursor = self.parent().conn.cursor()
                cursor.execute("""
                    SELECT DISTINCT search_term 
                    FROM search_history 
                    ORDER BY search_date DESC 
                    LIMIT 10
                """)
                history = cursor.fetchall()
                self.history_combo.addItem("Arama Geçmişi", None)
                for term in history:
                    self.history_combo.addItem(term[0], term[0])
            else:
                print("Arama geçmişi için veritabanı bağlantısı kurulamadı.")
        except Exception as e:
            print(f"Arama geçmişi yükleme hatası: {e}")

        # Form elemanlarını ekle
        layout.addRow("Başlık:", self.title_input)
        layout.addRow("Yazar:", self.author_input)
        layout.addRow("Yayınevi:", self.publisher_input)
        layout.addRow("Yıl Aralığı:", QHBoxLayout())
        h_layout = layout.itemAt(layout.rowCount()-1).layout()
        if h_layout is not None:
            h_layout.addWidget(self.year_from)
            h_layout.addWidget(QLabel(" - "))
            h_layout.addWidget(self.year_to)
        layout.addRow("Kategori:", self.category_combo)
        layout.addRow("Arama Geçmişi:", self.history_combo)

        # Butonlar
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_search_criteria(self):
        return {
            "title": self.title_input.text().strip(),
            "author": self.author_input.text().strip(),
            "publisher": self.publisher_input.text().strip(),
            "year_from": self.year_from.value(),
            "year_to": self.year_to.value(),
            "category": self.category_combo.currentData()
        }

###############################################################################
# Kategori Yönetimi Diyalogu
###############################################################################
class CategoryDialog(QDialog):
    def __init__(self, book_isbn=None, parent=None):
        super().__init__(parent)
        self.book_isbn = book_isbn
        self.setWindowTitle("Kategori Yönetimi")
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Kategori listesi
        self.category_list = QTableWidget()
        self.category_list.setColumnCount(2)
        self.category_list.setHorizontalHeaderLabels(["Kategori", "Seçili"])
        self.category_list.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.category_list)

        # Kategorileri yükle
        try:
            if self.parent() and hasattr(self.parent(), 'conn'):
                cursor = self.parent().conn.cursor()
                cursor.execute("SELECT id, name FROM categories ORDER BY name")
                categories = cursor.fetchall()
                
                # Seçili kategorileri al
                selected_categories = []
                if self.book_isbn:
                    cursor.execute("""
                        SELECT category_id 
                        FROM book_categories 
                        WHERE book_isbn = ?
                    """, (self.book_isbn,))
                    selected_categories = [row[0] for row in cursor.fetchall()]

                # Kategorileri tabloya ekle
                self.category_list.setRowCount(len(categories))
                for i, (cat_id, cat_name) in enumerate(categories):
                    self.category_list.setItem(i, 0, QTableWidgetItem(cat_name))
                    checkbox = QTableWidgetItem()
                    checkbox.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                    checkbox.setCheckState(Qt.Checked if cat_id in selected_categories else Qt.Unchecked)
                    self.category_list.setItem(i, 1, checkbox)
            else:
                print("Kategori listesi için veritabanı bağlantısı kurulamadı.")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Kategori yükleme hatası: {e}")

        # Butonlar
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_selected_categories(self):
        selected = []
        for row in range(self.category_list.rowCount()):
            if self.category_list.item(row, 1).checkState() == Qt.Checked:
                selected.append(self.category_list.item(row, 0).text())
        return selected

###############################################################################
# İşlem Giriş Diyalogu (ISBN ve Okul No ile)
###############################################################################
class TransactionInputDialog(QDialog):
    def __init__(self, title="İşlem Bilgileri", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.init_ui()

    def init_ui(self):
        layout = QFormLayout(self)

        self.isbn_input = QLineEdit()
        self.school_no_input = QLineEdit()

        layout.addRow("Kitap ISBN:", self.isbn_input)
        layout.addRow("Üye Okul Numarası:", self.school_no_input)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addRow(self.buttons)

    def get_data(self):
        return {
            "isbn": self.isbn_input.text().strip(),
            "school_no": self.school_no_input.text().strip()
        }

###############################################################################
# 1) Arka plan thread ile ISBN verisi + kapak resmi çekme
###############################################################################
class FetchThread(QThread):
    progress = pyqtSignal(int)
    result = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, isbns):
        super().__init__()
        self.isbns = isbns

    def run(self):
        """
        Open Library API'den kitap bilgisi ve varsa kapak resmi URL'si çekilir.
        """
        books_info = []
        total = len(self.isbns)
        try:
            isbn_query = ','.join([f"ISBN:{isbn}" for isbn in self.isbns])
            url = f"https://openlibrary.org/api/books?bibkeys={isbn_query}&format=json&jscmd=data"
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            for idx, isbn in enumerate(self.isbns):
                key = f"ISBN:{isbn}"
                if key in data:
                    book = data[key]
                    book_info = {
                        "ISBN": isbn,
                        "Başlık": book.get("title", "N/A"),
                        "Yazar": ", ".join([author['name'] for author in book.get("authors", [])]) or "N/A",
                        "Yayın Yılı": book.get("publish_date", "N/A"),
                        "Sayfa Sayısı": book.get("number_of_pages", "N/A"),
                        "Yayınevi": ", ".join([publisher['name'] for publisher in book.get("publishers", [])]) or "N/A",
                        "Diller": ", ".join([lang['key'].split('/')[-1] for lang in book.get("languages", [])]) if book.get("languages") else "N/A",
                        "Resim": "",
                        "Adet": 1  # Varsayılan adet değeri
                    }
                    # Kapak resmi (cover) bilgisi
                    if "cover" in book:
                        image_url = book["cover"].get("large") or book["cover"].get("medium") or None
                        if image_url:
                            try:
                                img_resp = requests.get(image_url, stream=True, timeout=5)
                                img_resp.raise_for_status()
                                tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                                tmp_file.write(img_resp.content)
                                tmp_file.flush()
                                tmp_file.close()
                                book_info["Resim"] = tmp_file.name
                            except:
                                pass
                else:
                    # API'de bilgi yoksa
                    book_info = {
                        "ISBN": isbn,
                        "Başlık": "Bilgi Bulunamadı",
                        "Yazar": "Bilgi Bulunamadı",
                        "Yayın Yılı": "Bilgi Bulunamadı",
                        "Sayfa Sayısı": "Bilgi Bulunamadı",
                        "Yayınevi": "Bilgi Bulunamadı",
                        "Diller": "Bilgi Bulunamadı",
                        "Resim": "",
                        "Adet": 1  # Varsayılan adet değeri
                    }
                books_info.append(book_info)
                self.progress.emit(int(((idx + 1) / total) * 100))
            self.result.emit(books_info)
        except requests.exceptions.RequestException as e:
            self.error.emit(str(e))

###############################################################################
# 2) Kütüphane Diyalogu: Kitap Detayı (Resim büyük göster)
###############################################################################
class LibraryDialog(QDialog):
    def __init__(self, book_info, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kitap Bilgileri")
        self.book_info = book_info
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Resim gösterme
        if self.book_info["Resim"] and os.path.exists(self.book_info["Resim"]):
            pixmap = QPixmap(self.book_info["Resim"])
            pixmap = pixmap.scaled(500, 700, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.image_label = QLabel()
            self.image_label.setPixmap(pixmap)
        else:
            self.image_label = QLabel("Resim Yok")
            self.image_label.setAlignment(Qt.AlignCenter)
            self.image_label.setFixedSize(300, 400)

        layout.addWidget(self.image_label)

        # Bilgi formu
        form = QFormLayout()
        info_fields = [
            ("ISBN", "ISBN"),
            ("Başlık", "Başlık"),
            ("Yazar", "Yazar"),
            ("Yayın Yılı", "Yayın Yılı"),
            ("Sayfa Sayısı", "Sayfa Sayısı"),
            ("Yayınevi", "Yayınevi"),
            ("Diller", "Diller"),
            ("Kategoriler", "Kategoriler"),
            ("Raf", "Raf"),
            ("Dolap", "Dolap")
        ]

        for label, key in info_fields:
            val = str(self.book_info.get(key, "N/A"))
            lab = QLabel(val)
            lab.setWordWrap(True)
            form.addRow(f"{label}:", lab)

        layout.addLayout(form)

        # Kapat butonu
        close_btn = QPushButton("Kapat")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self.setLayout(layout)

###############################################################################
# 3) Kütüphane Güncelleme Diyalogu: Tüm alanları düzenleme
###############################################################################
class LibraryUpdateDialog(QDialog):
    """
    Kütüphane sekmesinde 'Kitap Güncelle' dediğimizde açılan diyalog.
    ISBN, Başlık, Yazar, Yayınevi, Yayın Yılı, Sayfa, Raf, Dolap, Diller, Resim 
    gibi alanlar burada düzenlenebilir.
    """
    def __init__(self, book_info, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kitap Güncelle (Tüm Alanlar)")
        self.book_info = book_info
        self.init_ui()

    def init_ui(self):
        layout = QFormLayout(self)

        # ISBN (readonly olsun, primary key - genelde değişmez)
        self.isbn_input = QLineEdit(self.book_info.get("ISBN", ""))
        self.isbn_input.setReadOnly(True)

        self.title_input = QTextEdit(self.book_info.get("Başlık", ""))
        self.title_input.setFixedHeight(40)

        self.authors_input = QTextEdit(self.book_info.get("Yazar", ""))
        self.authors_input.setFixedHeight(40)

        self.publish_date_input = QLineEdit(self.book_info.get("Yayın Yılı", ""))

        # Sayfa sayısı int
        self.pages_input = QSpinBox()
        self.pages_input.setMaximum(100000)
        try:
            self.pages_input.setValue(int(self.book_info.get("Sayfa Sayısı", 0)))
        except:
            self.pages_input.setValue(0)

        self.publishers_input = QTextEdit(self.book_info.get("Yayınevi", ""))
        self.publishers_input.setFixedHeight(40)

        self.languages_input = QTextEdit(self.book_info.get("Diller", ""))
        self.languages_input.setFixedHeight(40)

        self.shelf_input = QLineEdit(self.book_info.get("Raf", ""))
        self.cupboard_input = QLineEdit(self.book_info.get("Dolap", ""))

        # Resim
        self.image_input = QLineEdit()
        self.image_input.setText(self.book_info.get("Resim", ""))
        self.image_input.setReadOnly(True)
        self.browse_image_button = QPushButton("Gözat")
        self.browse_image_button.clicked.connect(self.browse_image)

        layout.addRow("ISBN:", self.isbn_input)
        layout.addRow("Başlık:", self.title_input)
        layout.addRow("Yazar:", self.authors_input)
        layout.addRow("Yayın Yılı:", self.publish_date_input)
        layout.addRow("Sayfa Sayısı:", self.pages_input)
        layout.addRow("Yayınevi:", self.publishers_input)
        layout.addRow("Diller:", self.languages_input)
        layout.addRow("Raf:", self.shelf_input)
        layout.addRow("Dolap:", self.cupboard_input)

        # Resim satırı
        img_layout = QHBoxLayout()
        img_layout.addWidget(self.image_input)
        img_layout.addWidget(self.browse_image_button)
        layout.addRow("Resim:", img_layout)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addRow(self.buttons)

        self.setLayout(layout)

    def browse_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Resim Seç", "",
            "Resim Dosyaları (*.png *.jpg *.jpeg *.bmp);;Tüm Dosyalar (*)"
        )
        if file_path:
            self.image_input.setText(file_path)

    def get_updated_info(self):
        return {
            "ISBN": self.isbn_input.text(),  # Normalde değişmeyen alan
            "Başlık": self.title_input.toPlainText(),
            "Yazar": self.authors_input.toPlainText(),
            "Yayın Yılı": self.publish_date_input.text(),
            "Sayfa Sayısı": self.pages_input.value(),
            "Yayınevi": self.publishers_input.toPlainText(),
            "Diller": self.languages_input.toPlainText(),
            "Raf": self.shelf_input.text(),
            "Dolap": self.cupboard_input.text(),
            "Resim": self.image_input.text()
        }

###############################################################################
# 4) Üye Ekle/Güncelle Diyalogu
###############################################################################
class MemberDialog(QDialog):
    def __init__(self, member_info, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Üye Bilgileri")
        self.member_info = member_info  # This is a dictionary
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        self.form_layout = QFormLayout()

        # Define which fields are editable and their order
        self.editable_fields_config = [
            ("Ad Soyad", "ad_soyad"),
            ("Sınıf", "sinif"),
            ("Numara", "numara"),
            ("E-posta", "email"),
            ("Üye Türü", "uye_turu") # Consider QComboBox for predefined values
        ]

        self.input_widgets = {}

        # Add ID if viewing/editing existing member
        if self.member_info.get("ID"):
            self.form_layout.addRow("ID:", QLabel(str(self.member_info.get("ID", "N/A"))))

        for label_text, key in self.editable_fields_config:
            input_widget = QLineEdit(str(self.member_info.get(key, "")))
            self.form_layout.addRow(f"{label_text}:", input_widget)
            self.input_widgets[key] = input_widget
        
        # Display-only fields for existing members
        if self.member_info.get("ID"): # Check if it's an existing member
            display_only_fields = [
                ("Kayıt Tarihi", "Kayıt Tarihi"),
                ("Son İşlem", "Son İşlem"),
                ("Aktif Ödünç", "Aktif Ödünç"),
                ("Toplam Ödünç", "Toplam Ödünç")
            ]
            for label, d_key in display_only_fields:
                val = str(self.member_info.get(d_key, "N/A"))
                lab = QLabel(val)
                lab.setWordWrap(True)
                self.form_layout.addRow(f"{label}:", lab)

        layout.addLayout(self.form_layout)

        # Buttons
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.setLayout(layout)

    def get_input_data(self):
        data = {}
        for key, widget in self.input_widgets.items():
            data[key] = widget.text().strip()
        return data

###############################################################################
# 5) Ana Uygulama Penceresi
###############################################################################
class ISBNApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ISBN Kitap Bilgisi Çekici ve Kütüphane Yönetimi")
        self.setGeometry(100, 100, 1600, 900)

        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # Araç Çubuğu (ToolBar)
        self.toolbar = QToolBar("Araç Çubuğu")
        self.toolbar.setMovable(False)
        main_layout.addWidget(self.toolbar)

        # Veritabanını yedekle/geri yükle aksiyonları
        backup_action = QAction("Veritabanını Yedekle", self)
        backup_action.triggered.connect(self.backup_database)
        self.toolbar.addAction(backup_action)

        restore_action = QAction("Veritabanını Geri Yükle", self)
        restore_action.triggered.connect(self.restore_database)
        self.toolbar.addAction(restore_action)

        # Sekmeler
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # Anasayfa Sekmesi
        self.init_home_tab()

        # Veri Çekme Sekmesi
        self.fetch_tab = QWidget()
        self.tabs.addTab(self.fetch_tab, "Veri Çekme")

        # Kütüphane Sekmesi
        self.library_tab = QWidget()
        self.tabs.addTab(self.library_tab, "Kütüphane")

        # Üyeler Sekmesi
        self.members_tab = QWidget()
        self.tabs.addTab(self.members_tab, "Üyeler")

        # İşlemler Sekmesi
        self.transactions_tab = QWidget()
        self.tabs.addTab(self.transactions_tab, "İşlemler")

        # Veritabanı bağlantısı
        self.conn = sqlite3.connect('books_info.db')
        self.create_tables()

        # Sekmeleri başlat
        self.init_fetch_tab()
        self.init_library_tab()
        self.init_members_tab()
        self.init_transactions_tab()

        # Başlangıçta verileri yükle
        self.load_data_from_db()
        self.load_members_from_db()
        self.load_transactions_from_db()
        self.update_member_count_label()

        # Bildirim sistemi
        self.notification_system = NotificationSystem(self.conn)
        
        # Bildirim action'ı (Toolbar için)
        self.notification_action = QAction("Bildirimler", self)
        self.notification_action.triggered.connect(self.show_notifications)
        self.toolbar.addAction(self.notification_action)
        
        # Bildirim kontrolü için timer
        self.notification_timer = QTimer()
        self.notification_timer.timeout.connect(self.check_notifications)
        self.notification_timer.start(300000)  # 5 dakikada bir kontrol et

    ###########################################################################
    # ANASAYFA SEKMESİ
    ###########################################################################
    def init_home_tab(self):
        self.home_tab = QWidget()
        layout = QVBoxLayout(self.home_tab)

        # Hoşgeldiniz etiketi
        welcome_label = QLabel("Cumhuriyet Anadolu Lisesi Kütüphanesine Hoşgeldiniz")
        font = welcome_label.font()
        font.setPointSize(26)  
        font.setBold(True)
        welcome_label.setFont(font)
        layout.addWidget(welcome_label, alignment=Qt.AlignCenter)

        # Toplam Kitap Sayısı etiketi
        self.total_books_label = QLabel("Toplam Kitap Sayısı: 0")
        font2 = self.total_books_label.font()
        font2.setPointSize(18)
        self.total_books_label.setFont(font2)
        layout.addWidget(self.total_books_label, alignment=Qt.AlignCenter)

        # Toplam Farklı Kitap Sayısı etiketi
        self.distinct_books_label = QLabel("Toplam Farklı Kitap Sayısı: 0")
        self.distinct_books_label.setFont(font2)
        layout.addWidget(self.distinct_books_label, alignment=Qt.AlignCenter)

        # Mevcut Kitap Sayısı etiketi
        self.available_books_label = QLabel("Mevcut Kitap Sayısı: 0")
        self.available_books_label.setFont(font2)
        layout.addWidget(self.available_books_label, alignment=Qt.AlignCenter)

        # Toplam Üye Sayısı etiketi
        self.total_members_label = QLabel("Toplam Üye Sayısı: 0")
        self.total_members_label.setFont(font2)
        layout.addWidget(self.total_members_label, alignment=Qt.AlignCenter)

        # Tarih/Saat etiketi
        self.datetime_label = QLabel("Tarih/Saat: -")
        self.datetime_label.setFont(font2)
        layout.addWidget(self.datetime_label, alignment=Qt.AlignCenter)

        self.tabs.addTab(self.home_tab, "Anasayfa")

        # Tarih/Saat güncellemek için timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_datetime)
        self.timer.start(1000)  # 1 saniyede bir günceller

    def update_datetime(self):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.datetime_label.setText(f"Tarih/Saat: {now}")

    def update_member_count_label(self):
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM members")
            total = cursor.fetchone()[0]
            self.total_members_label.setText(f"Toplam Üye Sayısı: {total}")
        except:
            pass

    ###########################################################################
    # Veritabanı Oluşturma
    ###########################################################################
    def create_tables(self):
        cursor = self.conn.cursor()

        # Categories tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                description TEXT
            )
        """)

        # Book Categories tablosu (kitap-kategori ilişkisi)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS book_categories (
                book_isbn TEXT,
                category_id INTEGER,
                PRIMARY KEY (book_isbn, category_id),
                FOREIGN KEY (book_isbn) REFERENCES books(isbn),
                FOREIGN KEY (category_id) REFERENCES categories(id)
            )
        """)

        # Books tablosu güncelleme
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS books (
                isbn TEXT PRIMARY KEY,
                title TEXT,
                authors TEXT,
                publish_date TEXT,
                number_of_pages INTEGER,
                publishers TEXT,
                languages TEXT,
                quantity INTEGER DEFAULT 1,
                shelf TEXT,
                cupboard TEXT,
                image_path TEXT,
                cover_image BLOB,
                last_borrowed_date TEXT,
                total_borrow_count INTEGER DEFAULT 0
            )
        """)

        # Notifications tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT,
                message TEXT,
                created_date TEXT,
                is_read INTEGER DEFAULT 0,
                related_isbn TEXT,
                FOREIGN KEY (related_isbn) REFERENCES books(isbn)
            )
        """)

        # Search History tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                search_term TEXT,
                search_date TEXT,
                result_count INTEGER
            )
        """)

        # Members tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ad_soyad TEXT,
                sinif TEXT,
                numara TEXT,
                email TEXT,
                uye_turu TEXT,
                notification_preferences TEXT
            )
        """)

        # Transactions tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                isbn TEXT,
                member_id INTEGER,
                borrow_date TEXT,
                due_date TEXT,
                return_date TEXT,
                FOREIGN KEY(isbn) REFERENCES books(isbn),
                FOREIGN KEY(member_id) REFERENCES members(id)
            )
        """)

        # Varsayılan kategorileri ekle
        default_categories = [
            ("Türk Edebiyatı", "Türk edebiyatı eserleri"),
            ("Yabancı Edebiyat", "Yabancı edebiyat eserleri"),
            ("Şiir", "Şiir kitapları"),
            ("Hikaye", "Hikaye kitapları"),
            ("Roman", "Roman türündeki kitaplar"),
            ("Bilim", "Bilimsel kitaplar"),
            ("Tarih", "Tarih kitapları"),
            ("Biyografi", "Biyografi kitapları"),
            ("Çocuk", "Çocuk kitapları"),
            ("Eğitim", "Eğitim kitapları"),
            ("Felsefe", "Felsefe kitapları"),
            ("Sanat", "Sanat kitapları")
        ]
        
        try:
            cursor.executemany("""
                INSERT OR IGNORE INTO categories (name, description)
                VALUES (?, ?)
            """, default_categories)
        except:
            pass

        self.conn.commit()

    ###########################################################################
    # 1. SEKME: VERİ ÇEKME
    ###########################################################################
    def init_fetch_tab(self):
        layout = QVBoxLayout()
        self.fetch_tab.setLayout(layout)

        # ISBN Girişi
        isbn_layout = QHBoxLayout()
        isbn_label = QLabel("ISBN Numaraları (virgülle veya satır başı ile ayrılmış):")
        self.isbn_input = QTextEdit()
        isbn_layout.addWidget(isbn_label)
        isbn_layout.addWidget(self.isbn_input)
        layout.addLayout(isbn_layout)

        # Butonlar (Excel'den Yükle / Excel'e Aktar / Veritabanına Kaydet vs.)
        buttons_layout = QHBoxLayout()
        self.fetch_button = QPushButton("Kitap Bilgilerini Çek")
        self.fetch_button.clicked.connect(self.fetch_books_info)

        self.fetch_load_excel_button = QPushButton("Excel'den Yükle")
        self.fetch_load_excel_button.clicked.connect(self.load_isbns_from_excel)

        self.fetch_export_excel_button = QPushButton("Excel'e Aktar")
        self.fetch_export_excel_button.clicked.connect(self.export_to_excel)
        self.fetch_export_excel_button.setEnabled(False)

        self.fetch_export_db_button = QPushButton("Veritabanına Kaydet")
        self.fetch_export_db_button.clicked.connect(self.export_to_db)
        self.fetch_export_db_button.setEnabled(False)

        buttons_layout.addWidget(self.fetch_button)
        buttons_layout.addWidget(self.fetch_load_excel_button)
        buttons_layout.addWidget(self.fetch_export_excel_button)
        buttons_layout.addWidget(self.fetch_export_db_button)
        layout.addLayout(buttons_layout)

        # Arama alanı
        search_layout = QHBoxLayout()
        search_label = QLabel("Ara (Başlık/Yazar):")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Başlık veya Yazar adına göre arama...")
        search_button = QPushButton("Ara")
        search_button.clicked.connect(lambda: self.search_books(self.search_input.text()))

        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(search_button)
        layout.addLayout(search_layout)

        # Tablo
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "ISBN", "Başlık", "Yazar", "Yayın Yılı",
            "Sayfa Sayısı", "Yayınevi", "Diller", "Resim", "Adet"
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)
        self.table.cellDoubleClicked.connect(self.view_book_details)
        layout.addWidget(self.table)

        # İlerleme Çubuğu
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

    ###########################################################################
    # 2. SEKME: KÜTÜPHANE
    ###########################################################################
    def init_library_tab(self):
        layout = QVBoxLayout()
        self.library_tab.setLayout(layout)

        # Kütüphane Butonları (Excel'den Yükle / Excel'e Aktar / Sil / Güncelle)
        library_buttons_layout = QHBoxLayout()

        self.library_load_excel_button = QPushButton("Kütüphaneyi Excel'den Yükle")
        self.library_load_excel_button.clicked.connect(self.load_library_from_excel)

        self.library_export_excel_button = QPushButton("Kütüphaneyi Excel'e Aktar")
        self.library_export_excel_button.clicked.connect(self.export_library_to_excel)

        self.library_delete_button = QPushButton("Kitap Sil")
        self.library_delete_button.clicked.connect(self.library_delete_records)

        self.library_update_button = QPushButton("Kitap Güncelle")
        self.library_update_button.clicked.connect(self.library_update_record)

        library_buttons_layout.addWidget(self.library_load_excel_button)
        library_buttons_layout.addWidget(self.library_export_excel_button)
        library_buttons_layout.addWidget(self.library_delete_button)
        library_buttons_layout.addWidget(self.library_update_button)
        layout.addLayout(library_buttons_layout)

        # Arama (Kütüphane)
        lib_search_layout = QHBoxLayout()
        lib_search_label = QLabel("Ara (ISBN/Başlık/Yazar):")
        self.library_search_input = QLineEdit()
        self.library_search_input.setPlaceholderText("ISBN, Başlık veya Yazar arayın...")
        lib_search_button = QPushButton("Ara")
        lib_search_button.clicked.connect(lambda: self.search_library_books(self.library_search_input.text()))

        lib_search_layout.addWidget(lib_search_label)
        lib_search_layout.addWidget(self.library_search_input)
        lib_search_layout.addWidget(lib_search_button)
        layout.addLayout(lib_search_layout)

        # Kütüphane Tablosu
        self.library_table = QTableWidget()
        self.library_table.setColumnCount(13)  # Resim sütunu için 13'e çıkardık
        self.library_table.setHorizontalHeaderLabels([
            "Kapak", "ISBN", "Başlık", "Yazar", "Yayın Yılı",
            "Sayfa Sayısı", "Yayınevi", "Kategoriler",
            "Toplam Adet", "Ödünç Verilen", "Mevcut Adet", "Raf", "Dolap"
        ])
        self.library_table.horizontalHeader().setStretchLastSection(True)
        self.library_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.library_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.library_table.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)
        self.library_table.cellDoubleClicked.connect(self.view_library_book_details)
        layout.addWidget(self.library_table)

        # Gelişmiş arama butonu
        self.advanced_search_button = QPushButton("Gelişmiş Arama")
        self.advanced_search_button.clicked.connect(self.advanced_search)
        library_buttons_layout.addWidget(self.advanced_search_button)
        
        # Kategori yönetimi butonu
        self.category_button = QPushButton("Kategori Yönetimi")
        self.category_button.clicked.connect(self.manage_categories)
        library_buttons_layout.addWidget(self.category_button)

    ###########################################################################
    # 3. SEKME: ÜYELER
    ###########################################################################
    def init_members_tab(self):
        layout = QVBoxLayout()
        self.members_tab.setLayout(layout)

        # Butonlar
        members_buttons_layout = QHBoxLayout()
        self.add_member_button = QPushButton("Üye Ekle")
        self.add_member_button.clicked.connect(self.add_member)

        self.delete_member_button = QPushButton("Üye Sil")
        self.delete_member_button.clicked.connect(self.delete_member)

        self.update_member_button = QPushButton("Üye Düzenle")
        self.update_member_button.clicked.connect(self.update_member)

        # Excel butonları
        self.members_load_excel_button = QPushButton("Üyeleri Excel'den Yükle")
        self.members_load_excel_button.clicked.connect(self.load_members_from_excel)

        self.members_export_excel_button = QPushButton("Üyeleri Excel'e Aktar")
        self.members_export_excel_button.clicked.connect(self.export_members_to_excel)

        members_buttons_layout.addWidget(self.add_member_button)
        members_buttons_layout.addWidget(self.delete_member_button)
        members_buttons_layout.addWidget(self.update_member_button)
        members_buttons_layout.addWidget(self.members_load_excel_button)
        members_buttons_layout.addWidget(self.members_export_excel_button)
        layout.addLayout(members_buttons_layout)

        # Arama
        search_layout = QHBoxLayout()
        search_label = QLabel("Ara (Ad-Soyad / Üye Türü):")
        self.member_search_input = QLineEdit()
        self.member_search_input.setPlaceholderText("Örn: Ali Veli veya Öğrenci/Öğretmen")
        search_button = QPushButton("Ara")
        search_button.clicked.connect(lambda: self.search_members(self.member_search_input.text()))

        search_layout.addWidget(search_label)
        search_layout.addWidget(self.member_search_input)
        search_layout.addWidget(search_button)
        layout.addLayout(search_layout)

        # Üye Tablosu
        self.members_table = QTableWidget()
        self.members_table.setColumnCount(6)  
        self.members_table.setHorizontalHeaderLabels([
            "ID", "Ad-Soyad", "Sınıf", "Numara", "E-mail", "Üye Türü"
        ])
        self.members_table.horizontalHeader().setStretchLastSection(True)
        self.members_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.members_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.members_table.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)
        layout.addWidget(self.members_table)

    ###########################################################################
    # 4. SEKME: İŞLEMLER (Ödünç Verme, İade, Gecikme vb.)
    ###########################################################################
    def init_transactions_tab(self):
        layout = QVBoxLayout()
        self.transactions_tab.setLayout(layout)

        # Butonlar
        transactions_buttons_layout = QHBoxLayout()
        self.borrow_button = QPushButton("Ödünç Ver")
        self.borrow_button.clicked.connect(self.borrow_book)

        self.return_button = QPushButton("İade Al")
        self.return_button.clicked.connect(self.return_book)

        self.overdue_button = QPushButton("Gecikenler Listesi")
        self.overdue_button.clicked.connect(self.show_overdue_list)

        # Excel butonları
        self.transactions_load_excel_button = QPushButton("İşlemleri Excel'den Yükle")
        self.transactions_load_excel_button.clicked.connect(self.load_transactions_from_excel)

        self.transactions_export_excel_button = QPushButton("İşlemleri Excel'e Aktar")
        self.transactions_export_excel_button.clicked.connect(self.export_transactions_to_excel)

        transactions_buttons_layout.addWidget(self.borrow_button)
        transactions_buttons_layout.addWidget(self.return_button)
        transactions_buttons_layout.addWidget(self.overdue_button)
        transactions_buttons_layout.addWidget(self.transactions_load_excel_button)
        transactions_buttons_layout.addWidget(self.transactions_export_excel_button)

        layout.addLayout(transactions_buttons_layout)

        # Arama
        search_layout = QHBoxLayout()
        search_label = QLabel("Ara (ISBN / Üye ID):")
        self.transaction_search_input = QLineEdit()
        self.transaction_search_input.setPlaceholderText("ISBN veya Üye ID arayın...")
        search_button = QPushButton("Ara")
        search_button.clicked.connect(lambda: self.search_transactions(self.transaction_search_input.text()))

        search_layout.addWidget(search_label)
        search_layout.addWidget(self.transaction_search_input)
        search_layout.addWidget(search_button)
        layout.addLayout(search_layout)

        # İşlemler Tablosu
        self.transactions_table = QTableWidget()
        self.transactions_table.setColumnCount(6)
        self.transactions_table.setHorizontalHeaderLabels([
            "ID", "ISBN", "Üye ID", "Veriliş Tarihi", "Son Tarih (Due)", "İade Tarihi"
        ])
        self.transactions_table.horizontalHeader().setStretchLastSection(True)
        self.transactions_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.transactions_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.transactions_table.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)

        layout.addWidget(self.transactions_table)

    ###########################################################################
    # DB Yedekle/Geri Yükle
    ###########################################################################
    def backup_database(self):
        import shutil
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Veritabanını Yedekle", "", "DB Dosyaları (*.db);;Tüm Dosyalar (*)", options=options
        )
        if file_path:
            try:
                self.conn.close()
                shutil.copyfile('books_info.db', file_path)
                QMessageBox.information(self, "Başarılı", f"Veritabanı yedeklendi: {file_path}")
                self.conn = sqlite3.connect('books_info.db')
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"Yedekleme hatası: {e}")
                self.conn = sqlite3.connect('books_info.db')

    def restore_database(self):
        import shutil
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Veritabanı Yedeğini Seç", "", "DB Dosyaları (*.db);;Tüm Dosyalar (*)", options=options
        )
        if file_path:
            reply = QMessageBox.question(
                self, 'Onay', "Mevcut veritabanının üzerine yazılacak. Emin misiniz?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                try:
                    self.conn.close()
                    shutil.copyfile(file_path, 'books_info.db')
                    QMessageBox.information(self, "Başarılı", "Veritabanı geri yüklendi.")
                    self.conn = sqlite3.connect('books_info.db')
                    self.load_data_from_db()
                    self.load_members_from_db()
                    self.load_transactions_from_db()
                    self.update_member_count_label()
                except Exception as e:
                    QMessageBox.critical(self, "Hata", f"Geri yükleme hatası: {e}")
                    self.conn = sqlite3.connect('books_info.db')

    ###########################################################################
    # (A) Veri Çekme Sekmesi: Excel'den ISBN Yükleme
    ###########################################################################
    def load_isbns_from_excel(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(
            self, "ISBN'leri Excel'den Yükle", "",
            "Excel Dosyaları (*.xlsx *.xls);;Tüm Dosyalar (*)", options=options
        )
        if file_path:
            try:
                df = pd.read_excel(file_path, dtype=str)
                if 'ISBN' not in df.columns:
                    QMessageBox.warning(self, "Hata", "'ISBN' sütunu bulunamadı.")
                    return
                isbns = df['ISBN'].dropna().astype(str).str.strip().tolist()
                self.isbn_input.setPlainText(', '.join(isbns))
                QMessageBox.information(self, "Bilgi", f"{len(isbns)} ISBN yüklendi.")
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"Excel yüklenirken hata: {e}")

    ###########################################################################
    # (B) Kitap Bilgisi Çekme (Veri Çekme Sekmesi)
    ###########################################################################
    def fetch_books_info(self):
        text = self.isbn_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Uyarı", "Lütfen en az bir ISBN girin.")
            return

        isbns = [i.strip() for i in text.replace(',', '\n').split('\n') if i.strip()]
        if not isbns:
            QMessageBox.warning(self, "Uyarı", "Geçerli ISBN yok.")
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.fetch_button.setEnabled(False)
        self.fetch_load_excel_button.setEnabled(False)
        self.fetch_export_excel_button.setEnabled(False)
        self.fetch_export_db_button.setEnabled(False)

        self.thread = FetchThread(isbns)
        self.thread.progress.connect(self.progress_bar.setValue)
        self.thread.result.connect(self.on_fetch_success)
        self.thread.error.connect(self.on_fetch_error)
        self.thread.start()

    def on_fetch_success(self, books_info):
        self.current_books_info = books_info
        self.display_books_info(books_info)
        self.fetch_export_excel_button.setEnabled(True)
        self.fetch_export_db_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.fetch_button.setEnabled(True)
        self.fetch_load_excel_button.setEnabled(True)
        QMessageBox.information(self, "Başarılı", f"{len(books_info)} kitap bilgisi çekildi.")

    def on_fetch_error(self, message):
        QMessageBox.critical(self, "Hata", f"Kitap bilgisi çekme hatası: {message}")
        self.progress_bar.setVisible(False)
        self.fetch_button.setEnabled(True)
        self.fetch_load_excel_button.setEnabled(True)

    def display_books_info(self, books):
        self.table.setRowCount(0)
        for book in books:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(book["ISBN"]))
            self.table.setItem(r, 1, QTableWidgetItem(book["Başlık"]))
            self.table.setItem(r, 2, QTableWidgetItem(book["Yazar"]))
            self.table.setItem(r, 3, QTableWidgetItem(book["Yayın Yılı"]))
            self.table.setItem(r, 4, QTableWidgetItem(str(book["Sayfa Sayısı"])))
            self.table.setItem(r, 5, QTableWidgetItem(book["Yayınevi"]))
            self.table.setItem(r, 6, QTableWidgetItem(book["Diller"]))
            self.table.setItem(r, 7, QTableWidgetItem(book["Resim"]))
            self.table.setItem(r, 8, QTableWidgetItem(str(book["Adet"])))
        self.table.resizeColumnsToContents()

    ###########################################################################
    # (C) Excel'e Aktarma (Veri Çekme Sekmesi)
    ###########################################################################
    def export_to_excel(self):
        if not hasattr(self, 'current_books_info') or not self.current_books_info:
            QMessageBox.warning(self, "Uyarı", "Önce kitap bilgisi çekin.")
            return
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Excel Dosyası Kaydet", "", "Excel Dosyaları (*.xlsx);;Tüm Dosyalar (*)", options=options
        )
        if file_path:
            try:
                df = pd.DataFrame(self.current_books_info)
                df.to_excel(file_path, index=False)
                QMessageBox.information(self, "Başarılı", f"Excel kaydedildi: {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"Excel kaydedilemedi: {e}")

    ###########################################################################
    # (D) Veritabanına Kaydet (Veri Çekme Sekmesi)
    ###########################################################################
    def export_to_db(self):
        if not hasattr(self, 'current_books_info') or not self.current_books_info:
            QMessageBox.warning(self, "Uyarı", "Önce kitap bilgisi çekin.")
            return
        try:
            cursor = self.conn.cursor()
            for book in self.current_books_info:
                cursor.execute("""
                    INSERT OR REPLACE INTO books
                    (isbn, title, authors, publish_date, number_of_pages, 
                     publishers, languages, quantity, image_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    book["ISBN"],
                    book["Başlık"],
                    book["Yazar"],
                    book["Yayın Yılı"],
                    None if book["Sayfa Sayısı"] == "N/A" else book["Sayfa Sayısı"],
                    book["Yayınevi"],
                    book["Diller"],
                    book["Adet"],
                    book["Resim"]
                ))
            self.conn.commit()
            QMessageBox.information(self, "Başarılı", "Veriler veritabanına kaydedildi.")
            self.load_data_from_db()
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Veritabanına kaydetme hatası: {e}")

    ###########################################################################
    # KÜTÜPHANE: Excel'den Yükleme
    ###########################################################################
    def load_library_from_excel(self):
        """
        Kütüphaneye Excel'den toplu kitap yükler.
        Beklenen sütunlar: isbn, title, authors, publish_date, number_of_pages,
                           publishers, languages, quantity, shelf, cupboard, image_path
        """
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Kütüphaneyi Excel'den Yükle", "",
            "Excel Dosyaları (*.xlsx *.xls);;Tüm Dosyalar (*)", options=options
        )
        if file_path:
            try:
                df = pd.read_excel(file_path, dtype=str).fillna('')
                required_cols = [
                    "isbn", "title", "authors", "publish_date", "number_of_pages",
                    "publishers", "languages", "quantity", "shelf", "cupboard", "image_path"
                ]
                for col in required_cols:
                    if col not in df.columns:
                        QMessageBox.warning(self, "Hata", f"'{col}' sütunu bulunamadı.")
                        return

                cursor = self.conn.cursor()
                for idx, row in df.iterrows():
                    # quantity numerik alanda hata olmaması için
                    quantity_val = 1
                    try:
                        quantity_val = int(row["quantity"])
                    except:
                        pass

                    cursor.execute("""
                        INSERT OR REPLACE INTO books
                        (isbn, title, authors, publish_date, number_of_pages,
                         publishers, languages, quantity, shelf, cupboard, image_path)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        row["isbn"].strip(),
                        row["title"].strip(),
                        row["authors"].strip(),
                        row["publish_date"].strip(),
                        None if not row["number_of_pages"].strip() else row["number_of_pages"].strip(),
                        row["publishers"].strip(),
                        row["languages"].strip(),
                        quantity_val,
                        row["shelf"].strip(),
                        row["cupboard"].strip(),
                        row["image_path"].strip()
                    ))
                self.conn.commit()
                QMessageBox.information(self, "Başarılı", f"{len(df)} kitap başarıyla yüklendi.")
                self.load_data_from_db()
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"Kütüphane yüklenirken hata: {e}")

    ###########################################################################
    # KÜTÜPHANE: Excel'e Aktarma
    ###########################################################################
    def export_library_to_excel(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Kütüphaneyi Excel'e Aktar", "",
            "Excel Dosyaları (*.xlsx);;Tüm Dosyalar (*)", options=options
        )
        if file_path:
            try:
                cursor = self.conn.cursor()
                cursor.execute("SELECT * FROM books")
                rows = cursor.fetchall()
                columns = [desc[0] for desc in cursor.description]
                df = pd.DataFrame(rows, columns=columns)
                df.to_excel(file_path, index=False)
                QMessageBox.information(self, "Başarılı", f"Excel'e aktarıldı: {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"Excel aktarım hatası: {e}")

    ###########################################################################
    # KÜTÜPHANE: Veritabanından Yükle
    ###########################################################################
    def load_data_from_db(self):
        self.library_table.setRowCount(0)
        try:
            cursor = self.conn.cursor()
            # Kitapları ve ödünç verilen adetleri birleştiren sorgu
            cursor.execute("""
                SELECT b.*, 
                       COALESCE((
                           SELECT COUNT(*) 
                           FROM transactions t 
                           WHERE t.isbn = b.isbn 
                           AND t.return_date IS NULL
                       ), 0) as borrowed_count,
                       GROUP_CONCAT(c.name) as categories
                FROM books b
                LEFT JOIN book_categories bc ON b.isbn = bc.book_isbn
                LEFT JOIN categories c ON bc.category_id = c.id
                GROUP BY b.isbn
            """)
            rows = cursor.fetchall()
            for row_data in rows:
                r = self.library_table.rowCount()
                self.library_table.insertRow(r)
                
                # Kapak resmi
                image_path = row_data[10]  # image_path sütunu
                if image_path and os.path.exists(image_path):
                    pixmap = QPixmap(image_path)
                    pixmap = pixmap.scaled(50, 70, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    image_label = QLabel()
                    image_label.setPixmap(pixmap)
                    image_label.setAlignment(Qt.AlignCenter)
                    self.library_table.setCellWidget(r, 0, image_label)
                else:
                    no_image_label = QLabel("Resim Yok")
                    no_image_label.setAlignment(Qt.AlignCenter)
                    self.library_table.setCellWidget(r, 0, no_image_label)
                
                # Toplam adet
                total_quantity = row_data[7]  # quantity sütunu
                # Ödünç verilen adet
                borrowed_count = row_data[-2]  # borrowed_count sütunu
                # Mevcut adet
                available_quantity = total_quantity - borrowed_count
                
                # ISBN'den Yayınevi'ne kadar olan sütunları ekle (1'den başlayarak çünkü 0. sütun resim)
                for col_index, value in enumerate(row_data[:7]):  # ISBN'den publishers'a kadar
                    if value is None:
                        value = ""
                    self.library_table.setItem(r, col_index + 1, QTableWidgetItem(str(value)))
                
                # Kategoriler
                categories = row_data[-1] if row_data[-1] else ""
                self.library_table.setItem(r, 7, QTableWidgetItem(categories))
                
                # Ödünç verilen adet
                self.library_table.setItem(r, 9, QTableWidgetItem(str(borrowed_count)))
                # Mevcut adet
                self.library_table.setItem(r, 10, QTableWidgetItem(str(available_quantity)))
                # Raf ve Dolap
                self.library_table.setItem(r, 11, QTableWidgetItem(str(row_data[8] or "")))
                self.library_table.setItem(r, 12, QTableWidgetItem(str(row_data[9] or "")))  # Dolap
                
            self.library_table.resizeColumnsToContents()
            # Resim sütununu sabit genişlikte tut
            self.library_table.setColumnWidth(0, 70)

            # Toplam adet ve toplam farklı kitap sayısı
            cursor.execute("SELECT COUNT(*) FROM books")  # farklı ISBN sayısı
            distinct_count = cursor.fetchone()[0]

            cursor.execute("SELECT SUM(quantity) FROM books")  # toplam adet
            sum_quantity = cursor.fetchone()[0]
            if sum_quantity is None:
                sum_quantity = 0

            # Toplam ödünç verilen kitap sayısı
            cursor.execute("""
                SELECT COUNT(*) 
                FROM transactions 
                WHERE return_date IS NULL
            """)
            borrowed_count = cursor.fetchone()[0]
            if borrowed_count is None:
                borrowed_count = 0

            self.total_books_label.setText(f"Toplam Kitap Sayısı: {sum_quantity}")
            self.distinct_books_label.setText(f"Toplam Farklı Kitap Sayısı: {distinct_count}")
            self.available_books_label.setText(f"Mevcut Kitap Sayısı: {sum_quantity - borrowed_count}")

        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Veritabanı yükleme hatası: {e}")

    def manage_categories(self):
        selected_rows = self.library_table.selectionModel().selectedRows()
        if len(selected_rows) != 1:
            QMessageBox.warning(self, "Uyarı", "Kategori yönetimi için tek bir kitap seçmelisiniz.")
            return

        row = selected_rows[0].row()
        isbn = self.library_table.item(row, 1).text()  # Changed from 0 to 1 since ISBN is in column 1

        dialog = CategoryDialog(isbn, self)
        if dialog.exec_() == QDialog.Accepted:
            selected_categories = dialog.get_selected_categories()
            try:
                cursor = self.conn.cursor()
                # Mevcut kategorileri temizle
                cursor.execute("DELETE FROM book_categories WHERE book_isbn = ?", (isbn,))
                
                # Yeni kategorileri ekle
                for category_name in selected_categories:
                    cursor.execute("""
                        INSERT INTO book_categories (book_isbn, category_id)
                        SELECT ?, id FROM categories WHERE name = ?
                    """, (isbn, category_name))
                
                self.conn.commit()
                QMessageBox.information(self, "Başarılı", "Kategoriler güncellendi.")
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"Kategori güncelleme hatası: {e}")

    def view_book_details(self, row, column):
        """Kitap detaylarını gösterir."""
        try:
            isbn = self.table.item(row, 0).text()
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM books WHERE isbn = ?", (isbn,))
            book_data = cursor.fetchone()
            
            if book_data:
                book_info = {
                    "ISBN": book_data[0],
                    "Başlık": book_data[1],
                    "Yazar": book_data[2],
                    "Yayın Yılı": book_data[3],
                    "Sayfa Sayısı": book_data[4],
                    "Yayınevi": book_data[5],
                    "Diller": book_data[6],
                    "Raf": book_data[8],
                    "Dolap": book_data[9],
                    "Resim": book_data[10]
                }
                dialog = LibraryDialog(book_info, self)
                dialog.exec_()
            else:
                QMessageBox.warning(self, "Uyarı", "Kitap bulunamadı.")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Kitap detayları görüntülenirken hata oluştu: {e}")

    def library_delete_records(self):
        """Seçili kitapları kütüphaneden siler."""
        selected_rows = self.library_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "Uyarı", "Lütfen silinecek kitapları seçin.")
            return

        reply = QMessageBox.question(
            self, 'Onay',
            f"{len(selected_rows)} kitap silinecek. Emin misiniz?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                cursor = self.conn.cursor()
                for row in selected_rows:
                    isbn = self.library_table.item(row.row(), 1).text()  # ISBN sütunu
                    
                    # Önce ödünç verilmiş mi kontrol et
                    cursor.execute("""
                        SELECT COUNT(*) FROM transactions 
                        WHERE isbn = ? AND return_date IS NULL
                    """, (isbn,))
                    borrowed_count = cursor.fetchone()[0]
                    
                    if borrowed_count > 0:
                        QMessageBox.warning(
                            self, "Uyarı",
                            f"ISBN: {isbn} olan kitap şu anda ödünç verilmiş durumda. "
                            "Önce iade alınmalıdır."
                        )
                        continue
                    
                    # Kitabı sil
                    cursor.execute("DELETE FROM books WHERE isbn = ?", (isbn,))
                    # İlişkili kategorileri sil
                    cursor.execute("DELETE FROM book_categories WHERE book_isbn = ?", (isbn,))
                    # İlişkili işlemleri sil
                    cursor.execute("DELETE FROM transactions WHERE isbn = ?", (isbn,))
                    # İlişkili bildirimleri sil
                    cursor.execute("DELETE FROM notifications WHERE related_isbn = ?", (isbn,))

                self.conn.commit()
                QMessageBox.information(self, "Başarılı", "Seçili kitaplar silindi.")
                self.load_data_from_db()  # Tabloyu güncelle
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"Kitap silme hatası: {e}")

    def library_update_record(self):
        """Seçili kitabın bilgilerini günceller."""
        selected_rows = self.library_table.selectionModel().selectedRows()
        if len(selected_rows) != 1:
            QMessageBox.warning(self, "Uyarı", "Lütfen güncellenecek bir kitap seçin.")
            return

        row = selected_rows[0].row()
        isbn = self.library_table.item(row, 1).text()  # ISBN sütunu (1. sütun)

        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM books WHERE isbn = ?", (isbn,))
            book_data = cursor.fetchone()
            
            if book_data:
                book_info = {
                    "ISBN": book_data[0],
                    "Başlık": book_data[1],
                    "Yazar": book_data[2],
                    "Yayın Yılı": book_data[3],
                    "Sayfa Sayısı": book_data[4],
                    "Yayınevi": book_data[5],
                    "Diller": book_data[6],
                    "Raf": book_data[8],
                    "Dolap": book_data[9],
                    "Resim": book_data[10]
                }
                
                dialog = LibraryUpdateDialog(book_info, self)
                if dialog.exec_() == QDialog.Accepted:
                    updated_info = dialog.get_updated_info()
                    
                    # Veritabanını güncelle
                    cursor.execute("""
                        UPDATE books
                        SET title = ?, authors = ?, publish_date = ?, 
                            number_of_pages = ?, publishers = ?, languages = ?, 
                            shelf = ?, cupboard = ?, image_path = ?
                        WHERE isbn = ?
                    """, (
                        updated_info["Başlık"],
                        updated_info["Yazar"],
                        updated_info["Yayın Yılı"],
                        updated_info["Sayfa Sayısı"],
                        updated_info["Yayınevi"],
                        updated_info["Diller"],
                        updated_info["Raf"],
                        updated_info["Dolap"],
                        updated_info["Resim"],
                        updated_info["ISBN"]
                    ))
                    self.conn.commit()
                    QMessageBox.information(self, "Başarılı", "Kitap bilgileri güncellendi.")
                    self.load_data_from_db()  # Tabloyu güncelle
            else:
                QMessageBox.warning(self, "Uyarı", "Kitap bulunamadı.")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Kitap güncelleme hatası: {e}")

    def view_library_book_details(self, row, column):
        """Kütüphane sekmesinde kitap detaylarını gösterir."""
        try:
            isbn = self.library_table.item(row, 1).text()  # ISBN sütunu (1. sütun)
            
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM books WHERE isbn = ?", (isbn,))
            book_data = cursor.fetchone()
            
            if book_data:
                # Kitap kategorilerini al
                cursor.execute("""
                    SELECT c.name 
                    FROM categories c
                    JOIN book_categories bc ON c.id = bc.category_id
                    WHERE bc.book_isbn = ?
                """, (isbn,))
                categories = [row[0] for row in cursor.fetchall()]

                book_info = {
                    "ISBN": book_data[0],
                    "Başlık": book_data[1],
                    "Yazar": book_data[2],
                    "Yayın Yılı": book_data[3],
                    "Sayfa Sayısı": book_data[4],
                    "Yayınevi": book_data[5],
                    "Diller": book_data[6],
                    "Raf": book_data[8],
                    "Dolap": book_data[9],
                    "Resim": book_data[10],
                    "Kategoriler": ", ".join(categories) if categories else "Kategori yok"
                }
                
                dialog = LibraryDialog(book_info, self)
                dialog.exec_()
            else:
                QMessageBox.warning(self, "Uyarı", "Kitap bulunamadı.")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Kitap detayları görüntülenirken hata oluştu: {e}")

    def advanced_search(self):
        """Gelişmiş arama diyalogunu açar ve sonuçları filtreler."""
        dialog = AdvancedSearchDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            criteria = dialog.get_search_criteria()
            
            # Arama terimini geçmişe kaydet
            search_term_parts = []
            if criteria["title"]: search_term_parts.append(f"Başlık: {criteria['title']}")
            if criteria["author"]: search_term_parts.append(f"Yazar: {criteria['author']}")
            if criteria["publisher"]: search_term_parts.append(f"Yayınevi: {criteria['publisher']}")
            if criteria["year_from"] != 1800 or criteria["year_to"] != 2100:
                search_term_parts.append(f"Yıl: {criteria['year_from']}-{criteria['year_to']}")
            if criteria["category"]: search_term_parts.append(f"Kategori: {criteria['category']}")
            
            search_term_display = ", ".join(search_term_parts)
            if search_term_display:  # Sadece doluysa kaydet
                try:
                    cursor = self.conn.cursor()
                    cursor.execute("""
                        INSERT INTO search_history (search_term, search_date) 
                        VALUES (?, ?)
                    """, (search_term_display, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    self.conn.commit()
                except Exception as e:
                    print(f"Arama geçmişi kaydetme hatası: {e}")

            self.search_library_books(criteria=criteria)

    def add_member(self):
        """Yeni üye ekleme diyalogunu açar ve üyeyi kaydeder."""
        empty_info = {
            "ad_soyad": "",
            "sinif": "",
            "numara": "",
            "email": "",
            "uye_turu": "Öğrenci" # Default value
        }
        dialog = MemberDialog(empty_info, self)
        if dialog.exec_() == QDialog.Accepted:
            member_data = dialog.get_input_data()
            try:
                cursor = self.conn.cursor()
                cursor.execute("""
                    INSERT INTO members (ad_soyad, sinif, numara, email, uye_turu)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    member_data["ad_soyad"],
                    member_data["sinif"],
                    member_data["numara"],
                    member_data["email"],
                    member_data["uye_turu"]
                ))
                self.conn.commit()
                QMessageBox.information(self, "Başarılı", "Üye başarıyla eklendi.")
                self.load_members_from_db()  # Üye tablosunu güncelle
                self.update_member_count_label() # Ana sayfadaki üye sayısını güncelle
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"Üye ekleme hatası: {e}")

    def delete_member(self):
        """Seçili üyeleri siler."""
        selected_rows = self.members_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "Uyarı", "Lütfen silinecek üyeleri seçin.")
            return

        reply = QMessageBox.question(
            self, 'Onay',
            f"{len(selected_rows)} üye silinecek. Emin misiniz?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                cursor = self.conn.cursor()
                ids_to_delete = []
                for row_item in selected_rows:
                    member_id = self.members_table.item(row_item.row(), 0).text()  # ID sütunu
                    
                    # Üyenin iade etmediği kitap var mı kontrol et
                    cursor.execute("""
                        SELECT COUNT(*) FROM transactions 
                        WHERE member_id = ? AND return_date IS NULL
                    """, (member_id,))
                    borrowed_count = cursor.fetchone()[0]
                    
                    if borrowed_count > 0:
                        member_name = self.members_table.item(row_item.row(), 1).text()
                        QMessageBox.warning(
                            self, "Uyarı",
                            f"'{member_name}' adlı üyenin iade etmediği kitap/kitaplar var. "
                            f"Önce kitapların iade edilmesi gerekir."
                        )
                        continue  # Bu üyeyi atla
                    ids_to_delete.append(member_id)

                if ids_to_delete:
                    for member_id in ids_to_delete:
                        # Üyeyle ilişkili işlemleri sil (isteğe bağlı, ya da anonimleştirilebilir)
                        # Şimdilik sadece üyeyi siliyoruz, işlemleri bırakıyoruz.
                        # Eğer işlemler de silinmek istenirse: 
                        # cursor.execute("DELETE FROM transactions WHERE member_id = ?", (member_id,))
                        cursor.execute("DELETE FROM members WHERE id = ?", (member_id,))
                    
                    self.conn.commit()
                    QMessageBox.information(self, "Başarılı", f"{len(ids_to_delete)} üye başarıyla silindi.")
                    self.load_members_from_db()  # Üye tablosunu güncelle
                    self.update_member_count_label()  # Ana sayfadaki üye sayısını güncelle
                else:
                    QMessageBox.information(self, "Bilgi", "Silinecek uygun üye bulunamadı (muhtemelen iade edilmemiş kitapları var).")
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"Üye silme hatası: {e}")

    def update_member(self):
        """Seçili üyenin bilgilerini günceller."""
        selected_rows = self.members_table.selectionModel().selectedRows()
        if len(selected_rows) != 1:
            QMessageBox.warning(self, "Uyarı", "Lütfen güncellenecek üyeyi seçin.")
            return

        row = selected_rows[0].row()
        member_id = self.members_table.item(row, 0).text()
        
        # Fetch complete member info for the dialog, including non-editable fields
        try:
            cursor = self.conn.cursor()
            # This query might need to be expanded if MemberDialog expects more fields from DB
            cursor.execute("SELECT ad_soyad, sinif, numara, email, uye_turu FROM members WHERE id = ?", (member_id,))
            db_data = cursor.fetchone()
            if not db_data:
                QMessageBox.warning(self, "Hata", "Üye veritabanında bulunamadı.")
                return
            
            current_info_for_dialog = {
                "ID": member_id, # Add ID for display
                "ad_soyad": db_data[0],
                "sinif": db_data[1],
                "numara": db_data[2],
                "email": db_data[3],
                "uye_turu": db_data[4]
                # Potentially add other fields like 'Kayıt Tarihi' if you fetch and display them
            }
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Üye bilgileri alınırken hata: {e}")
            return

        dialog = MemberDialog(current_info_for_dialog, self)
        if dialog.exec_() == QDialog.Accepted:
            updated_data = dialog.get_input_data()
            try:
                cursor = self.conn.cursor()
                cursor.execute(
                    """
                    UPDATE members
                    SET ad_soyad = ?, sinif = ?, numara = ?, email = ?, uye_turu = ?
                    WHERE id = ?
                    """,
                    (
                        updated_data["ad_soyad"],
                        updated_data["sinif"],
                        updated_data["numara"],
                        updated_data["email"],
                        updated_data["uye_turu"],
                        member_id,
                    ),
                )
                self.conn.commit()
                QMessageBox.information(self, "Başarılı", "Üye bilgileri güncellendi.")
                self.load_members_from_db()
                self.update_member_count_label()
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"Üye güncelleme hatası: {e}")

    def load_members_from_db(self):
        """Üyeleri veritabanından yükler ve tabloya ekler."""
        self.members_table.setRowCount(0)
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM members ORDER BY ad_soyad")
            rows = cursor.fetchall()
            
            for row_data in rows:
                row = self.members_table.rowCount()
                self.members_table.insertRow(row)
                
                # Tüm sütunları ekle
                for col, value in enumerate(row_data):
                    self.members_table.setItem(row, col, QTableWidgetItem(str(value or "")))
                    
            self.members_table.resizeColumnsToContents()
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Üye verisi yükleme hatası: {e}")

    def export_members_to_excel(self):
        """Üyeleri Excel dosyasına aktarır."""
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Üyeleri Excel'e Aktar", "",
            "Excel Dosyaları (*.xlsx);;Tüm Dosyalar (*)", options=options
        )
        
        if file_path:
            try:
                cursor = self.conn.cursor()
                cursor.execute("""
                    SELECT id, ad_soyad, sinif, numara, email, uye_turu 
                    FROM members 
                    ORDER BY ad_soyad
                """)
                rows = cursor.fetchall()
                
                # DataFrame oluştur
                df = pd.DataFrame(rows, columns=[
                    "ID", "Ad-Soyad", "Sınıf", "Numara", "E-mail", "Üye Türü"
                ])
                
                # Excel'e kaydet
                df.to_excel(file_path, index=False)
                QMessageBox.information(
                    self, "Başarılı", 
                    f"Üyeler başarıyla Excel'e aktarıldı: {file_path}"
                )
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"Excel'e aktarma hatası: {e}")

    def load_members_from_excel(self):
        """Üyeleri Excel'den yükler."""
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Üyeleri Excel'den Yükle",
            "",
            "Excel Dosyaları (*.xlsx *.xls);;Tüm Dosyalar (*)",
            options=options,
        )
        if not file_path:
            return

        try:
            df = pd.read_excel(file_path, dtype=str).fillna("")
            required_cols = ["ad_soyad", "sinif", "numara", "email", "uye_turu"]
            missing_cols = [c for c in required_cols if c not in df.columns]
            if missing_cols:
                QMessageBox.warning(
                    self,
                    "Uyarı",
                    f"Excel dosyasında şu sütunlar eksik: {', '.join(missing_cols)}",
                )
                return

            cursor = self.conn.cursor()
            added_count = 0
            for _, row in df.iterrows():
                try:
                    cursor.execute(
                        """
                        INSERT INTO members (ad_soyad, sinif, numara, email, uye_turu)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            row["ad_soyad"].strip(),
                            row["sinif"].strip(),
                            row["numara"].strip(),
                            row["email"].strip(),
                            row["uye_turu"].strip() or "Öğrenci",
                        ),
                    )
                    added_count += 1
                except sqlite3.IntegrityError:
                    continue
            self.conn.commit()
            QMessageBox.information(self, "Başarılı", f"{added_count} üye başarıyla eklendi.")
            self.load_members_from_db()
            self.update_member_count_label()
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Excel'den üye yükleme hatası: {e}")

    # ---------------------------------------------------------------------
    # İŞLEMLER (Ödünç / İade) İLE İLGİLİ METODLAR
    # ---------------------------------------------------------------------
    def borrow_book(self):
        """Kitabı ISBN ve Okul No ile ödünç verir."""
        dialog = TransactionInputDialog(title="Kitap Ödünç Ver", parent=self)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            isbn = data["isbn"]
            school_no = data["school_no"]

            if not isbn or not school_no:
                QMessageBox.warning(self, "Uyarı", "ISBN ve Okul Numarası alanları boş bırakılamaz.")
                return

            try:
                cursor = self.conn.cursor()

                # Üye ID'sini okul numarasına göre bul
                cursor.execute("SELECT id FROM members WHERE numara = ?", (school_no,))
                member_result = cursor.fetchone()
                if not member_result:
                    QMessageBox.warning(self, "Uyarı", f"Okul Numarası '{school_no}' olan üye bulunamadı.")
                    return
                member_id = member_result[0]

                # Kitabın mevcut adedini ve varlığını kontrol et
                cursor.execute("SELECT quantity FROM books WHERE isbn = ?", (isbn,))
                book_result = cursor.fetchone()
                if not book_result:
                    QMessageBox.warning(self, "Uyarı", f"ISBN '{isbn}' olan kitap bulunamadı.")
                    return
                
                total_quantity = book_result[0]
                cursor.execute("SELECT COUNT(*) FROM transactions WHERE isbn = ? AND return_date IS NULL", (isbn,))
                borrowed_count = cursor.fetchone()[0]
                
                if total_quantity - borrowed_count <= 0:
                    QMessageBox.warning(self, "Uyarı", "Bu kitabın ödünç verilebilecek adedi yok.")
                    return

                # Son teslim tarihi diyaloğu (Mevcut QInputDialogWrapper kullanılabilir)
                due_date_str, ok = QInputDialogWrapper.getText(
                    self, "Son Teslim Tarihi", "Son teslim tarihi (YYYY-AA-GG):"
                )
                if not ok or not due_date_str.strip():
                    QMessageBox.warning(self, "Uyarı", "Son teslim tarihi girilmedi.")
                    return

                # Tarih formatını kontrol et
                try:
                    datetime.strptime(due_date_str.strip(), "%Y-%m-%d")
                except ValueError:
                    QMessageBox.warning(self, "Uyarı", "Tarih formatı geçersiz. Örnek: 2024-12-31")
                    return

                # İşlemi ekle
                cursor.execute(
                    """
                    INSERT INTO transactions (isbn, member_id, borrow_date, due_date)
                    VALUES (?, ?, ?, ?)
                    """,
                    (isbn, member_id, datetime.now().strftime("%Y-%m-%d"), due_date_str.strip())
                )
                # Kitap istatistikleri
                cursor.execute(
                    "UPDATE books SET last_borrowed_date = ?, total_borrow_count = total_borrow_count + 1 WHERE isbn = ?",
                    (datetime.now().strftime("%Y-%m-%d"), isbn)
                )
                self.conn.commit()
                QMessageBox.information(self, "Başarılı", "Kitap ödünç verildi.")
                self.load_transactions_from_db() # İşlemler tablosunu güncelle
                self.load_data_from_db() # Kütüphane tablosunu (adetler için) güncelle
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"Ödünç verme hatası: {e}")

    def return_book(self):
        """Kitabı ISBN ve Okul No ile iade alır."""
        dialog = TransactionInputDialog(title="Kitap İade Al", parent=self)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            isbn = data["isbn"]
            school_no = data["school_no"]

            if not isbn or not school_no:
                QMessageBox.warning(self, "Uyarı", "ISBN ve Okul Numarası alanları boş bırakılamaz.")
                return

            try:
                cursor = self.conn.cursor()

                # Üye ID'sini okul numarasına göre bul
                cursor.execute("SELECT id FROM members WHERE numara = ?", (school_no,))
                member_result = cursor.fetchone()
                if not member_result:
                    QMessageBox.warning(self, "Uyarı", f"Okul Numarası '{school_no}' olan üye bulunamadı.")
                    return
                member_id = member_result[0]

                # Aktif işlemi bul (ISBN ve Üye ID ile eşleşen, iade edilmemiş)
                cursor.execute("""
                    SELECT id, return_date 
                    FROM transactions 
                    WHERE isbn = ? AND member_id = ? AND return_date IS NULL
                    ORDER BY borrow_date DESC LIMIT 1 
                    """, (isbn, member_id))
                transaction_result = cursor.fetchone()

                if not transaction_result:
                    QMessageBox.warning(self, "Uyarı", f"Bu ISBN ('{isbn}') ve Okul Numarası ('{school_no}') ile eşleşen aktif bir ödünç işlemi bulunamadı.")
                    return
                
                trans_id = transaction_result[0]
                # Zaten iade edilmiş mi diye bir daha kontrol (Normalde yukarıdaki sorgu bunu engellemeli)
                if transaction_result[1] is not None:
                     QMessageBox.information(self, "Bilgi", "Bu işlem zaten daha önce iade alınmış.")
                     return

                # İade işlemini gerçekleştir
                cursor.execute("UPDATE transactions SET return_date = ? WHERE id = ?", 
                               (datetime.now().strftime("%Y-%m-%d"), trans_id))
                self.conn.commit()
                QMessageBox.information(self, "Başarılı", "Kitap iade alındı.")
                self.load_transactions_from_db() # İşlemler tablosunu güncelle
                self.load_data_from_db() # Kütüphane tablosunu (adetler için) güncelle
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"İade hatası: {e}")

    def show_overdue_list(self):
        """Geciken kitapların listesini gösterir."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT t.id, t.isbn, t.member_id, t.due_date, m.ad_soyad
                FROM transactions t
                JOIN members m ON t.member_id = m.id
                WHERE t.return_date IS NULL AND t.due_date < date('now')
                ORDER BY t.due_date
                """
            )
            rows = cursor.fetchall()
            if not rows:
                QMessageBox.information(self, "Bilgi", "Geciken kitap yok.")
                return
            message_lines = [f"ID:{r[0]} ISBN:{r[1]} Üye:{r[4]} Son Tarih:{r[3]}" for r in rows]
            QMessageBox.information(self, "Gecikenler", "\n".join(message_lines))
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Gecikenler listesi hatası: {e}")

    # ---------------------------------------------------------------------
    # İŞLEMLER: Yükleme / Kaydetme / Arama
    # ---------------------------------------------------------------------
    def load_transactions_from_db(self):
        """İşlemleri veritabanından yükler."""
        self.transactions_table.setRowCount(0)
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM transactions ORDER BY id DESC")
            rows = cursor.fetchall()
            for row_data in rows:
                r = self.transactions_table.rowCount()
                self.transactions_table.insertRow(r)
                for c, val in enumerate(row_data):
                    self.transactions_table.setItem(r, c, QTableWidgetItem(str(val or "")))
            self.transactions_table.resizeColumnsToContents()
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"İşlem verisi yükleme hatası: {e}")

    def load_transactions_from_excel(self):
        """Excel'den toplu işlem verisi yükler."""
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(
            self, "İşlemleri Excel'den Yükle", "",
            "Excel Dosyaları (*.xlsx *.xls);;Tüm Dosyalar (*)", options=options)
        if not file_path:
            return

        try:
            df = pd.read_excel(file_path, dtype=str).fillna('')
            required_cols = ["isbn", "member_id", "borrow_date", "due_date", "return_date"]
            missing = [c for c in required_cols if c not in df.columns]
            if missing:
                QMessageBox.warning(self, "Uyarı", f"Eksik sütunlar: {', '.join(missing)}")
                return

            cursor = self.conn.cursor()
            for _, row in df.iterrows():
                cursor.execute(
                    """
                    INSERT INTO transactions (isbn, member_id, borrow_date, due_date, return_date)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (row["isbn"].strip(), row["member_id"].strip(), row["borrow_date"].strip(),
                     row["due_date"].strip(), row["return_date"].strip() or None)
                )
            self.conn.commit()
            QMessageBox.information(self, "Başarılı", "İşlemler başarıyla yüklendi.")
            self.load_transactions_from_db()
            self.load_data_from_db()
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Excel'den işlem yükleme hatası: {e}")

    def export_transactions_to_excel(self):
        """İşlemleri Excel dosyasına aktarır."""
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getSaveFileName(
            self, "İşlemleri Excel'e Aktar", "",
            "Excel Dosyaları (*.xlsx);;Tüm Dosyalar (*)", options=options)
        if not file_path:
            return

        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM transactions ORDER BY id DESC")
            rows = cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            pd.DataFrame(rows, columns=cols).to_excel(file_path, index=False)
            QMessageBox.information(self, "Başarılı", f"İşlemler Excel'e aktarıldı: {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Excel'e aktarma hatası: {e}")

    def search_transactions(self, keyword):
        """İşlemler tablosunda arama yapar."""
        keyword = keyword.strip().lower()
        if not keyword:
            self.load_transactions_from_db()
            return
        try:
            cursor = self.conn.cursor()
            like_kw = f"%{keyword}%"
            cursor.execute(
                """
                SELECT * FROM transactions
                WHERE CAST(id AS TEXT) LIKE ?
                   OR isbn LIKE ?
                   OR CAST(member_id AS TEXT) LIKE ?
                ORDER BY id DESC
                """,
                (like_kw, like_kw, like_kw)
            )
            rows = cursor.fetchall()
            self.transactions_table.setRowCount(0)
            for row_data in rows:
                r = self.transactions_table.rowCount()
                self.transactions_table.insertRow(r)
                for c, val in enumerate(row_data):
                    self.transactions_table.setItem(r, c, QTableWidgetItem(str(val or "")))
            self.transactions_table.resizeColumnsToContents()
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Arama hatası: {e}")

    # ---------------------------------------------------------------------
    # ÜYE ARAMA
    # ---------------------------------------------------------------------
    def search_members(self, keyword):
        """Üye tablosunda arama yapar."""
        keyword = keyword.strip().lower()
        if not keyword:
            self.load_members_from_db()
            return

        try:
            cursor = self.conn.cursor()
            like_kw = f"%{keyword}%"
            cursor.execute(
                """
                SELECT * FROM members
                WHERE LOWER(ad_soyad) LIKE ? OR LOWER(uye_turu) LIKE ?
                ORDER BY ad_soyad
                """,
                (like_kw, like_kw)
            )
            rows = cursor.fetchall()
            self.members_table.setRowCount(0)
            for row_data in rows:
                r = self.members_table.rowCount()
                self.members_table.insertRow(r)
                for c, val in enumerate(row_data):
                    self.members_table.setItem(r, c, QTableWidgetItem(str(val or "")))
            self.members_table.resizeColumnsToContents()
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Arama hatası: {e}")

    # ---------------------------------------------------------------------
    # BİLDİRİMLER
    # ---------------------------------------------------------------------
    def show_notifications(self):
        """Okunmamış bildirimleri gösterir ve okundu olarak işaretler."""
        try:
            notifications = self.notification_system.get_unread_notifications()
            dialog = NotificationDialog(notifications, self)
            dialog.exec_()
            # Okundu olarak işaretle
            for notif in notifications:
                self.notification_system.mark_as_read(notif[0])
            # Toolbar yazısını güncelle
            self.check_notifications()
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Bildirimleri gösterme hatası: {e}")

    def check_notifications(self):
        """Okunmamış bildirim sayısını toolbar üzerinde günceller."""
        try:
            unread = self.notification_system.get_unread_notifications()
            count = len(unread)
            if count:
                self.notification_action.setText(f"Bildirimler ({count})")
            else:
                self.notification_action.setText("Bildirimler")
        except Exception as e:
            print(f"Bildirim kontrol hatası: {e}")

###############################################################################
# Basit bir QInputDialog sarmalayıcı
###############################################################################
from PyQt5.QtWidgets import QInputDialog

class QInputDialogWrapper:
    @staticmethod
    def getText(parent, title, label):
        text, ok = QInputDialog.getText(parent, title, label)
        return text, ok

###############################################################################
# main fonksiyonu
###############################################################################
def main():
    app = QApplication(sys.argv)
    window = ISBNApp()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
