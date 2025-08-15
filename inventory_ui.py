#!/usr/bin/env python3
# inventory_ui.py

import webbrowser
import tempfile
import re
import json, os, tkinter as tk
from tkinter import ttk, messagebox, filedialog
from dataclasses import dataclass, asdict
import sqlite3
import csv
from datetime import datetime, timedelta
import hashlib
import shutil
from typing import Dict, List, Optional
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import random
import string

# Constants
DATA_FILE = "inventory.json"
DB_FILE = "inventory.db"
LOW_STOCK_THRESHOLD = 5
BACKUP_DIR = "backups"

# --------------------------------------------------------------------- #
#   Data Models
# --------------------------------------------------------------------- #
@dataclass
class Item:
    sku: str
    name: str
    category: str = "General"
    quantity: int = 0
    unit_price: float = 0.0
    total_cost: float = 0.0
    supplier: str = ""
    location: str = "Main Warehouse"
    reorder_point: int = 5
    barcode: str = ""
    created_date: str = ""
    last_updated: str = ""
    salesperson: str = ""  # NEW: Who made the sale
    commission_rate: float = 0.0  # NEW: Commission percentage (e.g., 5.0 for 5%)
    commission_amount: float = 0.0  # NEW: Calculated commission amount

    def __post_init__(self):
        if not self.created_date:
            self.created_date = datetime.now().isoformat()
        if not self.last_updated:
            self.last_updated = datetime.now().isoformat()
        if not self.barcode:
            self.barcode = self._generate_barcode()

    def _generate_barcode(self):
        """Generate a simple barcode"""
        return f"BC{''.join(random.choices(string.digits, k=8))}"

    def purchase(self, qty: int, price_per_unit: float):
        if qty <= 0:
            raise ValueError("Qty must be > 0")
        if price_per_unit < 0:
            raise ValueError("Price cannot be negative")
        new_qty = self.quantity + qty
        if self.quantity > 0:
            new_price = ((self.unit_price * self.quantity) + (price_per_unit * qty)) / new_qty
        else:
            new_price = price_per_unit
        self.quantity = new_qty
        self.unit_price = round(new_price, 4)
        self.total_cost = round(self.total_cost + qty * price_per_unit, 2)
        self.last_updated = datetime.now().isoformat()

    def sell(self, qty: int, sale_price: float = None):
        if qty <= 0:
            raise ValueError("Qty must be > 0")
        if qty > self.quantity:
            raise ValueError("Not enough stock")
        
        if sale_price is None:
            sale_price = self.unit_price
            
        cost_per_unit = self.total_cost / self.quantity if self.quantity > 0 else 0
        self.quantity -= qty
        self.total_cost = round(self.total_cost - (cost_per_unit * qty), 2)
        self.last_updated = datetime.now().isoformat()
        
        # Return profit calculation
        profit = (sale_price - cost_per_unit) * qty
        return round(profit, 2)

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(d):
        return Item(**d)

@dataclass
class Sale:
    id: int
    sku: str
    quantity: int
    sale_price: float
    profit: float
    date: str
    customer: str = ""

@dataclass
class Supplier:
    id: int
    name: str
    contact_person: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""

@dataclass
class User:
    username: str
    password_hash: str
    role: str = "user"  # admin, user
    created_date: str = ""

    def __post_init__(self):
        if not self.created_date:
            self.created_date = datetime.now().isoformat()

# --------------------------------------------------------------------- #
#   Database Manager
# --------------------------------------------------------------------- #
class DatabaseManager:
    def __init__(self, db_path=DB_FILE):
        self.db_path = db_path
        self.init_database()
        self.init_database_with_commission()

    def init_database(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Items table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS items (
                sku TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT DEFAULT 'General',
                quantity INTEGER DEFAULT 0,
                unit_price REAL DEFAULT 0.0,
                total_cost REAL DEFAULT 0.0,
                supplier TEXT DEFAULT '',
                location TEXT DEFAULT 'Main Warehouse',
                reorder_point INTEGER DEFAULT 5,
                barcode TEXT DEFAULT '',
                created_date TEXT,
                last_updated TEXT
            )
        ''')
        
        # Sales table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT,
                quantity INTEGER,
                sale_price REAL,
                profit REAL,
                date TEXT,
                customer TEXT DEFAULT '',
                FOREIGN KEY (sku) REFERENCES items (sku)
            )
        ''')
        
        # Suppliers table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS suppliers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                contact_person TEXT DEFAULT '',
                email TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                address TEXT DEFAULT ''
            )
        ''')
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                created_date TEXT
            )
        ''')
        
        # Audit log table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                action TEXT,
                details TEXT,
                timestamp TEXT
            )
        ''')
        
        # Price history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT,
                old_price REAL,
                new_price REAL,
                change_date TEXT,
                FOREIGN KEY (sku) REFERENCES items (sku)
            )
        ''')
        
        conn.commit()
        conn.close()

    def log_action(self, username: str, action: str, details: str):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO audit_log (username, action, details, timestamp)
            VALUES (?, ?, ?, ?)
        ''', (username, action, details, datetime.now().isoformat()))
        conn.commit()
        conn.close()
      
    # Modify the DatabaseManager to include commission fields
    def init_database_with_commission(self):
      """Enhanced database initialization with commission support"""
      conn = sqlite3.connect(self.db_path)
      cursor = conn.cursor()
      
      # Check if commission columns exist, if not add them
      cursor.execute("PRAGMA table_info(sales)")
      columns = [col[1] for col in cursor.fetchall()]
      
      if 'salesperson' not in columns:
            cursor.execute('ALTER TABLE sales ADD COLUMN salesperson TEXT DEFAULT ""')
      if 'commission_rate' not in columns:
            cursor.execute('ALTER TABLE sales ADD COLUMN commission_rate REAL DEFAULT 0.0')
      if 'commission_amount' not in columns:
            cursor.execute('ALTER TABLE sales ADD COLUMN commission_amount REAL DEFAULT 0.0')
      
      conn.commit()
      conn.close()


# --------------------------------------------------------------------- #
#   Enhanced Inventory Manager
# --------------------------------------------------------------------- #
class EnhancedInventory:
    def __init__(self):
        self.db = DatabaseManager()
        self._items = {}
        self.current_user = None
        self.categories = set()
        self.suppliers = {}
        self.locations = {"Main Warehouse", "Secondary Storage", "Retail Floor"}
        self.load_from_database()

    def set_current_user(self, username):
        self.current_user = username

    def load_from_database(self):
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        # Load items
        cursor.execute('SELECT * FROM items')
        for row in cursor.fetchall():
            item_data = {
                'sku': row[0], 'name': row[1], 'category': row[2],
                'quantity': row[3], 'unit_price': row[4], 'total_cost': row[5],
                'supplier': row[6], 'location': row[7], 'reorder_point': row[8],
                'barcode': row[9], 'created_date': row[10], 'last_updated': row[11]
            }
            self._items[row[0]] = Item.from_dict(item_data)
            self.categories.add(row[2])
        
        # Load suppliers
        cursor.execute('SELECT * FROM suppliers')
        for row in cursor.fetchall():
            self.suppliers[row[0]] = Supplier(row[0], row[1], row[2], row[3], row[4], row[5])
        
        conn.close()

    def save_to_database(self):
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        for sku, item in self._items.items():
            cursor.execute('''
                INSERT OR REPLACE INTO items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (item.sku, item.name, item.category, item.quantity, item.unit_price,
                  item.total_cost, item.supplier, item.location, item.reorder_point,
                  item.barcode, item.created_date, item.last_updated))
        
        conn.commit()
        conn.close()

    def purchase_item(self, sku, name, category, qty, price, supplier="", location="Main Warehouse"):
        sku = sku.upper().strip()
        if sku not in self._items:
            self._items[sku] = Item(sku=sku, name=name or "Unnamed", category=category,
                                   supplier=supplier, location=location)
        
        old_price = self._items[sku].unit_price
        self._items[sku].purchase(qty, price)
        
        # Log price change
        if old_price != self._items[sku].unit_price:
            self._log_price_change(sku, old_price, self._items[sku].unit_price)
        
        self.categories.add(category)
        if self.current_user:
            self.db.log_action(self.current_user, "PURCHASE", 
                             f"Added {qty} units of {sku} at ₦{price} each")

    # Enhanced sell_item method with commission calculation
    def sell_item_with_commission(self, sku, qty, sale_price=None, customer="", salesperson="", commission_rate=0.0):
      """Enhanced sell_item method with commission tracking"""
      if sku not in self._items:
            raise ValueError("Item not found")
      
      profit = self._items[sku].sell(qty, sale_price)
      total_sale = (sale_price or self._items[sku].unit_price) * qty
      commission_amount = total_sale * (commission_rate / 100)
      
      # Record sale with commission
      conn = sqlite3.connect(self.db.db_path)
      cursor = conn.cursor()
      cursor.execute('''
            INSERT INTO sales (sku, quantity, sale_price, profit, date, customer, salesperson, commission_rate, commission_amount)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
      ''', (sku, qty, sale_price or self._items[sku].unit_price, profit, 
            datetime.now().isoformat(), customer, salesperson, commission_rate, commission_amount))
      conn.commit()
      conn.close()
      
      if self.current_user:
            self.db.log_action(self.current_user, "SALE", 
                              f"Sold {qty} units of {sku} for ₦{sale_price or self._items[sku].unit_price} each. Commission: ₦{commission_amount:.2f}")
      
      return profit, commission_amount


    def _log_price_change(self, sku, old_price, new_price):
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO price_history (sku, old_price, new_price, change_date)
            VALUES (?, ?, ?, ?)
        ''', (sku, old_price, new_price, datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def delete_item(self, sku):
        if sku in self._items:
            del self._items[sku]
            # Remove from database
            conn = sqlite3.connect(self.db.db_path)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM items WHERE sku = ?', (sku,))
            conn.commit()
            conn.close()
            
            if self.current_user:
                self.db.log_action(self.current_user, "DELETE", f"Deleted item {sku}")

    def search_items(self, query, category=None, location=None):
        results = {}
        query = query.lower() if query else ""
        
        for sku, item in self._items.items():
            matches = (not query or 
                      query in sku.lower() or 
                      query in item.name.lower() or
                      query in item.barcode.lower())
            
            if category and item.category != category:
                matches = False
            if location and item.location != location:
                matches = False
                
            if matches:
                results[sku] = item
        
        return results

    def get_reorder_suggestions(self):
        return {sku: item for sku, item in self._items.items() 
                if item.quantity <= item.reorder_point}

    # Enhanced get_sales_data method to include commission
    def get_sales_data_with_commission(self, days=30):
      """Get sales data including commission information"""
      conn = sqlite3.connect(self.db.db_path)
      cursor = conn.cursor()
      
      start_date = (datetime.now() - timedelta(days=days)).isoformat()
      cursor.execute('''
            SELECT id, sku, quantity, sale_price, profit, date, customer, 
                  COALESCE(salesperson, '') as salesperson,
                  COALESCE(commission_rate, 0.0) as commission_rate,
                  COALESCE(commission_amount, 0.0) as commission_amount
            FROM sales WHERE date >= ? ORDER BY date DESC
      ''', (start_date,))
      
      sales = []
      for row in cursor.fetchall():
            sale = Sale(row[0], row[1], row[2], row[3], row[4], row[5], row[6])
            sale.salesperson = row[7]
            sale.commission_rate = row[8]
            sale.commission_amount = row[9]
            sales.append(sale)
      
      conn.close()
      return sales

    def get_analytics(self):
        total_items = len(self._items)
        total_value = sum(item.total_cost for item in self._items.values())
        low_stock_count = len([item for item in self._items.values() 
                              if item.quantity <= item.reorder_point])
        
        # Sales analytics
        sales = self.get_sales_data_with_commission(30)
        total_sales = sum(sale.sale_price * sale.quantity for sale in sales)
        total_profit = sum(sale.profit for sale in sales)
        
        return {
            'total_items': total_items,
            'total_value': total_value,
            'low_stock_count': low_stock_count,
            'total_sales_30d': total_sales,
            'total_profit_30d': total_profit,
            'avg_profit_margin': (total_profit / total_sales * 100) if total_sales > 0 else 0
        }

    def export_to_csv(self, filepath):
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['sku', 'name', 'category', 'quantity', 'unit_price', 
                         'total_cost', 'supplier', 'location', 'reorder_point', 'barcode']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for item in self._items.values():
                writer.writerow({
                    'sku': item.sku, 'name': item.name, 'category': item.category,
                    'quantity': item.quantity, 'unit_price': item.unit_price,
                    'total_cost': item.total_cost, 'supplier': item.supplier,
                    'location': item.location, 'reorder_point': item.reorder_point,
                    'barcode': item.barcode
                })

    def import_from_csv(self, filepath):
        imported = 0
        with open(filepath, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                try:
                    sku = row['sku'].upper().strip()
                    self._items[sku] = Item(
                        sku=sku,
                        name=row['name'],
                        category=row.get('category', 'General'),
                        quantity=int(row.get('quantity', 0)),
                        unit_price=float(row.get('unit_price', 0)),
                        total_cost=float(row.get('total_cost', 0)),
                        supplier=row.get('supplier', ''),
                        location=row.get('location', 'Main Warehouse'),
                        reorder_point=int(row.get('reorder_point', 5)),
                        barcode=row.get('barcode', '')
                    )
                    self.categories.add(row.get('category', 'General'))
                    imported += 1
                except (ValueError, KeyError) as e:
                    continue
        
        if self.current_user:
            self.db.log_action(self.current_user, "IMPORT", f"Imported {imported} items from CSV")
        
        return imported

    def backup_data(self):
        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(BACKUP_DIR, f"inventory_backup_{timestamp}.db")
        shutil.copy2(self.db.db_path, backup_file)
        return backup_file

    def list_inventory(self):
        return dict(self._items)

    def total_inventory_value(self):
        return round(sum(i.total_cost for i in self._items.values()), 2)

    def low_stock_items(self):
        return {sku: it for sku, it in self._items.items()
                if it.quantity <= it.reorder_point}


# --------------------------------------------------------------------- #
#   User Management
# --------------------------------------------------------------------- #
class UserManager:
    def __init__(self, db: DatabaseManager):
        self.db = db
        self._ensure_admin_user()

    def _ensure_admin_user(self):
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users WHERE role = "admin"')
        admin_count = cursor.fetchone()[0]
        
        if admin_count == 0:
            # Create default admin
            admin_hash = self._hash_password("admin123")
            cursor.execute('''
                INSERT INTO users (username, password_hash, role, created_date)
                VALUES (?, ?, ?, ?)
            ''', ("admin", admin_hash, "admin", datetime.now().isoformat()))
            conn.commit()
        
        conn.close()

    def _hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()

    def authenticate(self, username, password):
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT password_hash, role FROM users WHERE username = ?', (username,))
        result = cursor.fetchone()
        conn.close()
        
        if result and result[0] == self._hash_password(password):
            return {"username": username, "role": result[1]}
        return None

    def create_user(self, username, password, role="user"):
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        try:
            password_hash = self._hash_password(password)
            cursor.execute('''
                INSERT INTO users (username, password_hash, role, created_date)
                VALUES (?, ?, ?, ?)
            ''', (username, password_hash, role, datetime.now().isoformat()))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()


# --------------------------------------------------------------------- #
#   Enhanced GUI Application
# --------------------------------------------------------------------- #
class EnhancedInventoryApp:
    def __init__(self, master):
        self.master = master
        self.master.title("Advanced Inventory Management System")
        self.master.geometry("1200x800")
        self.master.configure(bg='#f0f8f0')
        
        self.inventory = EnhancedInventory()
        self.user_manager = UserManager(self.inventory.db)
        self.current_user = None
        self.theme = "light"  # light or dark
        
        # Show login first
        self.show_login()


    def show_login(self):
      """Show login dialog"""
      login_window = tk.Toplevel(self.master)
      login_window.title("Login")
      login_window.geometry("380x240")  # Reduced from 450x280
      login_window.configure(bg='#f0f8f0')
      login_window.transient(self.master)
      login_window.grab_set()
      
      # Center the login window
      login_window.geometry("+%d+%d" % (
            self.master.winfo_rootx() + 50,
            self.master.winfo_rooty() + 50))
      
      # Title - smaller
      ttk.Label(login_window, text="🔐 Login", font=('Helvetica', 16, 'bold')).pack(pady=20)
      
      # Create a frame for better organization
      form_frame = ttk.Frame(login_window)
      form_frame.pack(pady=5)
      
      # Username - moderate size
      ttk.Label(form_frame, text="Username:", font=('Helvetica', 11)).pack(pady=(5, 2))
      username_entry = ttk.Entry(form_frame, width=22, font=('Helvetica', 12))
      username_entry.pack(pady=2, ipady=4)
      
      # Password - moderate size
      ttk.Label(form_frame, text="Password:", font=('Helvetica', 11)).pack(pady=(8, 2))
      password_entry = ttk.Entry(form_frame, width=22, font=('Helvetica', 12), show="*")
      password_entry.pack(pady=2, ipady=4)
      
      def do_login():
            username = username_entry.get().strip()
            password = password_entry.get().strip()
            
            if not username or not password:
                  messagebox.showerror("Login Failed", "Please enter both username and password")
                  return
            
            user = self.user_manager.authenticate(username, password)
            if user:
                  self.current_user = user
                  self.inventory.set_current_user(username)
                  login_window.destroy()
                  self._initialize_main_app()
            else:
                  messagebox.showerror("Login Failed", "Invalid username or password")
                  password_entry.delete(0, tk.END)
                  username_entry.focus()
      
      # Login button - moderate size
      login_btn = tk.Button(
            login_window, 
            text="Login", 
            command=do_login,
            font=('Helvetica', 12, 'bold'),
            bg="#4a7c59",
            fg="white",
            activebackground="#5d8b6a",
            activeforeground="white",
            width=12,
            height=1,
            cursor="hand2"
      )
      login_btn.pack(pady=15)
      
      # Default admin credentials hint
      ttk.Label(login_window, text="Default: admin / admin123", 
                  font=('Helvetica', 9), foreground='#666').pack()
      
      # Set focus and bind Enter key
      username_entry.focus()
      username_entry.bind('<Return>', lambda e: password_entry.focus())
      password_entry.bind('<Return>', lambda e: do_login())
      login_window.bind('<Return>', lambda e: do_login())
      login_window.bind('<Escape>', lambda e: login_window.destroy())


    def _initialize_main_app(self):
        """Initialize the main application after login"""
        self._configure_styles()
        
        # Main menu
        self._create_menu()
        
        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set(f"Logged in as: {self.current_user['username']} ({self.current_user['role']})")
        status_bar = ttk.Label(self.master, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Notebook for tabs
        self.nb = ttk.Notebook(self.master, style='Green.TNotebook')
        self.nb.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Create all tabs
        self._create_inventory_tab()
        self._create_enhanced_sales_tab()
        self._create_analytics_tab()
        self._create_suppliers_tab()
        self._create_settings_tab()
        self._create_calculator_tab()
        
        # Auto-save every 5 minutes
        self.master.after(300000, self._auto_save)

    def _create_menu(self):
        """Create application menu"""
        menubar = tk.Menu(self.master)
        self.master.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Import CSV", command=self._import_csv)
        file_menu.add_command(label="Export CSV", command=self._export_csv)
        file_menu.add_separator()
        file_menu.add_command(label="Backup Data", command=self._backup_data)
        file_menu.add_separator()
        file_menu.add_command(label="Logout", command=self._logout)
        file_menu.add_command(label="Exit", command=self._on_close)
        
        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Toggle Theme", command=self._toggle_theme)
        view_menu.add_command(label="Refresh All", command=self._refresh_all)
        
        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Generate Report", command=self._generate_comprehensive_report)
        tools_menu.add_command(label="Reorder Suggestions", command=self._show_reorder_suggestions)
        tools_menu.add_command(label="Price History", command=self._show_price_history)
        
        # Admin menu (only for admins)
        if self.current_user['role'] == 'admin':
            admin_menu = tk.Menu(menubar, tearoff=0)
            menubar.add_cascade(label="Admin", menu=admin_menu)
            admin_menu.add_command(label="User Management", command=self._show_user_management)
            admin_menu.add_command(label="Audit Log", command=self._show_audit_log)

    def _configure_styles(self):
        """Configure custom styles based on theme"""
        style = ttk.Style()
        
        if self.theme == "light":
            bg_color = '#f0f8f0'
            fg_color = '#2d5016'
            accent_color = '#4a7c59'
        else:
            bg_color = '#2d3142'
            fg_color = '#ffffff'
            accent_color = '#4f5d75'
        
        # Configure styles
        style.configure('Green.TNotebook', background=bg_color, tabposition='n')
        style.configure('Green.TNotebook.Tab', 
                       padding=[15, 8], 
                       background=accent_color,
                       foreground='white',
                       font=('Helvetica', 10, 'bold'))
        style.map('Green.TNotebook.Tab',
                 background=[('selected', fg_color), ('active', accent_color)])
        
        style.configure('Green.TFrame', background=bg_color)
        style.configure('Title.TLabel', 
                       background=bg_color,
                       foreground=fg_color,
                       font=('Helvetica', 14, 'bold'))
        style.configure('Green.TLabel', 
                       background=bg_color,
                       foreground=fg_color,
                       font=('Helvetica', 10))

    def _create_inventory_tab(self):
        """Create comprehensive inventory management tab"""
        self.inv_frame = ttk.Frame(self.nb, style='Green.TFrame')
        self.nb.add(self.inv_frame, text="📦 Inventory")
        
        # Main container
        main_container = ttk.Frame(self.inv_frame, style='Green.TFrame')
        main_container.pack(fill='both', expand=True, padx=15, pady=15)
        
        # Search and filter section
        search_frame = ttk.LabelFrame(main_container, text=" Search & Filter ", padding=10)
        search_frame.pack(fill='x', pady=(0, 10))
        
        # Search row
        search_row = ttk.Frame(search_frame)
        search_row.pack(fill='x')
        
        ttk.Label(search_row, text="Search:").pack(side='left', padx=(0, 5))
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_row, textvariable=self.search_var, width=30)
        self.search_entry.pack(side='left', padx=(0, 10))
        self.search_entry.bind('<KeyRelease>', self._on_search)
        
        ttk.Label(search_row, text="Category:").pack(side='left', padx=(10, 5))
        self.category_filter = ttk.Combobox(search_row, width=15, state='readonly')
        self.category_filter.pack(side='left', padx=(0, 10))
        self.category_filter.bind('<<ComboboxSelected>>', self._on_search)
        
        ttk.Label(search_row, text="Location:").pack(side='left', padx=(10, 5))
        self.location_filter = ttk.Combobox(search_row, width=15, state='readonly')
        self.location_filter.pack(side='left', padx=(0, 10))
        self.location_filter.bind('<<ComboboxSelected>>', self._on_search)
        
        ttk.Button(search_row, text="Clear", command=self._clear_search).pack(side='left', padx=(10, 0))
      #   ttk.Button(action_frame, text="🖨️ Print Report", command=self._print_inventory_report).pack(side='left', padx=(5,0))
        
        # Add/Edit item form
        form_frame = ttk.LabelFrame(main_container, text=" Add/Edit Item ", padding=15)
        form_frame.pack(fill='x', pady=(0, 10))
        
        # Form grid
        form_grid = ttk.Frame(form_frame)
        form_grid.pack(fill='x')
        
        # Row 1
        ttk.Label(form_grid, text="SKU:").grid(row=0, column=0, sticky='w', padx=(0,5))
        self.sku_entry = ttk.Entry(form_grid, width=12)
        self.sku_entry.grid(row=0, column=1, sticky='ew', padx=(0,10))
        
        ttk.Label(form_grid, text="Name:").grid(row=0, column=2, sticky='w', padx=(0,5))
        self.name_entry = ttk.Entry(form_grid, width=25)
        self.name_entry.grid(row=0, column=3, sticky='ew', padx=(0,10))
        
        ttk.Label(form_grid, text="Category:").grid(row=0, column=4, sticky='w', padx=(0,5))
        self.category_entry = ttk.Combobox(form_grid, width=15)
        self.category_entry.grid(row=0, column=5, sticky='ew', padx=(0,10))
        
        # Row 2
        ttk.Label(form_grid, text="Qty:").grid(row=1, column=0, sticky='w', padx=(0,5), pady=(10,0))
        self.qty_entry = ttk.Entry(form_grid, width=8)
        self.qty_entry.grid(row=1, column=1, sticky='w', padx=(0,10), pady=(10,0))
        
        ttk.Label(form_grid, text="Price:").grid(row=1, column=2, sticky='w', padx=(0,5), pady=(10,0))
        self.price_entry = ttk.Entry(form_grid, width=12)
        self.price_entry.grid(row=1, column=3, sticky='w', padx=(0,10), pady=(10,0))
        
        ttk.Label(form_grid, text="Supplier:").grid(row=1, column=4, sticky='w', padx=(0,5), pady=(10,0))
        self.supplier_entry = ttk.Combobox(form_grid, width=15)
        self.supplier_entry.grid(row=1, column=5, sticky='ew', padx=(0,10), pady=(10,0))
        
        # Row 3
        ttk.Label(form_grid, text="Location:").grid(row=2, column=0, sticky='w', padx=(0,5), pady=(10,0))
        self.location_entry = ttk.Combobox(form_grid, width=15, values=list(self.inventory.locations))
        self.location_entry.grid(row=2, column=1, sticky='ew', padx=(0,10), pady=(10,0))
        
        ttk.Label(form_grid, text="Reorder Point:").grid(row=2, column=2, sticky='w', padx=(0,5), pady=(10,0))
        self.reorder_entry = ttk.Entry(form_grid, width=8)
        self.reorder_entry.grid(row=2, column=3, sticky='w', padx=(0,10), pady=(10,0))
        
        # Action buttons
        btn_frame = ttk.Frame(form_grid)
        btn_frame.grid(row=2, column=4, columnspan=2, sticky='e', padx=(20,0), pady=(10,0))
        
        ttk.Button(btn_frame, text="➕ Add", command=self._add_item).pack(side='left', padx=(0,5))
        ttk.Button(btn_frame, text="✏️ Update", command=self._update_item).pack(side='left', padx=(0,5))
        ttk.Button(btn_frame, text="🗑️ Delete", command=self._delete_item).pack(side='left')
        
        # Configure grid weights
        for i in range(6):
            form_grid.columnconfigure(i, weight=1)
        
        # Inventory list
        list_frame = ttk.LabelFrame(main_container, text=" Inventory List ", padding=10)
        list_frame.pack(fill='both', expand=True, pady=(0, 10))
        
        # Treeview
        columns = ('SKU', 'Name', 'Category', 'Quantity', 'Unit Price', 'Total Cost', 'Supplier', 'Location', 'Reorder Point', 'Barcode')
        self.tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=15)
        
        # Configure columns
        widths = [80, 200, 100, 80, 100, 120, 120, 120, 100, 120]
        for i, (col, width) in enumerate(zip(columns, widths)):
            self.tree.heading(col, text=col, command=lambda c=col: self._sort_treeview(c))
            self.tree.column(col, width=width, anchor='center' if col in ['SKU', 'Quantity', 'Unit Price', 'Total Cost', 'Reorder Point'] else 'w')
        
        # Scrollbars
        v_scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=self.tree.yview)
        h_scrollbar = ttk.Scrollbar(list_frame, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        self.tree.grid(row=0, column=0, sticky='nsew')
        v_scrollbar.grid(row=0, column=1, sticky='ns')
        h_scrollbar.grid(row=1, column=0, sticky='ew')
        
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        
        # Bind item selection
        self.tree.bind('<<TreeviewSelect>>', self._on_item_select)
        
        # Bottom summary
        summary_frame = ttk.Frame(main_container)
        summary_frame.pack(fill='x')
        
        self.summary_label = ttk.Label(summary_frame, text="", font=('Helvetica', 12, 'bold'))
        self.summary_label.pack(side='left')
        
        # Action buttons
        action_frame = ttk.Frame(summary_frame)
        action_frame.pack(side='right')
        
        actions = [
            ("🔄 Refresh", self._refresh_inventory),
            ("💾 Save", self._save_inventory),
            ("📊 Analytics", lambda: self.nb.select(2)),
            ("📋 Generate Report", self._generate_comprehensive_report)
        ]
        
        for text, command in actions:
            ttk.Button(action_frame, text=text, command=command).pack(side='left', padx=(5,0))
        
        # Initialize
        self._update_form_dropdowns()
        self._refresh_inventory()

    def _create_enhanced_sales_tab(self):
      """Enhanced sales tab with commission support"""
      self.sales_frame = ttk.Frame(self.nb, style='Green.TFrame')
      self.nb.add(self.sales_frame, text="💰 Sales")
      
      main_container = ttk.Frame(self.sales_frame, style='Green.TFrame')
      main_container.pack(fill='both', expand=True, padx=15, pady=15)
      
      # Enhanced Sale form with commission
      sale_form = ttk.LabelFrame(main_container, text=" Record Sale with Commission ", padding=15)
      sale_form.pack(fill='x', pady=(0, 15))
      
      form_grid = ttk.Frame(sale_form)
      form_grid.pack(fill='x')
      
      # Row 1: SKU, Quantity, Sale Price
      ttk.Label(form_grid, text="SKU:").grid(row=0, column=0, sticky='w', padx=(0,5))
      self.sale_sku = ttk.Combobox(form_grid, width=15)
      self.sale_sku.grid(row=0, column=1, sticky='ew', padx=(0,10))
      self.sale_sku.bind('<<ComboboxSelected>>', self._on_sale_sku_select)
      
      ttk.Label(form_grid, text="Quantity:").grid(row=0, column=2, sticky='w', padx=(0,5))
      self.sale_qty = ttk.Entry(form_grid, width=10)
      self.sale_qty.grid(row=0, column=3, sticky='w', padx=(0,10))
      
      ttk.Label(form_grid, text="Sale Price:").grid(row=0, column=4, sticky='w', padx=(0,5))
      self.sale_price = ttk.Entry(form_grid, width=12)
      self.sale_price.grid(row=0, column=5, sticky='w', padx=(0,10))
      
      # Row 2: Customer, Salesperson, Commission Rate
      ttk.Label(form_grid, text="Customer:").grid(row=1, column=0, sticky='w', padx=(0,5), pady=(10,0))
      self.sale_customer = ttk.Entry(form_grid, width=15)
      self.sale_customer.grid(row=1, column=1, sticky='ew', padx=(0,10), pady=(10,0))
      
      ttk.Label(form_grid, text="Salesperson:").grid(row=1, column=2, sticky='w', padx=(0,5), pady=(10,0))
      self.sale_salesperson = ttk.Entry(form_grid, width=15)
      self.sale_salesperson.grid(row=1, column=3, sticky='w', padx=(0,10), pady=(10,0))
      
      ttk.Label(form_grid, text="Commission %:").grid(row=1, column=4, sticky='w', padx=(0,5), pady=(10,0))
      self.sale_commission = ttk.Entry(form_grid, width=8)
      self.sale_commission.grid(row=1, column=5, sticky='w', padx=(0,10), pady=(10,0))
      self.sale_commission.insert(0, "5.0")  # Default 5% commission
      
      # Row 3: Record Sale button and commission preview
      ttk.Button(form_grid, text="💰 Record Sale", command=self._record_enhanced_sale).grid(row=2, column=0, columnspan=2, pady=(10,0))
      
      self.commission_preview = ttk.Label(form_grid, text="", foreground='green', font=('Helvetica', 10, 'bold'))
      self.commission_preview.grid(row=2, column=2, columnspan=4, pady=(10,0), sticky='w')
      
      # Bind events for live commission calculation
      self.sale_qty.bind('<KeyRelease>', self._calculate_commission_preview)
      self.sale_price.bind('<KeyRelease>', self._calculate_commission_preview)
      self.sale_commission.bind('<KeyRelease>', self._calculate_commission_preview)
      
      # Available stock info
      self.stock_info = ttk.Label(form_grid, text="", foreground='blue')
      self.stock_info.grid(row=3, column=0, columnspan=6, pady=(10,0))
      
      # Enhanced Sales history with commission
      history_frame = ttk.LabelFrame(main_container, text=" Sales History with Commission ", padding=10)
      history_frame.pack(fill='both', expand=True)
      
      # Filter and print controls
      filter_frame = ttk.Frame(history_frame)
      filter_frame.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0,10))
      
      ttk.Label(filter_frame, text="Show sales from last:").pack(side='left', padx=(0,5))
      self.sales_period = ttk.Combobox(filter_frame, width=10, values=['7 days', '30 days', '90 days', '1 year'], state='readonly')
      self.sales_period.set('30 days')
      self.sales_period.pack(side='left', padx=(0,10))
      self.sales_period.bind('<<ComboboxSelected>>', self._refresh_enhanced_sales_history)
      
      ttk.Button(filter_frame, text="🔄 Refresh", command=self._refresh_enhanced_sales_history).pack(side='left', padx=(10,0))
      ttk.Button(filter_frame, text="🖨️ Print Sales Report", command=self._print_sales_report).pack(side='left', padx=(10,0))
      ttk.Button(filter_frame, text="📊 Commission Report", command=self._show_commission_report).pack(side='left', padx=(10,0))
      
      # Enhanced Sales tree with commission columns
      sales_columns = ('Date', 'SKU', 'Quantity', 'Sale Price', 'Total Sale', 'Profit', 'Customer', 'Salesperson', 'Commission %', 'Commission ₦')
      self.sales_tree = ttk.Treeview(history_frame, columns=sales_columns, show='headings', height=12)
      
      column_widths = {
            'Date': 120, 'SKU': 80, 'Quantity': 80, 'Sale Price': 100, 'Total Sale': 100,
            'Profit': 100, 'Customer': 120, 'Salesperson': 120, 'Commission %': 100, 'Commission ₦': 100
      }
      
      for col in sales_columns:
            self.sales_tree.heading(col, text=col)
            width = column_widths.get(col, 100)
            self.sales_tree.column(col, width=width, anchor='center')
      
      # Sales scrollbars
      sales_v_scroll = ttk.Scrollbar(history_frame, orient='vertical', command=self.sales_tree.yview)
      sales_h_scroll = ttk.Scrollbar(history_frame, orient='horizontal', command=self.sales_tree.xview)
      self.sales_tree.configure(yscrollcommand=sales_v_scroll.set, xscrollcommand=sales_h_scroll.set)
      
      self.sales_tree.grid(row=1, column=0, sticky='nsew')
      sales_v_scroll.grid(row=1, column=1, sticky='ns')
      sales_h_scroll.grid(row=2, column=0, sticky='ew')
      
      # Configure grid weights
      history_frame.grid_rowconfigure(1, weight=1)
      history_frame.grid_columnconfigure(0, weight=1)
      
      # Enhanced sales summary with commission totals
      self.sales_summary = ttk.Label(history_frame, text="", font=('Helvetica', 12, 'bold'))
      self.sales_summary.grid(row=3, column=0, columnspan=2, pady=(10,0))
      
      self._refresh_sales_form()
      self._refresh_enhanced_sales_history()

      # Commission calculation and preview methods
    def _calculate_commission_preview(self, event=None):
      """Calculate and display commission preview"""
      try:
            qty = float(self.sale_qty.get() or 0)
            price = float(self.sale_price.get() or 0)
            commission_rate = float(self.sale_commission.get() or 0)
            
            total_sale = qty * price
            commission_amount = total_sale * (commission_rate / 100)
            
            if total_sale > 0:
                  self.commission_preview.config(
                  text=f"Total Sale: ₦{total_sale:.2f} | Commission: ₦{commission_amount:.2f}"
                  )
            else:
                  self.commission_preview.config(text="")
      except ValueError:
            self.commission_preview.config(text="")

    def _record_enhanced_sale(self):
      """Record a sale with commission tracking"""
      try:
            sku = self.sale_sku.get().strip().upper()
            qty = int(self.sale_qty.get().strip())
            price = float(self.sale_price.get().strip())
            customer = self.sale_customer.get().strip()
            salesperson = self.sale_salesperson.get().strip()
            commission_rate = float(self.sale_commission.get().strip() or 0)
            
            if not sku:
                  messagebox.showwarning("Invalid Input", "Please select a SKU!")
                  return
            
            if sku not in self.inventory._items:
                  messagebox.showwarning("Item Not Found", "Selected item not found!")
                  return
            
            if qty <= 0:
                  messagebox.showwarning("Invalid Input", "Quantity must be greater than 0!")
                  return
            
            # Use the enhanced sell_item method
            profit, commission_amount = self.inventory.sell_item_with_commission(
                  sku, qty, price, customer, salesperson, commission_rate
            )
            
            # Clear form
            self.sale_qty.delete(0, tk.END)
            self.sale_customer.delete(0, tk.END)
            self.sale_salesperson.delete(0, tk.END)
            self.stock_info.config(text="")
            self.commission_preview.config(text="")
            
            self._refresh_enhanced_sales_history()
            self._refresh_inventory()
            
            total_sale = price * qty
            messagebox.showinfo("Success", 
                  f"Sale recorded successfully!\n\n"
                  f"Total Sale: ₦{total_sale:.2f}\n"
                  f"Profit: ₦{profit:.2f}\n"
                  f"Commission: ₦{commission_amount:.2f}\n"
                  f"Remaining stock: {self.inventory._items[sku].quantity}"
            )
            
      except ValueError as e:
            if "Not enough stock" in str(e):
                  messagebox.showwarning("Insufficient Stock", str(e))
            else:
                  messagebox.showerror("Invalid Input", "Please enter valid numbers!")
      except Exception as e:
            messagebox.showerror("Error", f"Failed to record sale: {str(e)}")

    def _refresh_enhanced_sales_history(self, event=None):
      """Refresh sales history with commission data"""
      # Clear existing items
      for item in self.sales_tree.get_children():
            self.sales_tree.delete(item)
      
      # Get period
      period_text = self.sales_period.get()
      days = {'7 days': 7, '30 days': 30, '90 days': 90, '1 year': 365}[period_text]
      
      sales = self.inventory.get_sales_data_with_commission(days)
      
      total_sales = 0
      total_profit = 0
      total_commission = 0
      
      for sale in sales:
            date_str = datetime.fromisoformat(sale.date).strftime('%Y-%m-%d %H:%M')
            total_sale = sale.sale_price * sale.quantity
            
            self.sales_tree.insert('', 'end', values=(
                  date_str, sale.sku, sale.quantity, f"₦{sale.sale_price:.2f}",
                  f"₦{total_sale:.2f}", f"₦{sale.profit:.2f}", sale.customer,
                  sale.salesperson, f"{sale.commission_rate:.1f}%", f"₦{sale.commission_amount:.2f}"
            ))
            
            total_sales += total_sale
            total_profit += sale.profit
            total_commission += sale.commission_amount
      
      # Update summary with commission totals
      profit_margin = (total_profit / total_sales * 100) if total_sales > 0 else 0
      commission_rate = (total_commission / total_sales * 100) if total_sales > 0 else 0
      
      self.sales_summary.config(
            text=f"Period: {period_text} | Sales: ₦{total_sales:.2f} | "
                  f"Profit: ₦{total_profit:.2f} ({profit_margin:.1f}%) | "
                  f"Total Commission: ₦{total_commission:.2f} ({commission_rate:.1f}%)"
      )

      # Print functionality methods
    def _print_sales_report(self):
      """Generate and print sales report"""
      period_text = self.sales_period.get()
      days = {'7 days': 7, '30 days': 30, '90 days': 90, '1 year': 365}[period_text]
      sales = self.inventory.get_sales_data_with_commission(days)
      
      # Generate HTML report
      html_content = self._generate_sales_html_report(sales, period_text)
      
      # Save to temporary file and open in browser
      with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            f.write(html_content)
            temp_file = f.name
      
      # Open in default browser for printing
      webbrowser.open(f'file://{temp_file}')
      messagebox.showinfo("Print Report", "Sales report opened in browser. Use Ctrl+P to print.")

    def _generate_sales_html_report(self, sales, period):
      """Generate HTML sales report for printing"""
      total_sales = sum(sale.sale_price * sale.quantity for sale in sales)
      total_profit = sum(sale.profit for sale in sales)
      total_commission = sum(sale.commission_amount for sale in sales)
      
      html = f"""
      <!DOCTYPE html>
      <html>
      <head>
            <title>Sales Report - {period}</title>
            <style>
                  body {{ font-family: Arial, sans-serif; margin: 20px; }}
                  .header {{ text-align: center; margin-bottom: 30px; }}
                  .summary {{ background-color: #f0f8f0; padding: 15px; margin-bottom: 20px; border-radius: 5px; }}
                  table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
                  th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                  th {{ background-color: #4a7c59; color: white; }}
                  tr:nth-child(even) {{ background-color: #f9f9f9; }}
                  .total-row {{ font-weight: bold; background-color: #e8f5e8; }}
                  .print-date {{ text-align: right; font-size: 12px; color: #666; }}
                  @media print {{
                  body {{ margin: 0; }}
                  .no-print {{ display: none; }}
                  }}
            </style>
      </head>
      <body>
            <div class="header">
                  <h1>📊 Sales Report</h1>
                  <h2>Period: {period}</h2>
                  <div class="print-date">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
            </div>
            
            <div class="summary">
                  <h3>📈 Summary</h3>
                  <p><strong>Total Sales:</strong> ₦{total_sales:.2f}</p>
                  <p><strong>Total Profit:</strong> ₦{total_profit:.2f}</p>
                  <p><strong>Total Commission:</strong> ₦{total_commission:.2f}</p>
                  <p><strong>Number of Transactions:</strong> {len(sales)}</p>
                  <p><strong>Average Sale:</strong> ₦{'%.2f' % (total_sales/len(sales)) if sales else '0.00'}</p>
            </div>
            
            <table>
                  <thead>
                  <tr>
                        <th>Date</th>
                        <th>SKU</th>
                        <th>Qty</th>
                        <th>Unit Price</th>
                        <th>Total Sale</th>
                        <th>Profit</th>
                        <th>Customer</th>
                        <th>Salesperson</th>
                        <th>Commission %</th>
                        <th>Commission ₦</th>
                  </tr>
                  </thead>
                  <tbody>
      """
      
      for sale in sales:
            date_str = datetime.fromisoformat(sale.date).strftime('%Y-%m-%d %H:%M')
            total_sale = sale.sale_price * sale.quantity
            
            html += f"""
                  <tr>
                        <td>{date_str}</td>
                        <td>{sale.sku}</td>
                        <td>{sale.quantity}</td>
                        <td>₦{sale.sale_price:.2f}</td>
                        <td>₦{total_sale:.2f}</td>
                        <td>₦{sale.profit:.2f}</td>
                        <td>{sale.customer}</td>
                        <td>{sale.salesperson}</td>
                        <td>{sale.commission_rate:.1f}%</td>
                        <td>₦{sale.commission_amount:.2f}</td>
                  </tr>
            """
      
      html += f"""
                  </tbody>
                  <tfoot>
                  <tr class="total-row">
                        <td colspan="4"><strong>TOTALS</strong></td>
                        <td><strong>₦{total_sales:.2f}</strong></td>
                        <td><strong>₦{total_profit:.2f}</strong></td>
                        <td colspan="3"></td>
                        <td><strong>₦{total_commission:.2f}</strong></td>
                  </tr>
                  </tfoot>
            </table>
            
            <div class="print-date">
                  <p>Report generated by: {self.current_user['username']} | Advanced Inventory Management System</p>
            </div>
      </body>
      </html>
      """
      
      return html

    def _show_commission_report(self):
      """Show detailed commission report window"""
      period_text = self.sales_period.get()
      days = {'7 days': 7, '30 days': 30, '90 days': 90, '1 year': 365}[period_text]
      sales = self.inventory.get_sales_data_with_commission(days)
      
      # Calculate commission by salesperson
      commission_by_person = {}
      for sale in sales:
            person = sale.salesperson or "No Salesperson"
            if person not in commission_by_person:
                  commission_by_person[person] = {'sales': 0, 'commission': 0, 'transactions': 0}
            
            commission_by_person[person]['sales'] += sale.sale_price * sale.quantity
            commission_by_person[person]['commission'] += sale.commission_amount
            commission_by_person[person]['transactions'] += 1
      
      # Create commission report window
      comm_window = tk.Toplevel(self.master)
      comm_window.title("Commission Report")
      comm_window.geometry("700x500")
      comm_window.configure(bg='#f0f8f0')
      
      # Header
      header_label = ttk.Label(comm_window, text=f"💰 Commission Report - {period_text}", 
                              font=('Helvetica', 14, 'bold'))
      header_label.pack(pady=10)
      
      # Commission summary tree
      comm_columns = ('Salesperson', 'Transactions', 'Total Sales', 'Total Commission', 'Avg Commission')
      comm_tree = ttk.Treeview(comm_window, columns=comm_columns, show='headings', height=15)
      
      for col in comm_columns:
            comm_tree.heading(col, text=col)
            width = 120 if col in ['Total Sales', 'Total Commission', 'Avg Commission'] else 100
            if col == 'Salesperson':
                  width = 150
            comm_tree.column(col, width=width, anchor='center')
      
      # Populate commission data
      total_all_sales = 0
      total_all_commission = 0
      
      for person, data in sorted(commission_by_person.items(), key=lambda x: x[1]['commission'], reverse=True):
            avg_commission = data['commission'] / data['transactions'] if data['transactions'] > 0 else 0
            
            comm_tree.insert('', 'end', values=(
                  person, data['transactions'], f"₦{data['sales']:.2f}",
                  f"₦{data['commission']:.2f}", f"₦{avg_commission:.2f}"
            ))
            
            total_all_sales += data['sales']
            total_all_commission += data['commission']
      
      # Add totals row
      comm_tree.insert('', 'end', values=(
            "TOTAL", sum(d['transactions'] for d in commission_by_person.values()),
            f"₦{total_all_sales:.2f}", f"₦{total_all_commission:.2f}", ""
      ), tags=('total',))
      
      # Configure total row style
      comm_tree.tag_configure('total', background='#e8f5e8', font=('Helvetica', 10, 'bold'))
      
      # Scrollbar
      comm_scroll = ttk.Scrollbar(comm_window, orient='vertical', command=comm_tree.yview)
      comm_tree.configure(yscrollcommand=comm_scroll.set)
      
      comm_tree.pack(side='left', fill='both', expand=True, padx=(10,0), pady=10)
      comm_scroll.pack(side='right', fill='y', padx=(0,10), pady=10)
      
      # Print button for commission report
      print_btn = ttk.Button(comm_window, text="🖨️ Print Commission Report", 
                              command=lambda: self._print_commission_report(commission_by_person, period_text))
      print_btn.pack(pady=10)

    def _print_commission_report(self, commission_data, period):
      """Print commission report"""
      html_content = self._generate_commission_html_report(commission_data, period)
      
      with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            f.write(html_content)
            temp_file = f.name
      
      webbrowser.open(f'file://{temp_file}')
      messagebox.showinfo("Print Report", "Commission report opened in browser. Use Ctrl+P to print.")

    def _generate_commission_html_report(self, commission_data, period):
      """Generate HTML commission report"""
      total_sales = sum(data['sales'] for data in commission_data.values())
      total_commission = sum(data['commission'] for data in commission_data.values())
      total_transactions = sum(data['transactions'] for data in commission_data.values())
      
      html = f"""
      <!DOCTYPE html>
      <html>
      <head>
            <title>Commission Report - {period}</title>
            <style>
                  body {{ font-family: Arial, sans-serif; margin: 20px; }}
                  .header {{ text-align: center; margin-bottom: 30px; }}
                  .summary {{ background-color: #f0f8f0; padding: 15px; margin-bottom: 20px; border-radius: 5px; }}
                  table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
                  th, td {{ border: 1px solid #ddd; padding: 8px; text-align: center; }}
                  th {{ background-color: #4a7c59; color: white; }}
                  tr:nth-child(even) {{ background-color: #f9f9f9; }}
                  .total-row {{ font-weight: bold; background-color: #e8f5e8; }}
                  .print-date {{ text-align: right; font-size: 12px; color: #666; }}
            </style>
      </head>
      <body>
            <div class="header">
                  <h1>💰 Commission Report</h1>
                  <h2>Period: {period}</h2>
                  <div class="print-date">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
            </div>
            
            <div class="summary">
                  <h3>📊 Commission Summary</h3>
                  <p><strong>Total Sales:</strong> ₦{total_sales:.2f}</p>
                  <p><strong>Total Commission Paid:</strong> ₦{total_commission:.2f}</p>
                  <p><strong>Total Transactions:</strong> {total_transactions}</p>
                  <p><strong>Average Commission per Transaction:</strong> ₦{total_commission/total_transactions:.2f if total_transactions > 0 else 0}</p>
                  <p><strong>Commission Rate:</strong> {total_commission/total_sales*100:.2f}% of total sales</p>
            </div>
            
            <table>
                  <thead>
                  <tr>
                        <th>Salesperson</th>
                        <th>Transactions</th>
                        <th>Total Sales</th>
                        <th>Commission Earned</th>
                        <th>Avg per Transaction</th>
                        <th>Commission Rate</th>
                  </tr>
                  </thead>
                  <tbody>
      """
      
      for person, data in sorted(commission_data.items(), key=lambda x: x[1]['commission'], reverse=True):
            avg_commission = data['commission'] / data['transactions'] if data['transactions'] > 0 else 0
            commission_rate = data['commission'] / data['sales'] * 100 if data['sales'] > 0 else 0
            
            html += f"""
                  <tr>
                        <td>{person}</td>
                        <td>{data['transactions']}</td>
                        <td>₦{data['sales']:.2f}</td>
                        <td>₦{data['commission']:.2f}</td>
                        <td>₦{avg_commission:.2f}</td>
                        <td>{commission_rate:.2f}%</td>
                  </tr>
            """
      
      html += f"""
                  </tbody>
                  <tfoot>
                  <tr class="total-row">
                        <td><strong>TOTALS</strong></td>
                        <td><strong>{total_transactions}</strong></td>
                        <td><strong>₦{total_sales:.2f}</strong></td>
                        <td><strong>₦{total_commission:.2f}</strong></td>
                        <td><strong>₦{total_commission/total_transactions:.2f if total_transactions > 0 else 0}</strong></td>
                        <td><strong>{total_commission/total_sales*100:.2f if total_sales > 0 else 0}%</strong></td>
                  </tr>
                  </tfoot>
            </table>
            
            <div class="print-date">
                  <p>Report generated by: {self.current_user['username']} | Advanced Inventory Management System</p>
            </div>
      </body>
      </html>
      """
      
      return html

      # Add print functionality to main inventory view
    def _print_inventory_report(self):
      """Print current inventory report"""
      items = self.inventory.list_inventory()
      html_content = self._generate_inventory_html_report(items)
      
      with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            f.write(html_content)
            temp_file = f.name
      
      webbrowser.open(f'file://{temp_file}')
      messagebox.showinfo("Print Report", "Inventory report opened in browser. Use Ctrl+P to print.")

    def _generate_inventory_html_report(self, items):
      """Generate HTML inventory report for printing"""
      total_items = len(items)
      total_value = sum(item.total_cost for item in items.values())
      total_quantity = sum(item.quantity for item in items.values())
      low_stock_items = [item for item in items.values() if item.quantity <= item.reorder_point]
      
      # Group by category
      categories = {}
      for item in items.values():
            if item.category not in categories:
                  categories[item.category] = {'items': 0, 'value': 0, 'qty': 0}
            categories[item.category]['items'] += 1
            categories[item.category]['value'] += item.total_cost
            categories[item.category]['qty'] += item.quantity
      
      html = f"""
      <!DOCTYPE html>
      <html>
      <head>
            <title>Inventory Report</title>
            <style>
                  body {{ font-family: Arial, sans-serif; margin: 20px; }}
                  .header {{ text-align: center; margin-bottom: 30px; }}
                  .summary {{ background-color: #f0f8f0; padding: 15px; margin-bottom: 20px; border-radius: 5px; }}
                  .category-summary {{ background-color: #fff3e0; padding: 15px; margin-bottom: 20px; border-radius: 5px; }}
                  .low-stock {{ background-color: #ffebee; padding: 15px; margin-bottom: 20px; border-radius: 5px; }}
                  table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 12px; }}
                  th, td {{ border: 1px solid #ddd; padding: 6px; text-align: left; }}
                  th {{ background-color: #4a7c59; color: white; }}
                  tr:nth-child(even) {{ background-color: #f9f9f9; }}
                  .low-stock-row {{ background-color: #ffcdd2; }}
                  .print-date {{ text-align: right; font-size: 12px; color: #666; }}
                  .page-break {{ page-break-before: always; }}
                  @media print {{
                  body {{ margin: 0; }}
                  .no-print {{ display: none; }}
                  }}
            </style>
      </head>
      <body>
            <div class="header">
                  <h1>📦 Inventory Report</h1>
                  <div class="print-date">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
            </div>
            
            <div class="summary">
                  <h3>📊 Inventory Summary</h3>
                  <p><strong>Total Items:</strong> {total_items}</p>
                  <p><strong>Total Quantity:</strong> {total_quantity:,}</p>
                  <p><strong>Total Value:</strong> ₦{total_value:,.2f}</p>
                  <p><strong>Low Stock Items:</strong> {len(low_stock_items)}</p>
                  <p><strong>Average Value per Item:</strong> ₦{total_value/total_items:.2f if total_items > 0 else 0}</p>
            </div>
            
            <div class="category-summary">
                  <h3>📋 Category Breakdown</h3>
                  <table>
                  <thead>
                        <tr>
                              <th>Category</th>
                              <th>Items</th>
                              <th>Total Quantity</th>
                              <th>Total Value</th>
                              <th>% of Total Value</th>
                        </tr>
                  </thead>
                  <tbody>
      """
      
      for category, data in sorted(categories.items(), key=lambda x: x[1]['value'], reverse=True):
            percentage = (data['value'] / total_value * 100) if total_value > 0 else 0
            html += f"""
                        <tr>
                              <td>{category}</td>
                              <td>{data['items']}</td>
                              <td>{data['qty']:,}</td>
                              <td>₦{data['value']:,.2f}</td>
                              <td>{percentage:.1f}%</td>
                        </tr>
            """
      
      html += """
                  </tbody>
                  </table>
            </div>
      """
      
      if low_stock_items:
            html += f"""
            <div class="low-stock">
                  <h3>⚠️ Low Stock Alert ({len(low_stock_items)} items)</h3>
                  <table>
                  <thead>
                        <tr>
                              <th>SKU</th>
                              <th>Name</th>
                              <th>Current Stock</th>
                              <th>Reorder Point</th>
                              <th>Suggested Order</th>
                        </tr>
                  </thead>
                  <tbody>
            """
            
            for item in sorted(low_stock_items, key=lambda x: x.quantity):
                  suggested_qty = max(item.reorder_point * 2, 10)
                  html += f"""
                        <tr>
                              <td>{item.sku}</td>
                              <td>{item.name}</td>
                              <td>{item.quantity}</td>
                              <td>{item.reorder_point}</td>
                              <td>{suggested_qty}</td>
                        </tr>
                  """
            
            html += """
                  </tbody>
                  </table>
            </div>
            """
      
      html += f"""
            <div class="page-break"></div>
            <h3>📋 Complete Inventory Listing</h3>
            <table>
                  <thead>
                  <tr>
                        <th>SKU</th>
                        <th>Name</th>
                        <th>Category</th>
                        <th>Qty</th>
                        <th>Unit Price</th>
                        <th>Total Cost</th>
                        <th>Supplier</th>
                        <th>Location</th>
                        <th>Reorder Point</th>
                        <th>Status</th>
                  </tr>
                  </thead>
                  <tbody>
      """
      
      for item in sorted(items.values(), key=lambda x: x.sku):
            status = "⚠️ LOW STOCK" if item.quantity <= item.reorder_point else "✅ OK"
            row_class = "low-stock-row" if item.quantity <= item.reorder_point else ""
            
            html += f"""
                  <tr class="{row_class}">
                        <td>{item.sku}</td>
                        <td>{item.name}</td>
                        <td>{item.category}</td>
                        <td>{item.quantity}</td>
                        <td>₦{item.unit_price:.2f}</td>
                        <td>₦{item.total_cost:.2f}</td>
                        <td>{item.supplier}</td>
                        <td>{item.location}</td>
                        <td>{item.reorder_point}</td>
                        <td>{status}</td>
                  </tr>
            """
      
      html += f"""
                  </tbody>
            </table>
            
            <div class="print-date">
                  <p>Report generated by: {self.current_user['username']} | Advanced Inventory Management System</p>
            </div>
      </body>
      </html>
      """
      
      return html

      # Enhanced analytics with commission data
    def _refresh_enhanced_analytics(self):
      """Refresh analytics data including commission metrics"""
      analytics = self.inventory.get_analytics()
      
      # Get commission data
      sales_30d = self.inventory.get_sales_data_with_commission(30)
      total_commission_30d = sum(sale.commission_amount for sale in sales_30d)
      
      self.metrics_vars['total_items'].set(str(analytics['total_items']))
      self.metrics_vars['total_value'].set(f"₦{analytics['total_value']:,.2f}")
      self.metrics_vars['low_stock'].set(str(analytics['low_stock_count']))
      self.metrics_vars['sales_30d'].set(f"₦{analytics['total_sales_30d']:,.2f}")
      self.metrics_vars['profit_30d'].set(f"₦{analytics['total_profit_30d']:,.2f}")
      self.metrics_vars['margin'].set(f"{analytics['avg_profit_margin']:.1f}%")

      # Add commission metric if it doesn't exist
      if 'commission_30d' not in self.metrics_vars:
            # You would need to add this to the metrics display in _create_analytics_tab
            pass


      # Method to add print buttons to existing tabs
    def _add_print_buttons_to_inventory_tab(self):
      """Add print button to inventory tab - call this in _create_inventory_tab"""
      # Add this to the action_frame in your existing _create_inventory_tab method
      ttk.Button(action_frame, text="🖨️ Print Report", command=self._print_inventory_report).pack(side='left', padx=(5,0))

            
    def _create_analytics_tab(self):
            """Create analytics and reporting tab"""
            self.analytics_frame = ttk.Frame(self.nb, style='Green.TFrame')
            self.nb.add(self.analytics_frame, text="📊 Analytics")
            
            main_container = ttk.Frame(self.analytics_frame, style='Green.TFrame')
            main_container.pack(fill='both', expand=True, padx=15, pady=15)
            
            # Top metrics
            metrics_frame = ttk.LabelFrame(main_container, text=" Key Metrics ", padding=15)
            metrics_frame.pack(fill='x', pady=(0, 15))
            
            # Metrics grid
            self.metrics_vars = {}
            metrics = [
                  ("Total Items", "total_items"),
                  ("Total Value", "total_value"),
                  ("Low Stock Items", "low_stock"),
                  ("30-Day Sales", "sales_30d"),
                  ("30-Day Profit", "profit_30d"),
                  ("Avg Profit Margin", "margin")
            ]
            
            for i, (label, key) in enumerate(metrics):
                  frame = ttk.Frame(metrics_frame)
                  frame.grid(row=i//3, column=i%3, padx=20, pady=10, sticky='ew')
                  
                  ttk.Label(frame, text=label, font=('Helvetica', 10, 'bold')).pack()
                  var = tk.StringVar()
                  self.metrics_vars[key] = var
                  ttk.Label(frame, textvariable=var, font=('Helvetica', 14), foreground='#2d5016').pack()
            
            for i in range(3):
                  metrics_frame.columnconfigure(i, weight=1)
            
            # Charts section
            charts_frame = ttk.LabelFrame(main_container, text=" Analytics Charts ", padding=10)
            charts_frame.pack(fill='both', expand=True)
            
            # Chart controls
            chart_controls = ttk.Frame(charts_frame)
            chart_controls.pack(fill='x', pady=(0, 10))
            
            ttk.Button(chart_controls, text="📈 Sales Trend", command=self._show_sales_chart).pack(side='left', padx=(0,10))
            ttk.Button(chart_controls, text="📊 Category Analysis", command=self._show_category_chart).pack(side='left', padx=(0,10))
            ttk.Button(chart_controls, text="🏆 Top Items", command=self._show_top_items_chart).pack(side='left', padx=(0,10))
            ttk.Button(chart_controls, text="⚠️ Stock Levels", command=self._show_stock_chart).pack(side='left')
            
            # Chart display area
            self.chart_frame = ttk.Frame(charts_frame)
            self.chart_frame.pack(fill='both', expand=True)
            
            self._refresh_analytics()

    def _create_suppliers_tab(self):
            """Create suppliers management tab"""
            self.suppliers_frame = ttk.Frame(self.nb, style='Green.TFrame')
            self.nb.add(self.suppliers_frame, text="🏢 Suppliers")
            
            main_container = ttk.Frame(self.suppliers_frame, style='Green.TFrame')
            main_container.pack(fill='both', expand=True, padx=15, pady=15)
            
            # Supplier form
            supplier_form = ttk.LabelFrame(main_container, text=" Add/Edit Supplier ", padding=15)
            supplier_form.pack(fill='x', pady=(0, 15))
            
            form_grid = ttk.Frame(supplier_form)
            form_grid.pack(fill='x')
            
            # Row 1
            ttk.Label(form_grid, text="Name:").grid(row=0, column=0, sticky='w', padx=(0,5))
            self.supplier_name = ttk.Entry(form_grid, width=25)
            self.supplier_name.grid(row=0, column=1, sticky='ew', padx=(0,15))
            
            ttk.Label(form_grid, text="Contact Person:").grid(row=0, column=2, sticky='w', padx=(0,5))
            self.supplier_contact = ttk.Entry(form_grid, width=25)
            self.supplier_contact.grid(row=0, column=3, sticky='ew', padx=(0,15))
            
            # Row 2
            ttk.Label(form_grid, text="Email:").grid(row=1, column=0, sticky='w', padx=(0,5), pady=(10,0))
            self.supplier_email = ttk.Entry(form_grid, width=25)
            self.supplier_email.grid(row=1, column=1, sticky='ew', padx=(0,15), pady=(10,0))
            
            ttk.Label(form_grid, text="Phone:").grid(row=1, column=2, sticky='w', padx=(0,5), pady=(10,0))
            self.supplier_phone = ttk.Entry(form_grid, width=25)
            self.supplier_phone.grid(row=1, column=3, sticky='ew', padx=(0,15), pady=(10,0))
            
            # Row 3
            ttk.Label(form_grid, text="Address:").grid(row=2, column=0, sticky='w', padx=(0,5), pady=(10,0))
            self.supplier_address = ttk.Entry(form_grid, width=50)
            self.supplier_address.grid(row=2, column=1, columnspan=2, sticky='ew', padx=(0,15), pady=(10,0))
            
            # Buttons
            btn_frame = ttk.Frame(form_grid)
            btn_frame.grid(row=2, column=3, sticky='e', pady=(10,0))
            
            ttk.Button(btn_frame, text="➕ Add", command=self._add_supplier).pack(side='left', padx=(0,5))
            ttk.Button(btn_frame, text="✏️ Update", command=self._update_supplier).pack(side='left', padx=(0,5))
            ttk.Button(btn_frame, text="🗑️ Delete", command=self._delete_supplier).pack(side='left')
            
            # Configure grid
            form_grid.columnconfigure(1, weight=1)
            form_grid.columnconfigure(3, weight=1)
            
            # Suppliers list
            list_frame = ttk.LabelFrame(main_container, text=" Suppliers List ", padding=10)
            list_frame.pack(fill='both', expand=True)
            
            supplier_columns = ('ID', 'Name', 'Contact Person', 'Email', 'Phone', 'Address')
            self.suppliers_tree = ttk.Treeview(list_frame, columns=supplier_columns, show='headings', height=15)
            
            # for col in supplier_columns:
            # self.suppliers_tree.heading(col, text=col)
            # width = 60 if col == 'ID' else 150
            # if col == 'Address':
            # width = 250
            # self.suppliers_tree.column(col, width=width, anchor='center' if col == 'ID' else 'w')

            for col in supplier_columns:
                  self.suppliers_tree.heading(col, text=col)
                  width = 60 if col == 'ID' else 150
                  if col == 'Address':
                        width = 250
                  self.suppliers_tree.column(col, width=width, anchor='center' if col == 'ID' else 'w')
                              
            # Scrollbars
            sup_v_scroll = ttk.Scrollbar(list_frame, orient='vertical', command=self.suppliers_tree.yview)
            sup_h_scroll = ttk.Scrollbar(list_frame, orient='horizontal', command=self.suppliers_tree.xview)
            self.suppliers_tree.configure(yscrollcommand=sup_v_scroll.set, xscrollcommand=sup_h_scroll.set)
            
            self.suppliers_tree.grid(row=0, column=0, sticky='nsew')
            sup_v_scroll.grid(row=0, column=1, sticky='ns')
            sup_h_scroll.grid(row=1, column=0, sticky='ew')
            
            list_frame.grid_rowconfigure(0, weight=1)
            list_frame.grid_columnconfigure(0, weight=1)
            
            # Bind selection
            self.suppliers_tree.bind('<<TreeviewSelect>>', self._on_supplier_select)
            
            self._refresh_suppliers()

    def _create_settings_tab(self):
        """Create settings and configuration tab"""
        self.settings_frame = ttk.Frame(self.nb, style='Green.TFrame')
        self.nb.add(self.settings_frame, text="⚙️ Settings")
        
        main_container = ttk.Frame(self.settings_frame, style='Green.TFrame')
        main_container.pack(fill='both', expand=True, padx=15, pady=15)
        
        # Application settings
        app_settings = ttk.LabelFrame(main_container, text=" Application Settings ", padding=15)
        app_settings.pack(fill='x', pady=(0, 15))
        
        # Theme setting
        theme_frame = ttk.Frame(app_settings)
        theme_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(theme_frame, text="Theme:").pack(side='left', padx=(0, 10))
        self.theme_var = tk.StringVar(value=self.theme)
        theme_light = ttk.Radiobutton(theme_frame, text="Light", variable=self.theme_var, value="light", command=self._change_theme)
        theme_dark = ttk.Radiobutton(theme_frame, text="Dark", variable=self.theme_var, value="dark", command=self._change_theme)
        theme_light.pack(side='left', padx=(0, 10))
        theme_dark.pack(side='left')
        
        # Low stock threshold
        threshold_frame = ttk.Frame(app_settings)
        threshold_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(threshold_frame, text="Low Stock Threshold:").pack(side='left', padx=(0, 10))
        self.threshold_var = tk.StringVar(value=str(LOW_STOCK_THRESHOLD))
        threshold_entry = ttk.Entry(threshold_frame, textvariable=self.threshold_var, width=10)
        threshold_entry.pack(side='left', padx=(0, 10))
        ttk.Button(threshold_frame, text="Update", command=self._update_threshold).pack(side='left')
        
        # Data management
        data_settings = ttk.LabelFrame(main_container, text=" Data Management ", padding=15)
        data_settings.pack(fill='x', pady=(0, 15))
        
        data_buttons = [
            ("📥 Import CSV", self._import_csv),
            ("📤 Export CSV", self._export_csv),
            ("💾 Backup Database", self._backup_data),
            ("🔄 Reset Database", self._reset_database),
        ]
        
        for i, (text, command) in enumerate(data_buttons):
            ttk.Button(data_settings, text=text, command=command).grid(row=i//2, column=i%2, padx=10, pady=5, sticky='ew')
        
        data_settings.columnconfigure(0, weight=1)
        data_settings.columnconfigure(1, weight=1)
        
        # System info
        info_frame = ttk.LabelFrame(main_container, text=" System Information ", padding=15)
        info_frame.pack(fill='both', expand=True)
        
        info_text = tk.Text(info_frame, height=10, wrap=tk.WORD, font=('Courier New', 10))
        info_scroll = ttk.Scrollbar(info_frame, orient='vertical', command=info_text.yview)
        info_text.configure(yscrollcommand=info_scroll.set)
        
        info_text.pack(side='left', fill='both', expand=True)
        info_scroll.pack(side='right', fill='y')
        
        # Populate system info
        self._update_system_info(info_text)



    def _create_calculator_tab(self):
      """Create calculator tab"""
      self.calc_frame = ttk.Frame(self.nb, style='Green.TFrame')
      self.nb.add(self.calc_frame, text="🧮 Calculator")
      
      self.calc_display = tk.StringVar()
      
      calc_container = ttk.Frame(self.calc_frame, style='Green.TFrame')
      calc_container.pack(expand=True, fill='both', padx=20, pady=20)
      
      # Display - made much larger
      display_entry = ttk.Entry(
            calc_container,
            textvariable=self.calc_display,
            font=("Helvetica", 28, "bold"),  # Increased from 18 to 28
            justify="right",
            style='Green.TEntry'
      )
      display_entry.grid(row=0, column=0, columnspan=4, sticky="nsew", padx=8, pady=8, ipady=15)
      
      # Button configuration - made bigger
      btn_cfg = {
            "font": ("Helvetica", 20, "bold"),  # Increased from 14 to 20
            "width": 8,  # Increased from 5 to 8
            "height": 3,  # Added height
            "takefocus": False,
            "bg": "#4a7c59", 
            "fg": "white", 
            "activebackground": "#5d8b6a"
      }
      
      buttons = [
            ("7", self._calc_append), ("8", self._calc_append), ("9", self._calc_append), ("/", self._calc_append),
            ("4", self._calc_append), ("5", self._calc_append), ("6", self._calc_append), ("*", self._calc_append),
            ("1", self._calc_append), ("2", self._calc_append), ("3", self._calc_append), ("-", self._calc_append),
            ("0", self._calc_append), (".", self._calc_append), ("=", self._calc_equal), ("+", self._calc_append),
      ]
      
      r, c = 1, 0
      for txt, cmd in buttons:
            btn = tk.Button(calc_container, text=txt, command=lambda t=txt, f=cmd: f(t), **btn_cfg)
            if txt == "=":
                  btn.config(bg="#2d5016", activebackground="#1a3009")
            btn.grid(row=r, column=c, padx=4, pady=4, sticky="nsew")  # Increased padding
            c += 1
            if c > 3:
                  c = 0
                  r += 1
      
      # Special buttons - made bigger
      tk.Button(calc_container, text="Clear", command=self._calc_clear,  # Changed "C" to "Clear" for better visibility
                  bg="#c62828", fg="white", font=("Helvetica", 18, "bold"),  # Increased font
                  height=2,  # Added height
                  activebackground="#d32f2f").grid(row=5, column=0, columnspan=2, padx=4, pady=4, sticky="nsew")
      
      tk.Button(calc_container, text="⌫", command=self._calc_backspace,  # Changed "←" to "⌫" for better visibility
                  bg="#f57c00", fg="white", font=("Helvetica", 18, "bold"),  # Increased font
                  height=2,  # Added height
                  activebackground="#ff9800").grid(row=5, column=2, columnspan=2, padx=4, pady=4, sticky="nsew")
      
      # Configure grid weights for better scaling
      for i in range(6):
            calc_container.rowconfigure(i, weight=1, minsize=60)  # Added minimum size
      for i in range(4):
            calc_container.columnconfigure(i, weight=1, minsize=80)  # Added minimum size

    # Event handlers and utility methods
    def _on_search(self, event=None):
        """Handle search and filter"""
        query = self.search_var.get()
        category = self.category_filter.get() if self.category_filter.get() != "All" else None
        location = self.location_filter.get() if self.location_filter.get() != "All" else None
        
        results = self.inventory.search_items(query, category, location)
        self._populate_tree(results)

    def _clear_search(self):
        """Clear search filters"""
        self.search_var.set("")
        self.category_filter.set("")
        self.location_filter.set("")
        self._refresh_inventory()

    def _on_item_select(self, event):
        """Handle item selection in tree"""
        selection = self.tree.selection()
        if selection:
            item = self.tree.item(selection[0])
            values = item['values']
            
            # Populate form with selected item data
            self.sku_entry.delete(0, tk.END)
            self.sku_entry.insert(0, values[0])
            self.name_entry.delete(0, tk.END)
            self.name_entry.insert(0, values[1])
            self.category_entry.set(values[2])
            self.qty_entry.delete(0, tk.END)
            self.qty_entry.insert(0, values[3])
            self.price_entry.delete(0, tk.END)
            self.price_entry.insert(0, values[4])
            if len(values) > 6:
                self.supplier_entry.set(values[6] if values[6] else "")
                self.location_entry.set(values[7] if values[7] else "Main Warehouse")
                if len(values) > 8:
                    self.reorder_entry.delete(0, tk.END)
                    self.reorder_entry.insert(0, values[8])

    def _add_item(self):
        """Add new item"""
        try:
            sku = self.sku_entry.get().strip().upper()
            name = self.name_entry.get().strip()
            category = self.category_entry.get().strip() or "General"
            qty = int(self.qty_entry.get().strip()) if self.qty_entry.get().strip() else 0
            price = float(self.price_entry.get().strip()) if self.price_entry.get().strip() else 0.0
            supplier = self.supplier_entry.get().strip()
            location = self.location_entry.get().strip() or "Main Warehouse"
            
            if not sku or not name:
                messagebox.showwarning("Invalid Input", "SKU and Name are required!")
                return
            
            self.inventory.purchase_item(sku, name, category, qty, price, supplier, location)
            self._clear_form()
            self._refresh_inventory()
            self._update_form_dropdowns()
            
            messagebox.showinfo("Success", f"Added {qty} units of {name} (SKU: {sku})")
            
        except ValueError as e:
            messagebox.showerror("Invalid Input", "Please enter valid numbers for quantity and price!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to add item: {str(e)}")

    def _update_item(self):
        """Update existing item"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select an item to update!")
            return
        
        try:
            sku = self.sku_entry.get().strip().upper()
            if sku not in self.inventory._items:
                messagebox.showwarning("Item Not Found", "Item does not exist!")
                return
            
            item = self.inventory._items[sku]
            item.name = self.name_entry.get().strip()
            item.category = self.category_entry.get().strip() or "General"
            item.supplier = self.supplier_entry.get().strip()
            item.location = self.location_entry.get().strip() or "Main Warehouse"
            
            if self.reorder_entry.get().strip():
                item.reorder_point = int(self.reorder_entry.get().strip())
            
            item.last_updated = datetime.now().isoformat()
            
            self._refresh_inventory()
            messagebox.showinfo("Success", f"Updated item {sku}")
            
        except ValueError as e:
            messagebox.showerror("Invalid Input", "Please enter valid values!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update item: {str(e)}")

    def _delete_item(self):
        """Delete selected item"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select an item to delete!")
            return
        
        item = self.tree.item(selection[0])
        sku = item['values'][0]
        name = item['values'][1]
        
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete {name} (SKU: {sku})?"):
            try:
                self.inventory.delete_item(sku)
                self._clear_form()
                self._refresh_inventory()
                messagebox.showinfo("Success", f"Deleted item {sku}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete item: {str(e)}")

    def _clear_form(self):
        """Clear all form fields"""
        for entry in [self.sku_entry, self.name_entry, self.qty_entry, self.price_entry, self.reorder_entry]:
            entry.delete(0, tk.END)
        self.category_entry.set("")
        self.supplier_entry.set("")
        self.location_entry.set("Main Warehouse")

    def _update_form_dropdowns(self):
        """Update dropdown values"""
        categories = sorted(list(self.inventory.categories))
        self.category_entry['values'] = categories
        self.category_filter['values'] = ["All"] + categories
        
        locations = sorted(list(self.inventory.locations))
        self.location_entry['values'] = locations
        self.location_filter['values'] = ["All"] + locations
        
        suppliers = [s.name for s in self.inventory.suppliers.values()]
        self.supplier_entry['values'] = suppliers

    def _populate_tree(self, items=None):
        """Populate treeview with items"""
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        if items is None:
            items = self.inventory.list_inventory()
        
        for sku, item in sorted(items.items()):
            tags = ()
            if item.quantity <= item.reorder_point:
                tags = ('low_stock',)
            
            self.tree.insert('', 'end', values=(
                item.sku, item.name, item.category, item.quantity,
                f"{item.unit_price:.2f}", f"{item.total_cost:.2f}",
                item.supplier, item.location, item.reorder_point, item.barcode
            ), tags=tags)
        
        # Configure tags
        self.tree.tag_configure('low_stock', background='#ffebee', foreground='#c62828')

    def _refresh_inventory(self):
        """Refresh inventory display"""
        self._populate_tree()
        
        # Update summary
        items = self.inventory.list_inventory()
        total_items = len(items)
        total_value = self.inventory.total_inventory_value()
        low_stock = len(self.inventory.low_stock_items())
        
        self.summary_label.config(
            text=f"Total Items: {total_items} | Total Value: ₦{total_value:,.2f} | Low Stock: {low_stock}"
        )

    def _save_inventory(self):
        """Save inventory to database"""
        try:
            self.inventory.save_to_database()
            messagebox.showinfo("Success", "Inventory saved successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save inventory: {str(e)}")

    

    def _sort_treeview(self, col):
        """Sort treeview by column"""
        items = [(self.tree.set(child, col), child) for child in self.tree.get_children('')]
        
        # Try to sort numerically if possible
        try:
            items.sort(key=lambda x: float(x[0].replace(',', '')))
        except:
            items.sort()
        
        for index, (val, child) in enumerate(items):
            self.tree.move(child, '', index)

    # Sales tab methods
    def _refresh_sales_form(self):
        """Refresh sales form dropdowns"""
        skus = sorted(list(self.inventory._items.keys()))
        self.sale_sku['values'] = skus

    def _on_sale_sku_select(self, event=None):
        """Handle SKU selection in sales form"""
        sku = self.sale_sku.get()
        if sku in self.inventory._items:
            item = self.inventory._items[sku]
            self.sale_price.delete(0, tk.END)
            self.sale_price.insert(0, str(item.unit_price))
            
            self.stock_info.config(
                text=f"Available: {item.quantity} units | Current Price: ₦{item.unit_price:.2f}"
            )

    def _record_sale(self):
        """Record a sale transaction"""
        try:
            sku = self.sale_sku.get().strip().upper()
            qty = int(self.sale_qty.get().strip())
            price = float(self.sale_price.get().strip())
            customer = self.sale_customer.get().strip()
            
            if not sku:
                messagebox.showwarning("Invalid Input", "Please select a SKU!")
                return
            
            if sku not in self.inventory._items:
                messagebox.showwarning("Item Not Found", "Selected item not found!")
                return
            
            if qty <= 0:
                messagebox.showwarning("Invalid Input", "Quantity must be greater than 0!")
                return
            
            profit = self.inventory.sell_item_with_commission(sku, qty, price, customer)
            
            # Clear form
            self.sale_qty.delete(0, tk.END)
            self.sale_customer.delete(0, tk.END)
            self.stock_info.config(text="")
            
            self._refresh_sales_history()
            self._refresh_inventory()
            
            messagebox.showinfo("Success", 
                f"Sale recorded!\nProfit: ₦{profit:.2f}\nRemaining stock: {self.inventory._items[sku].quantity}")
            
        except ValueError as e:
            if "Not enough stock" in str(e):
                messagebox.showwarning("Insufficient Stock", str(e))
            else:
                messagebox.showerror("Invalid Input", "Please enter valid numbers for quantity and price!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to record sale: {str(e)}")

    def _refresh_sales_history(self, event=None):
        """Refresh sales history display"""
        # Clear existing items
        for item in self.sales_tree.get_children():
            self.sales_tree.delete(item)
        
        # Get period
        period_text = self.sales_period.get()
        days = {'7 days': 7, '30 days': 30, '90 days': 90, '1 year': 365}[period_text]
        
        sales = self.inventory.get_sales_data_with_commission(days)
        
        total_sales = 0
        total_profit = 0
        
        for sale in sales:
            date_str = datetime.fromisoformat(sale.date).strftime('%Y-%m-%d %H:%M')
            total_sale = sale.sale_price * sale.quantity
            
            self.sales_tree.insert('', 'end', values=(
                date_str, sale.sku, sale.quantity, f"₦{sale.sale_price:.2f}",
                f"₦{total_sale:.2f}", f"₦{sale.profit:.2f}", sale.customer
            ))
            
            total_sales += total_sale
            total_profit += sale.profit
        
        # Update summary
        profit_margin = (total_profit / total_sales * 100) if total_sales > 0 else 0
        self.sales_summary.config(
            text=f"Period: {period_text} | Total Sales: ₦{total_sales:.2f} | "
                 f"Total Profit: ₦{total_profit:.2f} | Margin: {profit_margin:.1f}%"
        )

    # Analytics tab methods
    def _refresh_analytics(self):
        """Refresh analytics data"""
        analytics = self.inventory.get_analytics()
        
        self.metrics_vars['total_items'].set(str(analytics['total_items']))
        self.metrics_vars['total_value'].set(f"₦{analytics['total_value']:,.2f}")
        self.metrics_vars['low_stock'].set(str(analytics['low_stock_count']))
        self.metrics_vars['sales_30d'].set(f"₦{analytics['total_sales_30d']:,.2f}")
        self.metrics_vars['profit_30d'].set(f"₦{analytics['total_profit_30d']:,.2f}")
        self.metrics_vars['margin'].set(f"{analytics['avg_profit_margin']:.1f}%")

    def _show_sales_chart(self):
        """Show sales trend chart"""
        self._clear_chart_frame()
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        # Get sales data for last 30 days
        sales = self.inventory.get_sales_data_with_commission(30)
        
        # Group by date
        daily_sales = {}
        for sale in sales:
            date = datetime.fromisoformat(sale.date).date()
            if date not in daily_sales:
                daily_sales[date] = 0
            daily_sales[date] += sale.sale_price * sale.quantity
        
        if daily_sales:
            dates = sorted(daily_sales.keys())
            values = [daily_sales[date] for date in dates]
            
            ax.plot(dates, values, marker='o', linewidth=2, markersize=6, color='#4a7c59')
            ax.set_title('Daily Sales Trend (Last 30 Days)', fontsize=14, fontweight='bold')
            ax.set_xlabel('Date')
            ax.set_ylabel('Sales (₦)')
            ax.grid(True, alpha=0.3)
            
            # Format y-axis as currency
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'₦{x:.0f}'))
        else:
            ax.text(0.5, 0.5, 'No sales data available', ha='center', va='center', transform=ax.transAxes)
        
        plt.tight_layout()
        
        canvas = FigureCanvasTkAgg(fig, self.chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill='both', expand=True)

    def _show_category_chart(self):
        """Show category distribution chart"""
        self._clear_chart_frame()
        
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 6))
        
        # Category by quantity
        categories = {}
        for item in self.inventory._items.values():
            if item.category not in categories:
                categories[item.category] = {'qty': 0, 'value': 0}
            categories[item.category]['qty'] += item.quantity
            categories[item.category]['value'] += item.total_cost
        
        if categories:
            labels = list(categories.keys())
            qty_values = [categories[cat]['qty'] for cat in labels]
            value_values = [categories[cat]['value'] for cat in labels]
            
            colors = plt.cm.Set3(range(len(labels)))
            
            ax1.pie(qty_values, labels=labels, autopct='%1.1f%%', colors=colors)
            ax1.set_title('Inventory by Quantity')
            
            ax2.pie(value_values, labels=labels, autopct='%1.1f%%', colors=colors)
            ax2.set_title('Inventory by Value')
        else:
            for ax in [ax1, ax2]:
                ax.text(0.5, 0.5, 'No data available', ha='center', va='center', transform=ax.transAxes)
        
        plt.tight_layout()
        
        canvas = FigureCanvasTkAgg(fig, self.chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill='both', expand=True)

    def _show_top_items_chart(self):
        """Show top items by value chart"""
        self._clear_chart_frame()
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        # Get top 10 items by total cost
        items = sorted(self.inventory._items.values(), key=lambda x: x.total_cost, reverse=True)[:10]
        
        if items:
            names = [f"{item.sku}\n{item.name[:15]}" for item in items]
            values = [item.total_cost for item in items]
            
            bars = ax.bar(names, values, color='#4a7c59', alpha=0.8)
            ax.set_title('Top 10 Items by Total Value', fontsize=14, fontweight='bold')
            ax.set_ylabel('Total Value (₦)')
            
            # Add value labels on bars
            for bar, value in zip(bars, values):
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'₦{value:.0f}', ha='center', va='bottom')
            
            plt.xticks(rotation=45, ha='right')
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'₦{x:.0f}'))
        else:
            ax.text(0.5, 0.5, 'No items available', ha='center', va='center', transform=ax.transAxes)
        
        plt.tight_layout()
        
        canvas = FigureCanvasTkAgg(fig, self.chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill='both', expand=True)

    def _show_stock_chart(self):
        """Show stock levels chart"""
        self._clear_chart_frame()
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        items = list(self.inventory._items.values())
        
        if items:
            # Categorize by stock level
            good_stock = [item for item in items if item.quantity > item.reorder_point * 2]
            medium_stock = [item for item in items if item.reorder_point < item.quantity <= item.reorder_point * 2]
            low_stock = [item for item in items if item.quantity <= item.reorder_point]
            
            categories = ['Good Stock', 'Medium Stock', 'Low Stock']
            counts = [len(good_stock), len(medium_stock), len(low_stock)]
            colors = ['#4caf50', '#ff9800', '#f44336']
            
            bars = ax.bar(categories, counts, color=colors, alpha=0.8)
            ax.set_title('Stock Level Distribution', fontsize=14, fontweight='bold')
            ax.set_ylabel('Number of Items')
            
            # Add count labels on bars
            for bar, count in zip(bars, counts):
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       str(count), ha='center', va='bottom', fontweight='bold')
        else:
            ax.text(0.5, 0.5, 'No items available', ha='center', va='center', transform=ax.transAxes)
        
        plt.tight_layout()
        
        canvas = FigureCanvasTkAgg(fig, self.chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill='both', expand=True)

    def _clear_chart_frame(self):
        """Clear the chart display area"""
        for widget in self.chart_frame.winfo_children():
            widget.destroy()

    # Suppliers tab methods
    def _add_supplier(self):
        """Add new supplier"""
        try:
            name = self.supplier_name.get().strip()
            contact = self.supplier_contact.get().strip()
            email = self.supplier_email.get().strip()
            phone = self.supplier_phone.get().strip()
            address = self.supplier_address.get().strip()
            
            if not name:
                messagebox.showwarning("Invalid Input", "Supplier name is required!")
                return
            
            conn = sqlite3.connect(self.inventory.db.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO suppliers (name, contact_person, email, phone, address)
                VALUES (?, ?, ?, ?, ?)
            ''', (name, contact, email, phone, address))
            conn.commit()
            
            supplier_id = cursor.lastrowid
            self.inventory.suppliers[supplier_id] = Supplier(supplier_id, name, contact, email, phone, address)
            
            conn.close()
            
            self._clear_supplier_form()
            self._refresh_suppliers()
            self._update_form_dropdowns()
            
            messagebox.showinfo("Success", f"Added supplier: {name}")
            
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Supplier name already exists!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to add supplier: {str(e)}")

    def _update_supplier(self):
        """Update selected supplier"""
        selection = self.suppliers_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a supplier to update!")
            return
        
        try:
            item = self.suppliers_tree.item(selection[0])
            supplier_id = int(item['values'][0])
            
            name = self.supplier_name.get().strip()
            contact = self.supplier_contact.get().strip()
            email = self.supplier_email.get().strip()
            phone = self.supplier_phone.get().strip()
            address = self.supplier_address.get().strip()
            
            if not name:
                messagebox.showwarning("Invalid Input", "Supplier name is required!")
                return
            
            conn = sqlite3.connect(self.inventory.db.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE suppliers SET name=?, contact_person=?, email=?, phone=?, address=?
                WHERE id=?
            ''', (name, contact, email, phone, address, supplier_id))
            conn.commit()
            conn.close()
            
            # Update in memory
            self.inventory.suppliers[supplier_id] = Supplier(supplier_id, name, contact, email, phone, address)
            
            self._refresh_suppliers()
            self._update_form_dropdowns()
            
            messagebox.showinfo("Success", f"Updated supplier: {name}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update supplier: {str(e)}")

    def _delete_supplier(self):
        """Delete selected supplier"""
        selection = self.suppliers_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a supplier to delete!")
            return
        
        item = self.suppliers_tree.item(selection[0])
        supplier_id = int(item['values'][0])
        name = item['values'][1]
        
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete supplier '{name}'?"):
            try:
                conn = sqlite3.connect(self.inventory.db.db_path)
                cursor = conn.cursor()
                cursor.execute('DELETE FROM suppliers WHERE id=?', (supplier_id,))
                conn.commit()
                conn.close()
                
                if supplier_id in self.inventory.suppliers:
                    del self.inventory.suppliers[supplier_id]
                
                self._clear_supplier_form()
                self._refresh_suppliers()
                self._update_form_dropdowns()
                
                messagebox.showinfo("Success", f"Deleted supplier: {name}")
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete supplier: {str(e)}")

    def _clear_supplier_form(self):
        """Clear supplier form fields"""
        for entry in [self.supplier_name, self.supplier_contact, self.supplier_email, 
                     self.supplier_phone, self.supplier_address]:
            entry.delete(0, tk.END)

    def _on_supplier_select(self, event):
        """Handle supplier selection"""
        selection = self.suppliers_tree.selection()
        if selection:
            item = self.suppliers_tree.item(selection[0])
            values = item['values']
            
            self.supplier_name.delete(0, tk.END)
            self.supplier_name.insert(0, values[1])
            self.supplier_contact.delete(0, tk.END)
            self.supplier_contact.insert(0, values[2])
            self.supplier_email.delete(0, tk.END)
            self.supplier_email.insert(0, values[3])
            self.supplier_phone.delete(0, tk.END)
            self.supplier_phone.insert(0, values[4])
            self.supplier_address.delete(0, tk.END)
            self.supplier_address.insert(0, values[5])

    def _refresh_suppliers(self):
        """Refresh suppliers display"""
        for item in self.suppliers_tree.get_children():
            self.suppliers_tree.delete(item)
        
        for supplier in self.inventory.suppliers.values():
            self.suppliers_tree.insert('', 'end', values=(
                supplier.id, supplier.name, supplier.contact_person,
                supplier.email, supplier.phone, supplier.address
            ))

    # Settings and utility methods
    def _toggle_theme(self):
        """Toggle between light and dark theme"""
        self.theme = "dark" if self.theme == "light" else "light"
        self._configure_styles()
        messagebox.showinfo("Theme Changed", f"Theme changed to {self.theme}. Restart for full effect.")

    def _change_theme(self):
        """Change theme based on selection"""
        self.theme = self.theme_var.get()
        self._configure_styles()

    def _update_threshold(self):
        """Update low stock threshold"""
        try:
            global LOW_STOCK_THRESHOLD
            new_threshold = int(self.threshold_var.get())
            if new_threshold < 0:
                raise ValueError("Threshold must be non-negative")
            
            LOW_STOCK_THRESHOLD = new_threshold
            self._refresh_inventory()
            messagebox.showinfo("Success", f"Low stock threshold updated to {new_threshold}")
            
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter a valid number for threshold!")

    def _import_csv(self):
        """Import inventory from CSV file"""
        filepath = filedialog.askopenfilename(
            title="Import CSV File",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        
        if filepath:
            try:
                imported = self.inventory.import_from_csv(filepath)
                self._refresh_inventory()
                self._update_form_dropdowns()
                messagebox.showinfo("Import Complete", f"Successfully imported {imported} items!")
            except Exception as e:
                messagebox.showerror("Import Error", f"Failed to import CSV: {str(e)}")

    def _export_csv(self):
        """Export inventory to CSV file"""
        filepath = filedialog.asksaveasfilename(
            title="Export CSV File",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        
        if filepath:
            try:
                self.inventory.export_to_csv(filepath)
                messagebox.showinfo("Export Complete", f"Successfully exported to {filepath}!")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to export CSV: {str(e)}")

    def _backup_data(self):
        """Create data backup"""
        try:
            backup_file = self.inventory.backup_data()
            messagebox.showinfo("Backup Complete", f"Backup created: {backup_file}")
        except Exception as e:
            messagebox.showerror("Backup Error", f"Failed to create backup: {str(e)}")

    def _reset_database(self):
        """Reset database (admin only)"""
        if self.current_user['role'] != 'admin':
            messagebox.showwarning("Access Denied", "Only administrators can reset the database!")
            return
        
        if messagebox.askyesnocancel("Reset Database", 
                                    "This will DELETE ALL DATA!\n\nAre you absolutely sure?"):
            try:
                # Create backup first
                backup_file = self.inventory.backup_data()
                
                # Clear all data
                conn = sqlite3.connect(self.inventory.db.db_path)
                cursor = conn.cursor()
                
                tables = ['items', 'sales', 'suppliers', 'audit_log', 'price_history']
                for table in tables:
                    cursor.execute(f'DELETE FROM {table}')
                
                conn.commit()
                conn.close()
                
                # Reload
                self.inventory = EnhancedInventory()
                self.inventory.set_current_user(self.current_user['username'])
                self._refresh_all()
                
                messagebox.showinfo("Database Reset", 
                                   f"Database reset complete!\nBackup saved: {backup_file}")
                
            except Exception as e:
                messagebox.showerror("Reset Error", f"Failed to reset database: {str(e)}")

    def _update_system_info(self, text_widget):
        """Update system information display"""
        info = f"""Application: Advanced Inventory Management System
Version: 2.0.0
Database: SQLite ({DB_FILE})
Current User: {self.current_user['username']} ({self.current_user['role']})
Theme: {self.theme.title()}
Low Stock Threshold: {LOW_STOCK_THRESHOLD}

Database Statistics:
- Total Items: {len(self.inventory._items)}
- Total Categories: {len(self.inventory.categories)}
- Total Suppliers: {len(self.inventory.suppliers)}
- Total Locations: {len(self.inventory.locations)}

Recent Activity:
- Last Login: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- Database Size: {os.path.getsize(self.inventory.db.db_path) / 1024:.1f} KB

Features Available:
✓ Inventory Management
✓ Sales Tracking
✓ Analytics & Reports
✓ Supplier Management
✓ User Management (Admin)
✓ Data Import/Export
✓ Automatic Backups
✓ Audit Logging
✓ Price History
✓ Reorder Suggestions
✓ Low Stock Alerts
✓ Barcode Generation
✓ Multi-location Support
"""
        
        text_widget.insert('1.0', info)
        text_widget.config(state='disabled')

    def _generate_comprehensive_report(self):
        """Generate comprehensive inventory report"""
        report_window = tk.Toplevel(self.master)
        report_window.title("Comprehensive Inventory Report")
        report_window.geometry("800x600")
        report_window.configure(bg='#f0f8f0')
        
        # Report text
        text_widget = tk.Text(report_window, wrap=tk.WORD, font=('Courier New', 10),
                             bg='white', fg='#2d5016', padx=15, pady=15)
        
        scrollbar = ttk.Scrollbar(report_window, orient='vertical', command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        
        text_widget.pack(side='left', fill='both', expand=True, padx=(10,0), pady=10)
        scrollbar.pack(side='right', fill='y', padx=(0,10), pady=10)
        
        # Generate report content
        report = self._create_comprehensive_report()
        text_widget.insert('1.0', report)
        text_widget.config(state='disabled')
        
        # Export button
        export_btn = ttk.Button(report_window, text="💾 Export Report", 
                               command=lambda: self._export_report(report))
        export_btn.pack(pady=10)

    def _create_comprehensive_report(self):
        """Create comprehensive report content"""
        analytics = self.inventory.get_analytics()
        sales_30d = self.inventory.get_sales_data_with_commission(30)
        low_stock = self.inventory.low_stock_items()
        reorder_suggestions = self.inventory.get_reorder_suggestions()
        
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("COMPREHENSIVE INVENTORY REPORT")
        report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append(f"Generated by: {self.current_user['username']}")
        report_lines.append("=" * 80)
        
        # Executive Summary
        report_lines.append("\n📊 EXECUTIVE SUMMARY")
        report_lines.append("-" * 40)
        report_lines.append(f"Total Items in Inventory: {analytics['total_items']:,}")
        report_lines.append(f"Total Inventory Value: ₦{analytics['total_value']:,.2f}")
        report_lines.append(f"Items Requiring Attention: {analytics['low_stock_count']}")
        report_lines.append(f"30-Day Sales Revenue: ₦{analytics['total_sales_30d']:,.2f}")
        report_lines.append(f"30-Day Profit: ₦{analytics['total_profit_30d']:,.2f}")
        report_lines.append(f"Average Profit Margin: {analytics['avg_profit_margin']:.1f}%")
        
        # Inventory Details
        report_lines.append("\n📦 INVENTORY DETAILS")
        report_lines.append("-" * 40)
        header = f"{'SKU':<12} {'Name':<30} {'Category':<15} {'Qty':>8} {'Value':>12} {'Location':<15}"
        report_lines.append(header)
        report_lines.append("-" * len(header))
        
        for item in sorted(self.inventory._items.values(), key=lambda x: x.total_cost, reverse=True):
            report_lines.append(
                f"{item.sku:<12} {item.name[:30]:<30} {item.category:<15} "
                f"{item.quantity:>8} ₦{item.total_cost:>11.2f} {item.location:<15}"
            )
        
        # Low Stock Alert
        if low_stock:
            report_lines.append(f"\n⚠️  LOW STOCK ALERT ({len(low_stock)} items)")
            report_lines.append("-" * 40)
            for sku, item in low_stock.items():
                report_lines.append(f"• {sku}: {item.name} (Current: {item.quantity}, Reorder at: {item.reorder_point})")
        
        # Reorder Suggestions
        if reorder_suggestions:
            report_lines.append(f"\n🔄 REORDER SUGGESTIONS ({len(reorder_suggestions)} items)")
            report_lines.append("-" * 40)
            for sku, item in reorder_suggestions.items():
                suggested_qty = max(item.reorder_point * 2, 10)  # Suggest 2x reorder point or 10, whichever is higher
                report_lines.append(f"• {sku}: {item.name} - Suggested order: {suggested_qty} units")
        
        # Category Analysis
        categories = {}
        for item in self.inventory._items.values():
            if item.category not in categories:
                categories[item.category] = {'items': 0, 'value': 0, 'qty': 0}
            categories[item.category]['items'] += 1
            categories[item.category]['value'] += item.total_cost
            categories[item.category]['qty'] += item.quantity
        
        if categories:
            report_lines.append("\n📋 CATEGORY ANALYSIS")
            report_lines.append("-" * 40)
            cat_header = f"{'Category':<20} {'Items':>8} {'Total Qty':>12} {'Total Value':>15}"
            report_lines.append(cat_header)
            report_lines.append("-" * len(cat_header))
            
            for category, data in sorted(categories.items(), key=lambda x: x[1]['value'], reverse=True):
                report_lines.append(
                    f"{category:<20} {data['items']:>8} {data['qty']:>12} ₦{data['value']:>14.2f}"
                )
        
        # Recent Sales Performance
        if sales_30d:
            report_lines.append("\n💰 RECENT SALES PERFORMANCE (30 Days)")
            report_lines.append("-" * 40)
            
            # Sales by item
            sales_by_item = {}
            for sale in sales_30d:
                if sale.sku not in sales_by_item:
                    sales_by_item[sale.sku] = {'qty': 0, 'revenue': 0, 'profit': 0}
                sales_by_item[sale.sku]['qty'] += sale.quantity
                sales_by_item[sale.sku]['revenue'] += sale.sale_price * sale.quantity
                sales_by_item[sale.sku]['profit'] += sale.profit
            
            sales_header = f"{'SKU':<12} {'Qty Sold':>10} {'Revenue':>12} {'Profit':>12}"
            report_lines.append(sales_header)
            report_lines.append("-" * len(sales_header))
            
            for sku, data in sorted(sales_by_item.items(), key=lambda x: x[1]['revenue'], reverse=True)[:10]:
                report_lines.append(
                    f"{sku:<12} {data['qty']:>10} ₦{data['revenue']:>11.2f} ₦{data['profit']:>11.2f}"
                )
        
        # Supplier Analysis
        if self.inventory.suppliers:
            supplier_items = {}
            for item in self.inventory._items.values():
                if item.supplier:
                    if item.supplier not in supplier_items:
                        supplier_items[item.supplier] = {'items': 0, 'value': 0}
                    supplier_items[item.supplier]['items'] += 1
                    supplier_items[item.supplier]['value'] += item.total_cost
            
            if supplier_items:
                report_lines.append("\n🏢 SUPPLIER ANALYSIS")
                report_lines.append("-" * 40)
                sup_header = f"{'Supplier':<25} {'Items':>8} {'Total Value':>15}"
                report_lines.append(sup_header)
                report_lines.append("-" * len(sup_header))
                
                for supplier, data in sorted(supplier_items.items(), key=lambda x: x[1]['value'], reverse=True):
                    report_lines.append(
                        f"{supplier:<25} {data['items']:>8} ₦{data['value']:>14.2f}"
                    )
        
        # Location Analysis
        location_items = {}
        for item in self.inventory._items.values():
            if item.location not in location_items:
                location_items[item.location] = {'items': 0, 'value': 0, 'qty': 0}
            location_items[item.location]['items'] += 1
            location_items[item.location]['value'] += item.total_cost
            location_items[item.location]['qty'] += item.quantity
        
        if location_items:
            report_lines.append("\n📍 LOCATION ANALYSIS")
            report_lines.append("-" * 40)
            loc_header = f"{'Location':<20} {'Items':>8} {'Total Qty':>12} {'Total Value':>15}"
            report_lines.append(loc_header)
            report_lines.append("-" * len(loc_header))
            
            for location, data in sorted(location_items.items(), key=lambda x: x[1]['value'], reverse=True):
                report_lines.append(
                    f"{location:<20} {data['items']:>8} {data['qty']:>12} ₦{data['value']:>14.2f}"
                )
        
        report_lines.append("\n" + "=" * 80)
        report_lines.append("END OF REPORT")
        report_lines.append("=" * 80)
        
        return "\n".join(report_lines)

    def _export_report(self, report_content):
        """Export report to file"""
        filepath = filedialog.asksaveasfilename(
            title="Export Report",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        
        if filepath:
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(report_content)
                messagebox.showinfo("Export Complete", f"Report exported to {filepath}!")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to export report: {str(e)}")

    def _show_reorder_suggestions(self):
        """Show reorder suggestions window"""
        suggestions = self.inventory.get_reorder_suggestions()
        
        if not suggestions:
            messagebox.showinfo("Reorder Suggestions", "✅ All items have sufficient stock!")
            return
        
        # Create suggestions window
        suggest_window = tk.Toplevel(self.master)
        suggest_window.title("Reorder Suggestions")
        suggest_window.geometry("700x400")
        suggest_window.configure(bg='#f0f8f0')
        
        # Header
        header_label = ttk.Label(suggest_window, text=f"🔄 Items Requiring Reorder ({len(suggestions)})", 
                                font=('Helvetica', 14, 'bold'))
        header_label.pack(pady=10)
        
        # Suggestions tree
        columns = ('SKU', 'Name', 'Current Stock', 'Reorder Point', 'Suggested Order')
        suggest_tree = ttk.Treeview(suggest_window, columns=columns, show='headings', height=15)
        
        for col in columns:
            suggest_tree.heading(col, text=col)
            width = 100 if col in ['Current Stock', 'Reorder Point', 'Suggested Order'] else 150
            suggest_tree.column(col, width=width, anchor='center')
        
        # Populate suggestions
        for sku, item in suggestions.items():
            suggested_qty = max(item.reorder_point * 2, 10)
            suggest_tree.insert('', 'end', values=(
                item.sku, item.name, item.quantity, item.reorder_point, suggested_qty
            ))
        
        # Scrollbar
        suggest_scroll = ttk.Scrollbar(suggest_window, orient='vertical', command=suggest_tree.yview)
        suggest_tree.configure(yscrollcommand=suggest_scroll.set)
        
        suggest_tree.pack(side='left', fill='both', expand=True, padx=(10,0), pady=10)
        suggest_scroll.pack(side='right', fill='y', padx=(0,10), pady=10)

    def _show_price_history(self):
        """Show price history for selected item"""
        # Get item selection
        selection = self.tree.selection() if hasattr(self, 'tree') else None
        if not selection:
            # Show dialog to select item
            sku = tk.simpledialog.askstring("Price History", "Enter SKU to view price history:")
            if not sku or sku.upper() not in self.inventory._items:
                messagebox.showwarning("Invalid SKU", "Please enter a valid SKU!")
                return
            sku = sku.upper()
        else:
            item = self.tree.item(selection[0])
            sku = item['values'][0]
        
        # Get price history from database
        conn = sqlite3.connect(self.inventory.db.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT old_price, new_price, change_date FROM price_history 
            WHERE sku = ? ORDER BY change_date DESC
        ''', (sku,))
        history = cursor.fetchall()
        conn.close()
        
        if not history:
            messagebox.showinfo("Price History", f"No price history found for {sku}")
            return
        
        # Create price history window
        history_window = tk.Toplevel(self.master)
        history_window.title(f"Price History - {sku}")
        history_window.geometry("500x400")
        history_window.configure(bg='#f0f8f0')
        
        # Header
        item_name = self.inventory._items[sku].name if sku in self.inventory._items else "Unknown"
        header_label = ttk.Label(history_window, 
                                text=f"📈 Price History for {sku} - {item_name}", 
                                font=('Helvetica', 14, 'bold'))
        header_label.pack(pady=10)
        
        # History tree
        columns = ('Date', 'Old Price', 'New Price', 'Change')
        history_tree = ttk.Treeview(history_window, columns=columns, show='headings', height=15)
        
        for col in columns:
            history_tree.heading(col, text=col)
            history_tree.column(col, width=120, anchor='center')
        
        # Populate history
        for old_price, new_price, change_date in history:
            date_str = datetime.fromisoformat(change_date).strftime('%Y-%m-%d %H:%M')
            change = new_price - old_price
            change_str = f"+₦{change:.2f}" if change >= 0 else f"-₦{abs(change):.2f}"
            
            history_tree.insert('', 'end', values=(
                date_str, f"₦{old_price:.2f}", f"₦{new_price:.2f}", change_str
            ))
        
        history_tree.pack(fill='both', expand=True, padx=10, pady=(0,10))

    def _show_user_management(self):
        """Show user management window (admin only)"""
        if self.current_user['role'] != 'admin':
            messagebox.showwarning("Access Denied", "Only administrators can manage users!")
            return
        
        # Create user management window
        user_window = tk.Toplevel(self.master)
        user_window.title("User Management")
        user_window.geometry("600x500")
        user_window.configure(bg='#f0f8f0')
        
        # Header
        header_label = ttk.Label(user_window, text="👥 User Management", 
                                font=('Helvetica', 14, 'bold'))
        header_label.pack(pady=10)
        
        # Add user form
        form_frame = ttk.LabelFrame(user_window, text=" Add New User ", padding=15)
        form_frame.pack(fill='x', padx=10, pady=(0,10))
        
        form_grid = ttk.Frame(form_frame)
        form_grid.pack(fill='x')
        
        ttk.Label(form_grid, text="Username:").grid(row=0, column=0, sticky='w', padx=(0,5))
        new_username = ttk.Entry(form_grid, width=20)
        new_username.grid(row=0, column=1, padx=(0,10))
        
        ttk.Label(form_grid, text="Password:").grid(row=0, column=2, sticky='w', padx=(0,5))
        new_password = ttk.Entry(form_grid, width=20, show="*")
        new_password.grid(row=0, column=3, padx=(0,10))
        
        ttk.Label(form_grid, text="Role:").grid(row=1, column=0, sticky='w', padx=(0,5), pady=(10,0))
        new_role = ttk.Combobox(form_grid, width=17, values=['user', 'admin'], state='readonly')
        new_role.set('user')
        new_role.grid(row=1, column=1, pady=(10,0))
        
        def add_user():
            username = new_username.get().strip()
            password = new_password.get().strip()
            role = new_role.get()
            
            if not username or not password:
                messagebox.showwarning("Invalid Input", "Username and password are required!")
                return
            
            if self.user_manager.create_user(username, password, role):
                new_username.delete(0, tk.END)
                new_password.delete(0, tk.END)
                new_role.set('user')
                refresh_users()
                messagebox.showinfo("Success", f"User '{username}' created successfully!")
            else:
                messagebox.showerror("Error", "Username already exists!")
        
        ttk.Button(form_grid, text="➕ Add User", command=add_user).grid(row=1, column=2, columnspan=2, pady=(10,0))
        
        # Users list
        list_frame = ttk.LabelFrame(user_window, text=" Current Users ", padding=10)
        list_frame.pack(fill='both', expand=True, padx=10, pady=(0,10))
        
        user_columns = ('Username', 'Role', 'Created Date')
        users_tree = ttk.Treeview(list_frame, columns=user_columns, show='headings', height=12)
        
        for col in user_columns:
            users_tree.heading(col, text=col)
            width = 150 if col == 'Username' else 100 if col == 'Role' else 200
            users_tree.column(col, width=width, anchor='center')
        
        users_scroll = ttk.Scrollbar(list_frame, orient='vertical', command=users_tree.yview)
        users_tree.configure(yscrollcommand=users_scroll.set)
        
        users_tree.pack(side='left', fill='both', expand=True)
        users_scroll.pack(side='right', fill='y')
        
        def refresh_users():
            for item in users_tree.get_children():
                users_tree.delete(item)
            
            conn = sqlite3.connect(self.inventory.db.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT username, role, created_date FROM users ORDER BY username')
            
            for username, role, created_date in cursor.fetchall():
                date_str = datetime.fromisoformat(created_date).strftime('%Y-%m-%d %H:%M')
                users_tree.insert('', 'end', values=(username, role, date_str))
            
            conn.close()
        
        refresh_users()

    def _show_audit_log(self):
        """Show audit log window (admin only)"""
        if self.current_user['role'] != 'admin':
            messagebox.showwarning("Access Denied", "Only administrators can view audit logs!")
            return
        
        # Create audit log window
        audit_window = tk.Toplevel(self.master)
        audit_window.title("Audit Log")
        audit_window.geometry("900x600")
        audit_window.configure(bg='#f0f8f0')
        
        # Header
        header_label = ttk.Label(audit_window, text="📋 System Audit Log", 
                                font=('Helvetica', 14, 'bold'))
        header_label.pack(pady=10)
        
        # Filter frame
        filter_frame = ttk.Frame(audit_window)
        filter_frame.pack(fill='x', padx=10, pady=(0,10))
        
        ttk.Label(filter_frame, text="Show last:").pack(side='left', padx=(0,5))
        audit_period = ttk.Combobox(filter_frame, width=10, values=['100', '500', '1000', 'All'], state='readonly')
        audit_period.set('100')
        audit_period.pack(side='left', padx=(0,10))
        
        def refresh_audit():
            for item in audit_tree.get_children():
                audit_tree.delete(item)
            
            conn = sqlite3.connect(self.inventory.db.db_path)
            cursor = conn.cursor()
            
            limit_clause = ""
            if audit_period.get() != 'All':
                limit_clause = f"LIMIT {audit_period.get()}"
            
            cursor.execute(f'''
                SELECT username, action, details, timestamp FROM audit_log 
                ORDER BY timestamp DESC {limit_clause}
            ''')
            
            for username, action, details, timestamp in cursor.fetchall():
                date_str = datetime.fromisoformat(timestamp).strftime('%Y-%m-%d %H:%M:%S')
                audit_tree.insert('', 'end', values=(date_str, username, action, details))
            
            conn.close()
        
        ttk.Button(filter_frame, text="🔄 Refresh", command=refresh_audit).pack(side='left')
        
        # Audit tree
        audit_columns = ('Timestamp', 'User', 'Action', 'Details')
        audit_tree = ttk.Treeview(audit_window, columns=audit_columns, show='headings', height=20)
        
        widths = [150, 100, 100, 400]
        for col, width in zip(audit_columns, widths):
            audit_tree.heading(col, text=col)
            audit_tree.column(col, width=width, anchor='w')
        
        audit_scroll = ttk.Scrollbar(audit_window, orient='vertical', command=audit_tree.yview)
        audit_tree.configure(yscrollcommand=audit_scroll.set)
        
        audit_tree.pack(side='left', fill='both', expand=True, padx=(10,0), pady=(0,10))
        audit_scroll.pack(side='right', fill='y', padx=(0,10), pady=(0,10))
        
        refresh_audit()

    def _refresh_all(self):
        """Refresh all displays"""
        if hasattr(self, 'tree'):
            self._refresh_inventory()
        if hasattr(self, 'sales_tree'):
            self._refresh_sales_history()
        if hasattr(self, 'suppliers_tree'):
            self._refresh_suppliers()
        if hasattr(self, 'metrics_vars'):
            self._refresh_analytics()
        self._update_form_dropdowns()

    def _auto_save(self):
        """Auto-save inventory data"""
        try:
            self.inventory.save_to_database()
            self.status_var.set(f"Logged in as: {self.current_user['username']} ({self.current_user['role']}) - Auto-saved at {datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"Auto-save failed: {e}")
        
        # Schedule next auto-save
        self.master.after(300000, self._auto_save)  # 5 minutes

    def _logout(self):
        """Logout current user"""
        if messagebox.askyesno("Logout", "Are you sure you want to logout?"):
            self.master.destroy()
            # Restart application
            root = tk.Tk()
            app = EnhancedInventoryApp(root)
            root.mainloop()

    # Calculator methods
    def _calc_append(self, char: str):
        cur = self.calc_display.get()
        self.calc_display.set(cur + char)

    def _calc_clear(self, *_):
        self.calc_display.set("")

    def _calc_backspace(self, *_):
        cur = self.calc_display.get()
        self.calc_display.set(cur[:-1])

    def _calc_equal(self, *_):
        expr = self.calc_display.get()
        result = self._safe_eval(expr)
        if result is not None:
            self.calc_display.set(str(result))

    _SAFE_EXPR_RE = re.compile(r"^[\d\.\+\-\*/\(\) \t]+₦")

    def _safe_eval(self, expr: str):
        expr = expr.strip()
        if not expr:
            return None
        if not self._SAFE_EXPR_RE.fullmatch(expr):
            messagebox.showerror("Invalid expression", "Only numbers and + - * / ( ) are allowed.")
            return None
        try:
            result = eval(expr, {"__builtins__": None}, {})
            if isinstance(result, (int, float)):
                return round(result, 6)
            raise ValueError
        except Exception:
            messagebox.showerror("Evaluation error", "Could not evaluate the expression.")
            return None

    def _on_close(self):
        """Handle application close"""
        result = messagebox.askyesnocancel("Quit", 
                                          "Save before exiting?\n\nYes → Save & quit\nNo → Quit without saving\nCancel → Stay")
        if result is True:  # Yes - save and quit
            try:
                self.inventory.save_to_database()
                self.master.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save: {e}")
        elif result is False:  # No - quit without saving
            self.master.destroy()
        # Cancel - do nothing (stay)


# --------------------------------------------------------------------- #
#   Main Application Entry Point
# --------------------------------------------------------------------- #
def main():
    """Main application entry point"""
    try:
        root = tk.Tk()
        app = EnhancedInventoryApp(root)
        root.mainloop()
    except Exception as e:
        print(f"Application error: {e}")
        messagebox.showerror("Application Error", f"Failed to start application: {e}")

if __name__ == "__main__":
    main()