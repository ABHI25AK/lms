# ASM Nextgen Technical Campus
## Department of Computer Science &bull; Academic Year 2025–2026
### Capstone Project: Automated Library Management System (LMS)

---

## 👥 Project Team & Academic Guidance
- **Abhishek Kamble** (Roll No. SCS101) &mdash; *Team Lead / Full-Stack Developer*
- **Kunal Ambhore** (Roll No. SCS104) &mdash; *Backend & Database Developer*
- **Arpit Sharma** (Roll No. SCS106) &mdash; *Frontend & UI/UX Developer*
- **Vishweshwar Gaikwad** (Roll No. SCS123) &mdash; *Quality Assurance & Systems*
- **Guided by:** **Prof. Apeksha Pande**, Department of Computer Science

---

## 🌟 Executive Summary & Unique Innovations

The **ASM LMS** is an enterprise-grade academic library circulation and cataloguing platform designed to replace manual registers with an automated, paperless, data-driven system.

### Key Innovations:
1. **Deposit-Linked Fine Settlement:**
   - Rather than accumulating uncollectible paper fines, a refundable security deposit (e.g. ₹500.00) is collected when a copy is issued.
   - When returned, overdue penalties (₹5/day) are calculated and offset directly against the held deposit:
     $$\text{Overdue Days} = \max(0, \text{Return Date} - \text{Due Date})$$
     $$\text{Fine} = \text{Overdue Days} \times \text{Daily Fine Rate}$$
     $$\text{Deposit Applied} = \min(\text{Deposit Held}, \text{Fine})$$
     $$\text{Refund Due} = \max(0, \text{Deposit Held} - \text{Fine})$$
     $$\text{Remaining Fine Due} = \max(0, \text{Fine} - \text{Deposit Held})$$
   - Financial accounting preserves clear segregation between *Refund Due* vs *Refund Paid*, and *Fine Assessed* vs *Fine Collected*.
2. **First-In, First-Out (FIFO) Reservation Queue:**
   - Fair online reservation queue for books currently checked out.
   - When a copy is returned, the system automatically reserves it for the student at Position #1 and sets an auditable pickup deadline (e.g. 48 hours).
   - If the student fails to collect within the window, the management command automatically expires the reservation and re-allocates the copy to the next student in line.
3. **Rigorous Title vs. Physical Copy Modeling:**
   - Distinguishes abstract bibliographic records (`Book`) from inventory barcode units (`BookCopy`). Real-time stock counts never drift.
4. **API-First Architecture:**
   - Powered by Django REST Framework (DRF) with full JSON endpoints for mobile or external institutional integration.
5. **Interactive Chart.js Dashboards:**
   - Live visual analytics on most-borrowed technical titles, category-wise distributions, inventory status, and circulation trends.

---

## 🛠️ Technology Stack

| Layer | Technology |
|---|---|
| **Backend Framework** | Python 3.14 & Django 6.1 (MVT Architecture) |
| **REST API** | Django REST Framework (DRF) 3.18 |
| **Relational Database** | MySQL Server (via PyMySQL / Cryptography) with automated fallback to SQLite3 |
| **Frontend** | HTML5, CSS3, JavaScript, Bootstrap 5.3, Bootstrap Icons |
| **Data Visualizations** | Chart.js 4.4 CDN |
| **Security & Auth** | Role-Based Access Control (RBAC), CSRF protection, PBKDF2 hashing |

---

## 📂 Project Structure

```text
asm_library_management/
├── core/
│   ├── settings.py           # Multi-DB configuration (MySQL + PyMySQL), DRF, security
│   ├── urls.py               # Root URL configuration and static routing
│   ├── wsgi.py
│   └── asgi.py
├── library/
│   ├── migrations/           # Database migration schemas
│   ├── management/commands/
│   │   ├── seed_library_data.py         # Seeds 32 CS titles, 117 copies, users, loans
│   │   └── process_library_reminders.py # Scheduled job for due alerts and queue expiration
│   ├── models.py             # Relational schemas: Book, Copy, Loan, Reservation, Ledger
│   ├── views.py              # Full MVT view controllers and workflows
│   ├── api_views.py          # DRF REST API endpoints
│   ├── serializers.py        # Model serializers for REST API
│   ├── forms.py              # Secure validation forms
│   ├── urls.py               # Application URL dispatcher
│   ├── admin.py              # Django Admin integration
│   ├── context_processors.py # Global branding & notification badges
│   └── tests.py              # Comprehensive test suite (10 test cases)
├── templates/
│   ├── base.html             # Institutional master layout
│   ├── public/               # Home, Catalogue, Book Detail, Login, Register, API Docs
│   ├── student/              # Student Dashboard, My Loans, Reservations, Fines, Profile
│   └── librarian/            # Admin Dashboard, Issue, Return, Copies, Ledger, Reports, Settings
├── static/
│   ├── css/custom.css        # Academic navy-teal-gold responsive design system
│   └── js/                   # Main frontend scripts
├── requirements.txt          # Python dependencies
├── .env.example              # Environment variables template
├── .env                      # Active environment configuration
└── README.md                 # Complete project documentation
```

---

## 🚀 Quick Setup & Installation Guide

### Step 1: Clone or Navigate to the Project Directory
```powershell
cd c:\Users\Abhis\OneDrive\Desktop\asm_library_management
```

### Step 2: Activate the Virtual Environment
```powershell
.\venv\Scripts\Activate.ps1
```

### Step 3: Install Required Dependencies
```powershell
pip install -r requirements.txt
```

---

## 🗄️ MySQL Database Setup Instructions

1. Start your local **MySQL Server** (via MySQL Workbench, XAMPP, or Windows Service).
2. Open your MySQL client and execute:
   ```sql
   CREATE DATABASE asm_library CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```
3. Update `.env` with your MySQL credentials:
   ```ini
   DB_ENGINE=mysql
   DB_NAME=asm_library
   DB_USER=root
   DB_PASSWORD=your_mysql_password
   DB_HOST=127.0.0.1
   DB_PORT=3306
   ```
> **Note on Resilient Execution:** If MySQL Server is not currently started or unreachable, the system automatically and cleanly falls back to `db.sqlite3` so that development, demonstrations, and test runs execute without crashes.

---

## ⚙️ Database Migrations & Repeatable Demo Seeding

### 1. Apply Migrations
```powershell
python manage.py migrate
```

### 2. Run the Repeatable Demo Seeding Command
```powershell
python manage.py seed_library_data
```
This populates:
- **32 Computer Science Technical Books** across 7 curriculum categories (CLRS, OS Concepts, Clean Code, Design Patterns, SRE, etc.)
- **117 Physical Copies** with individual accession numbers (`CS-2025-0101`, etc.)
- **Staff Accounts** (Chief Librarian, Faculty Advisor)
- **Student Accounts** for all presentation team members
- **Active Loans, Overdue Loans, and Settled Loans**
- **FIFO Reservations and Financial Transactions**

---

## 🔐 Development Login Credentials

| Role | Username | Password | Notes |
|---|---|---|---|
| **Chief Librarian (Admin)** | `admin` | `admin123` | Full administrative, cataloguing, and settlement rights |
| **Faculty Guide** | `apeksha_pande` | `admin123` | Faculty Librarian permissions |
| **Student (Lead)** | `abhishek` | `student123` | Roll No: **SCS101** (Holds active loan & ready reservation) |
| **Student (Co-Author)** | `kunal` | `student123` | Roll No: **SCS104** (Holds overdue loan with fine penalty) |
| **Student (Co-Author)** | `arpit` | `student123` | Roll No: **SCS106** (Returned loan on time, full deposit refund) |
| **Student (Co-Author)** | `vishweshwar` | `student123` | Roll No: **SCS123** (Returned loan late, ₹20 fine deducted from deposit) |

---

## 🏃 Running the Development Web Server

Start the local server:
```powershell
python manage.py runserver
```

Open your browser and navigate to:
- **Public Portal & Landing Page:** [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Book Catalogue:** [http://127.0.0.1:8000/catalogue/](http://127.0.0.1:8000/catalogue/)
- **Sign In:** [http://127.0.0.1:8000/login/](http://127.0.0.1:8000/login/)
- **Interactive REST API Reference:** [http://127.0.0.1:8000/api/docs/](http://127.0.0.1:8000/api/docs/)
- **Django Standard Admin:** [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/)

---

## ⏰ Automated Daily Reminders & Queue Processing

To execute the automated background job that checks due-date proximity (loans due in next 48 hours), flags overdue accounts, and expires uncollected FIFO reservations:
```powershell
python manage.py process_library_reminders
```
*In production, this command can be scheduled via Windows Task Scheduler or cron (`0 0 * * *`).*

---

## 🧪 Automated Test Suite

Run the comprehensive test suite to verify role permissions, privacy, duplicate protection, fine calculations, and queue operations:
```powershell
python manage.py test
```

### Verified Test Cases:
1. `test_role_based_dashboard_access`: Verifies admin and student RBAC.
2. `test_student_record_privacy`: Ensures students cannot view another student's loan receipt or personal records.
3. `test_book_search_and_dynamic_availability`: Tests real-time physical copy counters without drift.
4. `test_issue_workflow_and_duplicate_prevention`: Verifies atomic copy locking and double-loan prevention.
5. `test_return_on_due_date_zero_fine`: Zero overdue days, zero fine, full deposit refund.
6. `test_return_fine_smaller_than_deposit`: 4 days late $\rightarrow$ ₹20 fine offset, ₹480 refund.
7. `test_return_fine_greater_than_deposit`: 110 days late $\rightarrow$ ₹500 deposit exhausted, ₹50 balance outstanding.
8. `test_duplicate_return_prevention`: Prevents double-settlement on returned loans.
9. `test_reservation_queue_ordering_and_expiration`: Verifies FIFO position ordering and auto-expiration past pickup deadlines.
10. `test_policy_change_does_not_alter_existing_loans`: Verifies that global settings updates never modify the snapshotted financial terms of active loans.

---

## 📡 REST API Overview

| Endpoint | Method | Permission | Description |
|---|---|---|---|
| `/api/profile/` | `GET` | Authenticated | Current user profile, role, active loans & fines |
| `/api/books/` | `GET`, `POST` | Public / Admin | Search catalogue (`?search=`, `?category=`, `?available=true`) |
| `/api/books/<id>/` | `GET`, `PUT` | Public / Admin | Bibliographic detail & physical copy inventory |
| `/api/copies/` | `GET`, `POST` | Librarian | Physical copy management & accession creation |
| `/api/students/` | `GET` | Librarian | Directory of registered student borrowers |
| `/api/loans/` | `GET` | Authenticated | Loans list (students see own; admin sees all) |
| `/api/loans/issue/` | `POST` | Librarian | Check out copy, enforce limits, collect deposit |
| `/api/loans/<id>/return/` | `POST` | Librarian | Process return, auto-settle fine from deposit |
| `/api/reservations/` | `GET`, `POST` | Authenticated | View FIFO queue, request book reservation |
| `/api/finances/` | `GET` | Authenticated | Auditable financial transaction ledger |
| `/api/notifications/` | `GET` | Authenticated | In-app alerts & reminders |
| `/api/dashboard/stats/` | `GET` | Authenticated | Aggregated metrics and live Chart.js datasets |

---

## 📜 Academic Integrity Statement

This project was built for academic evaluation at **ASM Nextgen Technical Campus**, **Department of Computer Science**, for Academic Year **2025–2026**. All student data is fictional and seeded specifically for demonstration purposes.
