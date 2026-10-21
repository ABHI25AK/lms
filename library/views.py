import csv
from decimal import Decimal
from datetime import date, datetime, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Sum, Q
from django.http import HttpResponse, JsonResponse
from django.utils import timezone

from .models import (
    LibrarySettings, StudentProfile, Category, Book, BookCopy,
    Loan, Reservation, FinancialTransaction, Notification, AuditLog
)
from .forms import (
    StudentRegistrationForm, StudentProfileForm, BookForm,
    BookCopyForm, IssueBookForm, ReturnBookForm, LibrarySettingsForm
)

def record_audit(request, action, module, details):
    """Utility helper to persist user activity in AuditLog."""
    ip = request.META.get('REMOTE_ADDR')
    user = request.user if request.user.is_authenticated else None
    AuditLog.objects.create(
        user=user,
        action=action,
        module=module,
        details=details,
        ip_address=ip
    )

def librarian_required(view_func):
    """Decorator ensuring current user is staff/librarian."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not (request.user.is_staff or request.user.is_superuser):
            messages.error(request, "Access restricted to Library Staff and Administrators.")
            return redirect('student_dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper

def student_required(view_func):
    """Decorator ensuring current user is authenticated student."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if request.user.is_staff or request.user.is_superuser:
            return redirect('librarian_dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


# ==============================================================================
# PUBLIC VIEWS
# ==============================================================================

def home(request):
    """
    Public landing page introducing ASM Nextgen Technical Campus Library.
    """
    settings = LibrarySettings.get_settings()
    total_titles = Book.objects.filter(is_active=True).count()
    total_copies = BookCopy.objects.count()
    available_copies = BookCopy.objects.filter(status='AVAILABLE', condition__in=['NEW', 'GOOD', 'FAIR']).count()
    categories = Category.objects.annotate(book_count=Count('books')).filter(book_count__gt=0)
    
    featured_books = Book.objects.filter(is_active=True).select_related('category').prefetch_related('copies')[:6]

    return render(request, 'public/home.html', {
        'settings': settings,
        'total_titles': total_titles,
        'total_copies': total_copies,
        'available_copies': available_copies,
        'categories': categories,
        'featured_books': featured_books,
    })


def catalogue(request):
    """
    Searchable book catalogue with live filters and real-time stock counters.
    """
    query = request.GET.get('q', '').strip()
    category_slug = request.GET.get('category', '').strip()
    availability = request.GET.get('availability', '').strip()

    books_qs = Book.objects.filter(is_active=True).select_related('category').prefetch_related('copies')

    if query:
        books_qs = books_qs.filter(
            Q(title__icontains=query) |
            Q(author__icontains=query) |
            Q(isbn__icontains=query) |
            Q(shelf_location__icontains=query)
        )

    if category_slug:
        books_qs = books_qs.filter(category__slug=category_slug)

    # Convert to list if availability filtering is needed
    if availability == 'available':
        filtered = [b for b in books_qs if b.is_available]
    elif availability == 'checked_out':
        filtered = [b for b in books_qs if not b.is_available]
    else:
        filtered = list(books_qs)

    paginator = Paginator(filtered, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    categories = Category.objects.all()

    return render(request, 'public/catalogue.html', {
        'page_obj': page_obj,
        'categories': categories,
        'query': query,
        'category_slug': category_slug,
        'availability': availability,
        'total_count': len(filtered),
    })


def book_detail(request, pk):
    """
    Public book detail page showing bibliographic data, copy shelf locations, and reservation status.
    """
    book = get_object_or_404(Book.objects.select_related('category').prefetch_related('copies'), pk=pk)
    copies = book.copies.all().order_by('accession_number')
    
    user_has_active_loan = False
    user_active_reservation = None

    if request.user.is_authenticated and not request.user.is_staff:
        user_has_active_loan = Loan.objects.filter(student=request.user, copy__book=book, status__in=['ACTIVE', 'OVERDUE']).exists()
        user_active_reservation = Reservation.objects.filter(
            book=book, student=request.user, status__in=['PENDING', 'APPROVED', 'READY_FOR_PICKUP']
        ).first()

    return render(request, 'public/book_detail.html', {
        'book': book,
        'copies': copies,
        'user_has_active_loan': user_has_active_loan,
        'user_active_reservation': user_active_reservation,
    })


def login_view(request):
    """
    Role-based authentication login view.
    """
    if request.user.is_authenticated:
        return redirect('dashboard_redirect')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        user = authenticate(request, username=username, password=password)
        if user is not None:
            if not user.is_active:
                messages.error(request, "Your account has been deactivated. Please contact the librarian.")
                return render(request, 'public/login.html')

            login(request, user)
            record_audit(request, "USER_LOGIN", "AUTH", f"User {user.username} logged in successfully.")
            messages.success(request, f"Welcome back, {user.first_name or user.username}!")
            return redirect('dashboard_redirect')
        else:
            messages.error(request, "Invalid username or password. Please try again.")

    return render(request, 'public/login.html')


def logout_view(request):
    """
    Session termination.
    """
    if request.user.is_authenticated:
        record_audit(request, "USER_LOGOUT", "AUTH", f"User {request.user.username} logged out.")
        logout(request)
        messages.info(request, "You have been logged out successfully.")
    return redirect('home')


def register_view(request):
    """
    Student self-service account registration (if enabled by admin).
    """
    settings = LibrarySettings.get_settings()
    if not settings.allow_student_registration:
        messages.error(request, "Online student self-registration is currently disabled by the administration.")
        return redirect('login')

    if request.user.is_authenticated:
        return redirect('dashboard_redirect')

    if request.method == 'POST':
        form = StudentRegistrationForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = User.objects.create_user(
                    username=form.cleaned_data['username'],
                    first_name=form.cleaned_data['first_name'],
                    last_name=form.cleaned_data['last_name'],
                    email=form.cleaned_data['email'],
                    password=form.cleaned_data['password'],
                    is_staff=False,
                    is_superuser=False
                )
                StudentProfile.objects.create(
                    user=user,
                    roll_number=form.cleaned_data['roll_number'],
                    department="Department of Computer Science",
                    academic_year=settings.academic_year,
                    semester=form.cleaned_data['semester'],
                    phone=form.cleaned_data['phone'],
                    address=form.cleaned_data['address'],
                    max_books_allowed=settings.max_active_loans
                )

                # Send welcome notification
                Notification.objects.create(
                    recipient=user,
                    title="Welcome to ASM Library!",
                    message="Your student library account is active. You can browse catalogue, borrow books, and reserve titles online.",
                    notification_type='GENERAL',
                    link="/catalogue/"
                )

                record_audit(request, "STUDENT_REGISTRATION", "AUTH", f"New student account created: {user.username} (Roll: {form.cleaned_data['roll_number']})")

            messages.success(request, "Registration successful! You may now sign in.")
            return redirect('login')
    else:
        form = StudentRegistrationForm()

    return render(request, 'public/register.html', {'form': form})


@login_required
def dashboard_redirect(request):
    """
    Redirects authenticated users to their corresponding role portal.
    """
    if request.user.is_staff or request.user.is_superuser:
        return redirect('librarian_dashboard')
    return redirect('student_dashboard')


# ==============================================================================
# STUDENT PORTAL VIEWS
# ==============================================================================

@student_required
def student_dashboard(request):
    """
    Personal student dashboard displaying loan stats, upcoming due dates, and notifications.
    """
    user = request.user
    profile = getattr(user, 'student_profile', None)

    active_loans = Loan.objects.filter(student=user, status__in=['ACTIVE', 'OVERDUE']).select_related('copy__book').order_by('due_date')
    overdue_count = active_loans.filter(status='OVERDUE').count()
    
    reservations = Reservation.objects.filter(student=user, status__in=['PENDING', 'APPROVED', 'READY_FOR_PICKUP']).select_related('book', 'allocated_copy')
    
    # Financial summary
    deposits_held = sum(loan.deposit_amount for loan in active_loans)
    unpaid_loans = Loan.objects.filter(student=user, status='RETURNED', fine_status='PARTIALLY_SETTLED')
    outstanding_fines = sum(l.remaining_fine_due for l in unpaid_loans)

    pending_refund_loans = Loan.objects.filter(student=user, status='RETURNED', refund_status='PENDING')
    refunds_pending = sum(l.refund_due - l.refund_paid for l in pending_refund_loans)

    notifications = Notification.objects.filter(recipient=user).order_by('-created_at')[:6]

    return render(request, 'student/dashboard.html', {
        'profile': profile,
        'active_loans': active_loans,
        'overdue_count': overdue_count,
        'reservations': reservations,
        'deposits_held': deposits_held,
        'outstanding_fines': outstanding_fines,
        'refunds_pending': refunds_pending,
        'notifications': notifications,
        'today': date.today(),
    })


@student_required
def student_loans(request):
    """
    Displays active borrowings and historical loans with fine settlement receipts.
    """
    user = request.user
    active_loans = Loan.objects.filter(student=user, status__in=['ACTIVE', 'OVERDUE']).select_related('copy__book').order_by('due_date')
    history_loans = Loan.objects.filter(student=user, status='RETURNED').select_related('copy__book').order_by('-return_date')

    return render(request, 'student/my_loans.html', {
        'active_loans': active_loans,
        'history_loans': history_loans,
        'today': date.today(),
    })


@student_required
def student_reservations(request):
    """
    Displays active and historical book reservations with queue position and pickup deadlines.
    """
    user = request.user
    reservations = Reservation.objects.filter(student=user).select_related('book', 'allocated_copy').order_by('-request_date')

    for r in reservations:
        if r.status in ['PENDING', 'APPROVED']:
            r.recalculate_queue_position()

    return render(request, 'student/my_reservations.html', {
        'reservations': reservations,
        'now': timezone.now(),
    })


@student_required
def student_reserve_book(request, book_id):
    """
    Action to place a book reservation request.
    """
    if request.method != 'POST':
        return redirect('catalogue')

    book = get_object_or_404(Book, pk=book_id, is_active=True)
    user = request.user

    # Prevent duplicate active reservations
    exists = Reservation.objects.filter(
        book=book,
        student=user,
        status__in=['PENDING', 'APPROVED', 'READY_FOR_PICKUP']
    ).exists()

    if exists:
        messages.warning(request, f"You already have an active reservation for '{book.title}'.")
        return redirect('book_detail', pk=book.id)

    # Check available copies policy
    settings = LibrarySettings.get_settings()
    if not settings.allow_reserving_available_books and book.is_available:
        messages.info(request, "This title currently has physical copies available on the shelf. Please visit the library counter directly to issue it.")
        return redirect('book_detail', pk=book.id)

    with transaction.atomic():
        res = Reservation.objects.create(
            book=book,
            student=user,
            status='PENDING'
        )
        res.recalculate_queue_position()
        res.save()

        Notification.objects.create(
            recipient=user,
            title="Reservation Submitted",
            message=f"Your reservation for '{book.title}' is queued (Position #{res.queue_position}). You will receive an alert once approved.",
            notification_type='GENERAL',
            link="/student/reservations/"
        )

        record_audit(request, "STUDENT_RESERVE", "RESERVATIONS", f"Student {user.username} reserved '{book.title}' (Queue #{res.queue_position})")

    messages.success(request, f"Reservation placed for '{book.title}'! Your queue position is #{res.queue_position}.")
    return redirect('student_reservations')


@student_required
def student_cancel_reservation(request, pk):
    """
    Cancel an active reservation.
    """
    if request.method != 'POST':
        return redirect('student_reservations')

    res = get_object_or_404(Reservation, pk=pk, student=request.user)
    if res.status in ['FULFILLED', 'CANCELLED', 'EXPIRED']:
        messages.warning(request, "This reservation cannot be cancelled.")
        return redirect('student_reservations')

    with transaction.atomic():
        copy = res.allocated_copy
        res.status = 'CANCELLED'
        res.cancelled_at = timezone.now()
        res.allocated_copy = None
        res.save()

        # If a copy was reserved for them, reallocate to next student or make available!
        if copy:
            next_res = Reservation.objects.filter(
                book=copy.book, status='APPROVED', allocated_copy__isnull=True
            ).order_by('request_date').first()

            if next_res:
                settings = LibrarySettings.get_settings()
                deadline = timezone.now() + timedelta(hours=settings.reservation_pickup_hours)
                next_res.status = 'READY_FOR_PICKUP'
                next_res.allocated_copy = copy
                next_res.pickup_deadline = deadline
                next_res.notification_sent = True
                next_res.save()

                Notification.objects.create(
                    recipient=next_res.student,
                    title="Book Ready for Pickup!",
                    message=f"'{copy.book.title}' is ready for pickup following a queue update. Collect before {deadline.strftime('%d-%b-%Y %I:%M %p')}.",
                    notification_type='RESERVATION_READY',
                    link="/student/reservations/"
                )
            else:
                copy.status = 'AVAILABLE'
                copy.save()

        record_audit(request, "CANCEL_RESERVATION", "RESERVATIONS", f"Reservation #{res.id} for '{res.book.title}' cancelled by {request.user.username}.")

    messages.success(request, "Reservation cancelled successfully.")
    return redirect('student_reservations')


@student_required
def student_fines_deposits(request):
    """
    Statement of security deposits, fine adjustments, and refunds.
    """
    user = request.user
    loans = Loan.objects.filter(student=user).select_related('copy__book').order_by('-created_at')
    transactions = FinancialTransaction.objects.filter(student=user).select_related('loan').order_by('-created_at')

    active_deposits = sum(l.deposit_amount for l in loans.filter(status__in=['ACTIVE', 'OVERDUE']))
    total_fines_assessed = sum(l.fine_amount for l in loans.filter(status='RETURNED'))
    total_fines_paid = (
        sum(l.deposit_applied for l in loans.filter(status='RETURNED')) +
        sum(l.fine_collected for l in loans.filter(status='RETURNED'))
    )
    unpaid_fines = sum(l.remaining_fine_due for l in loans.filter(status='RETURNED', fine_status='PARTIALLY_SETTLED'))
    refunds_pending = sum(l.refund_due - l.refund_paid for l in loans.filter(status='RETURNED', refund_status='PENDING'))

    return render(request, 'student/fines_deposits.html', {
        'loans': loans,
        'transactions': transactions,
        'active_deposits': active_deposits,
        'total_fines_assessed': total_fines_assessed,
        'total_fines_paid': total_fines_paid,
        'unpaid_fines': unpaid_fines,
        'refunds_pending': refunds_pending,
    })


@login_required
def student_notifications(request):
    """
    Lists notifications and provides action to mark as read.
    """
    notifications = Notification.objects.filter(recipient=request.user).order_by('-created_at')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'mark_all_read':
            notifications.filter(is_read=False).update(is_read=True)
            messages.success(request, "All notifications marked as read.")
            return redirect('student_notifications')

    return render(request, 'student/notifications.html', {
        'notifications': notifications,
    })


@login_required
def mark_single_notification_read(request, pk):
    """
    Marks a single notification as read and optionally redirects to its link.
    """
    notif = get_object_or_404(Notification, pk=pk, recipient=request.user)
    notif.is_read = True
    notif.save()
    if notif.link:
        return redirect(notif.link)
    return redirect('student_notifications')


@student_required
def student_profile(request):
    """
    Student profile overview and contact update form.
    """
    user = request.user
    profile = get_object_or_404(StudentProfile, user=user)

    if request.method == 'POST':
        form = StudentProfileForm(request.POST, instance=profile)
        if form.is_valid():
            user.first_name = form.cleaned_data['first_name']
            user.last_name = form.cleaned_data['last_name']
            user.email = form.cleaned_data['email']
            user.save()
            form.save()
            messages.success(request, "Profile updated successfully.")
            return redirect('student_profile')
    else:
        form = StudentProfileForm(instance=profile, initial={
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
        })

    return render(request, 'student/profile.html', {
        'form': form,
        'profile': profile,
    })


@login_required
def loan_receipt(request, receipt_number):
    """
    Generates a printable, auditable transaction receipt for loan issuance or return settlement.
    """
    loan = get_object_or_404(Loan.objects.select_related('student__student_profile', 'copy__book', 'issued_by', 'returned_by'), receipt_number=receipt_number)

    # Privacy check: students can only see their own receipts
    if not (request.user.is_staff or request.user.is_superuser) and loan.student != request.user:
        messages.error(request, "Permission denied. You cannot view another student's loan receipt.")
        return redirect('student_loans')

    transactions = FinancialTransaction.objects.filter(loan=loan).order_by('created_at')

    return render(request, 'librarian/receipt_detail.html', {
        'loan': loan,
        'transactions': transactions,
        'settings': LibrarySettings.get_settings(),
    })


# ==============================================================================
# ADMIN / LIBRARIAN VIEWS
# ==============================================================================

@librarian_required
def librarian_dashboard(request):
    """
    Admin overview dashboard with key circulation metrics and live Chart.js analytics.
    """
    today = date.today()
    settings = LibrarySettings.get_settings()

    total_titles = Book.objects.filter(is_active=True).count()
    total_copies = BookCopy.objects.count()
    available_copies = BookCopy.objects.filter(status='AVAILABLE', condition__in=['NEW', 'GOOD', 'FAIR']).count()
    active_students = StudentProfile.objects.filter(is_membership_active=True).count()
    active_loans = Loan.objects.filter(status='ACTIVE').count()
    overdue_loans = Loan.objects.filter(status='OVERDUE').count()
    pending_reservations = Reservation.objects.filter(status__in=['PENDING', 'APPROVED']).count()

    deposits_held = Loan.objects.filter(status__in=['ACTIVE', 'OVERDUE']).aggregate(s=Sum('deposit_amount'))['s'] or Decimal("0.00")
    fines_assessed = Loan.objects.filter(status='RETURNED').aggregate(s=Sum('fine_amount'))['s'] or Decimal("0.00")
    fines_collected = (
        (Loan.objects.filter(status='RETURNED').aggregate(s=Sum('deposit_applied'))['s'] or Decimal("0.00")) +
        (Loan.objects.filter(status='RETURNED').aggregate(s=Sum('fine_collected'))['s'] or Decimal("0.00"))
    )
    refunds_pending = (
        (Loan.objects.filter(status='RETURNED', refund_status='PENDING').aggregate(s=Sum('refund_due'))['s'] or Decimal("0.00")) -
        (Loan.objects.filter(status='RETURNED', refund_status='PENDING').aggregate(s=Sum('refund_paid'))['s'] or Decimal("0.00"))
    )

    recent_loans = Loan.objects.select_related('student', 'copy__book').order_by('-created_at')[:8]
    recent_reservations = Reservation.objects.select_related('student', 'book').order_by('-request_date')[:6]

    # Chart 1 Data: Top 6 Borrowed Books
    top_books = Book.objects.annotate(loan_count=Count('copies__loans')).order_by('-loan_count')[:6]
    top_books_labels = [b.title[:25] + "..." if len(b.title) > 25 else b.title for b in top_books]
    top_books_data = [b.loan_count for b in top_books]

    # Chart 2 Data: Borrowing by Category
    cat_stats = Category.objects.annotate(loan_count=Count('books__copies__loans')).filter(loan_count__gt=0)
    cat_labels = [c.name for c in cat_stats]
    cat_data = [c.loan_count for c in cat_stats]

    # Chart 3 Data: Inventory Copies by Status
    copy_status_counts = BookCopy.objects.values('status').annotate(total=Count('id'))
    status_map = dict(BookCopy.STATUS_CHOICES)
    inventory_labels = [status_map.get(s['status'], s['status']) for s in copy_status_counts]
    inventory_data = [s['total'] for s in copy_status_counts]

    return render(request, 'librarian/dashboard.html', {
        'total_titles': total_titles,
        'total_copies': total_copies,
        'available_copies': available_copies,
        'active_students': active_students,
        'active_loans': active_loans,
        'overdue_loans': overdue_loans,
        'pending_reservations': pending_reservations,
        'deposits_held': deposits_held,
        'fines_assessed': fines_assessed,
        'fines_collected': fines_collected,
        'refunds_pending': refunds_pending,
        'recent_loans': recent_loans,
        'recent_reservations': recent_reservations,
        'top_books_labels': top_books_labels,
        'top_books_data': top_books_data,
        'cat_labels': cat_labels,
        'cat_data': cat_data,
        'inventory_labels': inventory_labels,
        'inventory_data': inventory_data,
        'today': today,
    })


@librarian_required
def admin_books(request):
    """
    Catalogue inventory management for administrators.
    """
    query = request.GET.get('q', '').strip()
    category_id = request.GET.get('category', '').strip()
    status_filter = request.GET.get('status', '').strip()

    books = Book.objects.select_related('category').prefetch_related('copies').order_by('title')

    if query:
        books = books.filter(
            Q(title__icontains=query) |
            Q(author__icontains=query) |
            Q(isbn__icontains=query) |
            Q(shelf_location__icontains=query)
        )
    if category_id:
        books = books.filter(category_id=category_id)
    if status_filter == 'active':
        books = books.filter(is_active=True)
    elif status_filter == 'archived':
        books = books.filter(is_active=False)

    paginator = Paginator(books, 15)
    page_obj = paginator.get_page(request.GET.get('page'))
    categories = Category.objects.all()

    return render(request, 'librarian/book_list.html', {
        'page_obj': page_obj,
        'categories': categories,
        'query': query,
        'category_id': category_id,
        'status_filter': status_filter,
    })


@librarian_required
def admin_book_add(request):
    """
    Add a new book title to the catalogue.
    """
    if request.method == 'POST':
        form = BookForm(request.POST, request.FILES)
        if form.is_valid():
            book = form.save()
            record_audit(request, "ADD_BOOK", "CATALOGUE", f"Added book title '{book.title}' (ISBN: {book.isbn})")
            messages.success(request, f"Book '{book.title}' added successfully. You can now add physical copies.")
            return redirect('admin_book_detail', pk=book.id)
    else:
        form = BookForm()

    return render(request, 'librarian/book_form.html', {
        'form': form,
        'title': "Add New Book Title",
        'is_edit': False,
    })


@librarian_required
def admin_book_edit(request, pk):
    """
    Edit bibliographic metadata of an existing book.
    """
    book = get_object_or_404(Book, pk=pk)
    if request.method == 'POST':
        form = BookForm(request.POST, request.FILES, instance=book)
        if form.is_valid():
            form.save()
            record_audit(request, "EDIT_BOOK", "CATALOGUE", f"Updated book #{book.id} - '{book.title}'")
            messages.success(request, f"Book '{book.title}' updated successfully.")
            return redirect('admin_book_detail', pk=book.id)
    else:
        form = BookForm(instance=book)

    return render(request, 'librarian/book_form.html', {
        'form': form,
        'title': f"Edit Book: {book.title}",
        'is_edit': True,
        'book': book,
    })


@librarian_required
def admin_book_detail(request, pk):
    """
    Admin detail view of a book with its physical copies, active loans, and reservation queue.
    """
    book = get_object_or_404(Book.objects.select_related('category').prefetch_related('copies'), pk=pk)
    copies = book.copies.all().order_by('accession_number')
    reservations = book.reservations.select_related('student').order_by('request_date')

    copy_form = BookCopyForm(initial={'book': book, 'shelf_location': book.shelf_location})

    return render(request, 'librarian/book_detail_admin.html', {
        'book': book,
        'copies': copies,
        'reservations': reservations,
        'copy_form': copy_form,
    })


@librarian_required
def admin_copy_add(request, book_id):
    """
    Add one or more physical copies with accession numbers for a book.
    """
    book = get_object_or_404(Book, pk=book_id)
    if request.method == 'POST':
        form = BookCopyForm(request.POST)
        if form.is_valid():
            num_copies = form.cleaned_data.get('number_of_copies', 1)
            condition = form.cleaned_data.get('condition', 'GOOD')
            status_choice = form.cleaned_data.get('status', 'AVAILABLE')
            shelf_location = form.cleaned_data.get('shelf_location') or book.shelf_location
            notes = form.cleaned_data.get('notes', '')

            custom_accession = form.cleaned_data.get('accession_number')

            created_copies = []
            with transaction.atomic():
                for i in range(num_copies):
                    if custom_accession and num_copies == 1:
                        acc = custom_accession
                    else:
                        # Auto-generate unique accession number
                        last_copy = BookCopy.objects.order_by('-id').first()
                        next_num = (last_copy.id + 101) if last_copy else 101
                        acc = f"CS-{date.today().year}-{next_num + i:04d}"

                    copy = BookCopy.objects.create(
                        book=book,
                        accession_number=acc,
                        shelf_location=shelf_location,
                        condition=condition,
                        status=status_choice,
                        notes=notes
                    )
                    created_copies.append(copy)

            record_audit(request, "ADD_COPIES", "INVENTORY", f"Added {len(created_copies)} physical copies for '{book.title}'")
            messages.success(request, f"Successfully created {len(created_copies)} copy records for '{book.title}'.")
            return redirect('admin_book_detail', pk=book.id)
    return redirect('admin_book_detail', pk=book.id)


@librarian_required
def admin_copy_update_status(request, pk):
    """
    Update condition or status of an existing physical copy.
    """
    copy = get_object_or_404(BookCopy, pk=pk)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        new_condition = request.POST.get('condition')
        shelf = request.POST.get('shelf_location')

        if copy.status == 'ON_LOAN' and new_status != 'ON_LOAN':
            messages.error(request, "Cannot change status of a copy that is currently ON LOAN. Process a return first.")
            return redirect('admin_book_detail', pk=copy.book.id)

        copy.status = new_status
        copy.condition = new_condition
        if shelf:
            copy.shelf_location = shelf
        copy.save()

        record_audit(request, "UPDATE_COPY", "INVENTORY", f"Updated copy {copy.accession_number} to {new_status} / {new_condition}")
        messages.success(request, f"Copy {copy.accession_number} updated.")
    return redirect('admin_book_detail', pk=copy.book.id)


@librarian_required
def admin_issue_book(request):
    """
    Interactive issue workflow enforcing student limits, reservation priority, and deposit collection.
    """
    settings = LibrarySettings.get_settings()
    preselected_copy_id = request.GET.get('copy_id')
    preselected_student_id = request.GET.get('student_id')

    if request.method == 'POST':
        form = IssueBookForm(request.POST)
        if form.is_valid():
            student = form.cleaned_data['student']
            copy = form.cleaned_data['copy']
            deposit_collected = form.cleaned_data['deposit_collected']
            payment_mode = form.cleaned_data['payment_mode']
            notes = form.cleaned_data['notes']

            today = date.today()
            due_date = today + timedelta(days=settings.loan_period_days)

            with transaction.atomic():
                copy.status = 'ON_LOAN'
                copy.save()

                loan = Loan.objects.create(
                    copy=copy,
                    student=student,
                    issue_date=today,
                    due_date=due_date,
                    status='ACTIVE',
                    deposit_amount=deposit_collected,
                    daily_fine_rate=settings.daily_fine_rate,
                    issued_by=request.user,
                    notes=notes
                )

                # Record security deposit transaction
                FinancialTransaction.objects.create(
                    loan=loan,
                    student=student,
                    transaction_type='DEPOSIT_COLLECTED',
                    amount=deposit_collected,
                    payment_mode=payment_mode,
                    reference_number=f"TXN-DEP-{timezone.now().strftime('%Y%m%d%H%M%S')}-{loan.id}",
                    recorded_by=request.user,
                    notes=f"Refundable security deposit collected for Loan #{loan.receipt_number}"
                )

                # Fulfill any matching active reservation for this student & book
                res = Reservation.objects.filter(
                    book=copy.book, student=student, status__in=['PENDING', 'APPROVED', 'READY_FOR_PICKUP']
                ).first()
                if res:
                    res.status = 'FULFILLED'
                    res.fulfilled_at = timezone.now()
                    res.save()

                Notification.objects.create(
                    recipient=student,
                    title="Book Issued Successfully",
                    message=f"'{copy.book.title}' (Copy: {copy.accession_number}) has been issued. Due date: {due_date.strftime('%d-%b-%Y')}. Deposit held: ₹{deposit_collected}.",
                    notification_type='BOOK_ISSUED',
                    link="/student/loans/"
                )

                record_audit(request, "ISSUE_BOOK", "CIRCULATION", f"Issued copy {copy.accession_number} to {student.username}. Receipt #{loan.receipt_number}")

            messages.success(request, f"Book issued successfully! Receipt #{loan.receipt_number} generated.")
            return redirect('loan_receipt', receipt_number=loan.receipt_number)
    else:
        initial = {}
        if preselected_copy_id:
            initial['copy'] = preselected_copy_id
        if preselected_student_id:
            initial['student'] = preselected_student_id
        form = IssueBookForm(initial=initial)

    return render(request, 'librarian/issue_book.html', {
        'form': form,
        'settings': settings,
    })


@librarian_required
def admin_return_book(request):
    """
    Interactive return workflow with auto-calculated overdue fine, deposit settlement, and refund options.
    """
    preselected_loan_id = request.GET.get('loan_id')

    if request.method == 'POST':
        form = ReturnBookForm(request.POST)
        if form.is_valid():
            loan = form.cleaned_data['loan']
            return_date_val = form.cleaned_data['return_date']
            disburse_refund = form.cleaned_data['disburse_refund_now']
            collect_fine = form.cleaned_data['collect_remaining_fine_now']
            notes = form.cleaned_data['notes']

            with transaction.atomic():
                loan.execute_return_and_settlement(return_date_val, request.user, notes)

                # Disburse cash refund if student has money due back
                if disburse_refund and loan.refund_due > Decimal("0.00") and loan.refund_status == 'PENDING':
                    loan.refund_paid = loan.refund_due
                    loan.refund_status = 'PAID'
                    loan.save()

                    FinancialTransaction.objects.create(
                        loan=loan,
                        student=loan.student,
                        transaction_type='REFUND_ISSUED',
                        amount=loan.refund_due,
                        payment_mode='CASH',
                        reference_number=f"TXN-REF-{timezone.now().strftime('%Y%m%d%H%M%S')}-{loan.id}",
                        recorded_by=request.user,
                        notes=f"Deposit balance refund of ₹{loan.refund_due} paid in cash to student on return."
                    )

                # Collect extra fine cash if fine exceeded deposit
                if collect_fine and loan.remaining_fine_due > Decimal("0.00") and loan.fine_status == 'PARTIALLY_SETTLED':
                    loan.fine_collected = loan.remaining_fine_due
                    loan.fine_status = 'FULLY_PAID'
                    loan.save()

                    FinancialTransaction.objects.create(
                        loan=loan,
                        student=loan.student,
                        transaction_type='FINE_COLLECTED_CASH',
                        amount=loan.remaining_fine_due,
                        payment_mode='CASH',
                        reference_number=f"TXN-CASH-{timezone.now().strftime('%Y%m%d%H%M%S')}-{loan.id}",
                        recorded_by=request.user,
                        notes=f"Outstanding fine of ₹{loan.remaining_fine_due} collected in cash from student."
                    )

            messages.success(request, f"Loan #{loan.receipt_number} returned and settled successfully.")
            return redirect('loan_receipt', receipt_number=loan.receipt_number)
    else:
        initial = {}
        if preselected_loan_id:
            initial['loan'] = preselected_loan_id
        form = ReturnBookForm(initial=initial)

    active_loans = Loan.objects.filter(status__in=['ACTIVE', 'OVERDUE']).select_related('student', 'copy__book')

    return render(request, 'librarian/return_book.html', {
        'form': form,
        'active_loans': active_loans,
        'today': date.today(),
    })


@librarian_required
def admin_disburse_refund(request, pk):
    """
    Disburse pending cash refund for an already returned loan.
    """
    loan = get_object_or_404(Loan, pk=pk)
    if loan.refund_status != 'PENDING':
        messages.warning(request, "This loan does not have a pending refund.")
        return redirect('admin_financial_ledger')

    amount_to_pay = loan.refund_due - loan.refund_paid
    if amount_to_pay <= Decimal("0.00"):
        loan.refund_status = 'PAID'
        loan.save()
        messages.info(request, "Refund was already fully disbursed.")
        return redirect('admin_financial_ledger')

    with transaction.atomic():
        loan.refund_paid = loan.refund_due
        loan.refund_status = 'PAID'
        loan.save()

        FinancialTransaction.objects.create(
            loan=loan,
            student=loan.student,
            transaction_type='REFUND_ISSUED',
            amount=amount_to_pay,
            payment_mode='CASH',
            reference_number=f"TXN-REF-{timezone.now().strftime('%Y%m%d%H%M%S')}-{loan.id}",
            recorded_by=request.user,
            notes=f"Disbursed remaining deposit refund of ₹{amount_to_pay} in cash."
        )

        record_audit(request, "DISBURSE_REFUND", "FINANCE", f"Disbursed refund of ₹{amount_to_pay} to {loan.student.username} for Loan #{loan.receipt_number}")

    messages.success(request, f"Refund of ₹{amount_to_pay} marked as disbursed.")
    return redirect('admin_financial_ledger')


@librarian_required
def admin_collect_fine(request, pk):
    """
    Collect remaining cash fine from student for a loan where fine exceeded deposit.
    """
    loan = get_object_or_404(Loan, pk=pk)
    if loan.fine_status != 'PARTIALLY_SETTLED':
        messages.warning(request, "This loan does not have an outstanding fine balance.")
        return redirect('admin_financial_ledger')

    with transaction.atomic():
        unpaid = loan.remaining_fine_due
        loan.fine_collected = unpaid
        loan.fine_status = 'FULLY_PAID'
        loan.save()

        FinancialTransaction.objects.create(
            loan=loan,
            student=loan.student,
            transaction_type='FINE_COLLECTED_CASH',
            amount=unpaid,
            payment_mode='CASH',
            reference_number=f"TXN-CASH-{timezone.now().strftime('%Y%m%d%H%M%S')}-{loan.id}",
            recorded_by=request.user,
            notes=f"Collected remaining overdue fine of ₹{unpaid} in cash."
        )

        record_audit(request, "COLLECT_FINE", "FINANCE", f"Collected fine ₹{unpaid} in cash from {loan.student.username} for Loan #{loan.receipt_number}")

    messages.success(request, f"Collected outstanding fine of ₹{unpaid} from {loan.student.username}.")
    return redirect('admin_financial_ledger')


@librarian_required
def admin_reservations(request):
    """
    Reservation queue management: approve, reject, mark ready, or cancel.
    """
    status_filter = request.GET.get('status', '').strip()
    reservations = Reservation.objects.select_related('book', 'student', 'allocated_copy').order_by('request_date')

    if status_filter:
        reservations = reservations.filter(status=status_filter)

    for r in reservations:
        if r.status in ['PENDING', 'APPROVED']:
            r.recalculate_queue_position()

    return render(request, 'librarian/reservation_list.html', {
        'reservations': reservations,
        'status_filter': status_filter,
        'now': timezone.now(),
    })


@librarian_required
def admin_reservation_action(request, pk, action):
    """
    Action dispatcher for reservations: approve, reject, mark_ready, cancel.
    """
    res = get_object_or_404(Reservation, pk=pk)
    settings = LibrarySettings.get_settings()

    with transaction.atomic():
        if action == 'approve':
            res.status = 'APPROVED'
            res.approved_by = request.user
            res.recalculate_queue_position()
            res.save()

            Notification.objects.create(
                recipient=res.student,
                title="Reservation Approved",
                message=f"Your reservation for '{res.book.title}' is approved (Queue Position #{res.queue_position}). You will be notified when a copy is available.",
                notification_type='RESERVATION_APPROVED',
                link="/student/reservations/"
            )
            messages.success(request, f"Reservation #{res.id} approved.")

        elif action == 'reject':
            res.status = 'CANCELLED'
            res.cancelled_at = timezone.now()
            res.save()

            Notification.objects.create(
                recipient=res.student,
                title="Reservation Rejected",
                message=f"Your reservation for '{res.book.title}' could not be accommodated at this time.",
                notification_type='GENERAL',
                link="/catalogue/"
            )
            messages.info(request, f"Reservation #{res.id} rejected.")

        elif action == 'ready':
            # Find an available copy to allocate
            available_copy = res.book.copies.filter(status='AVAILABLE', condition__in=['NEW', 'GOOD', 'FAIR']).first()
            if not available_copy:
                messages.error(request, f"No available physical copies for '{res.book.title}' to allocate right now.")
                return redirect('admin_reservations')

            available_copy.status = 'RESERVED'
            available_copy.save()

            deadline = timezone.now() + timedelta(hours=settings.reservation_pickup_hours)
            res.status = 'READY_FOR_PICKUP'
            res.allocated_copy = available_copy
            res.pickup_deadline = deadline
            res.notification_sent = True
            res.save()

            Notification.objects.create(
                recipient=res.student,
                title="Book Ready for Pickup!",
                message=f"'{res.book.title}' (Copy: {available_copy.accession_number}) is ready for pickup! Please collect it before {deadline.strftime('%d-%b-%Y %I:%M %p')}.",
                notification_type='RESERVATION_READY',
                link="/student/reservations/"
            )
            messages.success(request, f"Copy {available_copy.accession_number} allocated to reservation #{res.id}.")

        elif action == 'cancel':
            copy = res.allocated_copy
            res.status = 'CANCELLED'
            res.cancelled_at = timezone.now()
            res.allocated_copy = None
            res.save()

            if copy:
                copy.status = 'AVAILABLE'
                copy.save()

            messages.info(request, f"Reservation #{res.id} cancelled.")

        record_audit(request, f"RESERVATION_{action.upper()}", "RESERVATIONS", f"Reservation #{res.id} for {res.student.username} updated with action '{action}'.")

    return redirect('admin_reservations')


@librarian_required
def admin_students(request):
    """
    Student directory and borrowing account management.
    """
    query = request.GET.get('q', '').strip()
    students = User.objects.filter(is_staff=False).select_related('student_profile').order_by('username')

    if query:
        students = students.filter(
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(student_profile__roll_number__icontains=query) |
            Q(email__icontains=query)
        )

    paginator = Paginator(students, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'librarian/student_list.html', {
        'page_obj': page_obj,
        'query': query,
    })


@librarian_required
def admin_student_detail(request, pk):
    """
    Detailed profile of a student including active loans, borrowing history, reservations, and financial ledger.
    """
    student = get_object_or_404(User.objects.select_related('student_profile'), pk=pk, is_staff=False)
    active_loans = Loan.objects.filter(student=student, status__in=['ACTIVE', 'OVERDUE']).select_related('copy__book')
    loan_history = Loan.objects.filter(student=student, status='RETURNED').select_related('copy__book').order_by('-return_date')
    reservations = Reservation.objects.filter(student=student).select_related('book').order_by('-request_date')
    transactions = FinancialTransaction.objects.filter(student=student).select_related('loan').order_by('-created_at')

    return render(request, 'librarian/student_detail.html', {
        'student': student,
        'profile': getattr(student, 'student_profile', None),
        'active_loans': active_loans,
        'loan_history': loan_history,
        'reservations': reservations,
        'transactions': transactions,
        'today': date.today(),
    })


@librarian_required
def admin_financial_ledger(request):
    """
    Auditable financial transaction ledger with filters and CSV export.
    """
    txn_type = request.GET.get('type', '').strip()
    search = request.GET.get('q', '').strip()

    transactions = FinancialTransaction.objects.select_related('student', 'loan', 'recorded_by').order_by('-created_at')

    if txn_type:
        transactions = transactions.filter(transaction_type=txn_type)
    if search:
        transactions = transactions.filter(
            Q(reference_number__icontains=search) |
            Q(student__username__icontains=search) |
            Q(notes__icontains=search)
        )

    # Export CSV if requested
    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="financial_ledger_{date.today().strftime("%Y%m%d")}.csv"'
        writer = csv.writer(response)
        writer.writerow(['Ref Number', 'Date', 'Student', 'Type', 'Amount (INR)', 'Payment Mode', 'Loan Receipt', 'Recorded By', 'Notes'])
        for t in transactions:
            writer.writerow([
                t.reference_number,
                t.created_at.strftime('%Y-%m-%d %H:%M'),
                t.student.username,
                t.get_transaction_type_display(),
                t.amount,
                t.get_payment_mode_display(),
                t.loan.receipt_number if t.loan else 'N/A',
                t.recorded_by.username if t.recorded_by else 'System',
                t.notes
            ])
        return response

    paginator = Paginator(transactions, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    # Pending refunds list
    pending_refund_loans = Loan.objects.filter(status='RETURNED', refund_status='PENDING').select_related('student', 'copy__book')
    outstanding_fine_loans = Loan.objects.filter(status='RETURNED', fine_status='PARTIALLY_SETTLED').select_related('student', 'copy__book')

    return render(request, 'librarian/financial_ledger.html', {
        'page_obj': page_obj,
        'txn_type': txn_type,
        'search': search,
        'pending_refund_loans': pending_refund_loans,
        'outstanding_fine_loans': outstanding_fine_loans,
    })


@librarian_required
def admin_reports(request):
    """
    Comprehensive analytics and reports with Chart.js charts and CSV downloads.
    """
    today = date.today()
    start_date = request.GET.get('start_date', (today - timedelta(days=90)).strftime('%Y-%m-%d'))
    end_date = request.GET.get('end_date', today.strftime('%Y-%m-%d'))

    loans = Loan.objects.filter(issue_date__gte=start_date, issue_date__lte=end_date).select_related('student', 'copy__book')

    # CSV Exports
    export_type = request.GET.get('export')
    if export_type == 'loans':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="circulation_report_{date.today().strftime("%Y%m%d")}.csv"'
        writer = csv.writer(response)
        writer.writerow(['Receipt', 'Student', 'Roll No', 'Book Title', 'Accession', 'Issue Date', 'Due Date', 'Return Date', 'Status', 'Deposit', 'Fine', 'Refund Due'])
        for l in loans:
            writer.writerow([
                l.receipt_number,
                l.student.get_full_name() or l.student.username,
                l.student.student_profile.roll_number if hasattr(l.student, 'student_profile') else 'N/A',
                l.copy.book.title,
                l.copy.accession_number,
                l.issue_date,
                l.due_date,
                l.return_date or 'Active',
                l.status,
                l.deposit_amount,
                l.fine_amount,
                l.refund_due
            ])
        return response

    elif export_type == 'defaulters':
        defaulters = Loan.objects.filter(status='OVERDUE').select_related('student', 'copy__book')
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="defaulters_list_{date.today().strftime("%Y%m%d")}.csv"'
        writer = csv.writer(response)
        writer.writerow(['Receipt', 'Student Name', 'Roll No', 'Phone', 'Email', 'Book Title', 'Accession', 'Due Date', 'Days Overdue', 'Daily Fine Rate', 'Calculated Fine (INR)'])
        for l in defaulters:
            days = (today - l.due_date).days
            writer.writerow([
                l.receipt_number,
                l.student.get_full_name() or l.student.username,
                l.student.student_profile.roll_number if hasattr(l.student, 'student_profile') else 'N/A',
                l.student.student_profile.phone if hasattr(l.student, 'student_profile') else 'N/A',
                l.student.email,
                l.copy.book.title,
                l.copy.accession_number,
                l.due_date,
                days,
                l.daily_fine_rate,
                days * l.daily_fine_rate
            ])
        return response

    # Aggregates
    total_issues = loans.count()
    returned_count = loans.filter(status='RETURNED').count()
    active_in_period = loans.filter(status__in=['ACTIVE', 'OVERDUE']).count()
    total_fines_in_period = loans.filter(status='RETURNED').aggregate(s=Sum('fine_amount'))['s'] or Decimal("0.00")

    # Chart: Top Borrowed Titles
    top_books = (
        Book.objects.filter(copies__loans__issue_date__gte=start_date, copies__loans__issue_date__lte=end_date)
        .annotate(borrow_count=Count('copies__loans'))
        .order_by('-borrow_count')[:7]
    )
    top_books_labels = [b.title[:20] + "..." if len(b.title) > 20 else b.title for b in top_books]
    top_books_data = [b.borrow_count for b in top_books]

    # Chart: Category Borrowings
    cat_stats = (
        Category.objects.filter(books__copies__loans__issue_date__gte=start_date, books__copies__loans__issue_date__lte=end_date)
        .annotate(borrow_count=Count('books__copies__loans'))
        .filter(borrow_count__gt=0)
    )
    cat_labels = [c.name for c in cat_stats]
    cat_data = [c.borrow_count for c in cat_stats]

    return render(request, 'librarian/reports.html', {
        'start_date': start_date,
        'end_date': end_date,
        'total_issues': total_issues,
        'returned_count': returned_count,
        'active_in_period': active_in_period,
        'total_fines_in_period': total_fines_in_period,
        'top_books_labels': top_books_labels,
        'top_books_data': top_books_data,
        'cat_labels': cat_labels,
        'cat_data': cat_data,
    })


@librarian_required
def admin_categories(request):
    """
    Manage academic categories.
    """
    categories = Category.objects.annotate(book_count=Count('books')).order_by('name')

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        slug = request.POST.get('slug', '').strip().lower()
        icon = request.POST.get('icon', 'bi-journal-code').strip()
        description = request.POST.get('description', '').strip()

        if name and slug:
            Category.objects.create(
                name=name,
                slug=slug,
                icon=icon,
                description=description
            )
            record_audit(request, "ADD_CATEGORY", "CATALOGUE", f"Added category '{name}'")
            messages.success(request, f"Category '{name}' created successfully.")
            return redirect('admin_categories')

    return render(request, 'librarian/category_list.html', {
        'categories': categories,
    })


@librarian_required
def admin_settings(request):
    """
    Manage configurable library parameters and operational rules.
    """
    settings_obj = LibrarySettings.get_settings()

    if request.method == 'POST':
        form = LibrarySettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            form.save()
            record_audit(request, "UPDATE_SETTINGS", "SETTINGS", "Updated library operational policy parameters.")
            messages.success(request, "Library settings updated successfully.")
            return redirect('admin_settings')
    else:
        form = LibrarySettingsForm(instance=settings_obj)

    return render(request, 'librarian/settings.html', {
        'form': form,
        'settings': settings_obj,
    })


@librarian_required
def admin_audit_logs(request):
    """
    View permanent system audit trail.
    """
    module = request.GET.get('module', '').strip()
    search = request.GET.get('q', '').strip()

    logs = AuditLog.objects.select_related('user').order_by('-created_at')

    if module:
        logs = logs.filter(module=module)
    if search:
        logs = logs.filter(
            Q(action__icontains=search) |
            Q(details__icontains=search) |
            Q(user__username__icontains=search)
        )

    paginator = Paginator(logs, 30)
    page_obj = paginator.get_page(request.GET.get('page'))

    modules = AuditLog.objects.values_list('module', flat=True).distinct()

    return render(request, 'librarian/audit_logs.html', {
        'page_obj': page_obj,
        'module': module,
        'search': search,
        'modules': modules,
    })


def api_documentation_view(request):
    """
    Renders interactive and nicely styled REST API documentation page.
    """
    return render(request, 'public/api_docs.html')
