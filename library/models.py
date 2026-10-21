import uuid
from decimal import Decimal
from datetime import date, datetime, timedelta
from django.db import models, transaction
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.exceptions import ValidationError


class LibrarySettings(models.Model):
    """
    Singleton model for configurable library operational rules and policy parameters.
    """
    institution_name = models.CharField(max_length=200, default="ASM Nextgen Technical Campus")
    department_name = models.CharField(max_length=200, default="Department of Computer Science")
    academic_year = models.CharField(max_length=50, default="2025–2026")
    
    loan_period_days = models.PositiveIntegerField(
        default=14, 
        help_text="Standard loan duration in calendar days"
    )
    daily_fine_rate = models.DecimalField(
        max_digits=8, 
        decimal_places=2, 
        default=Decimal("5.00"), 
        help_text="Daily overdue penalty in INR (₹)"
    )
    deposit_per_loan = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal("500.00"), 
        help_text="Refundable security deposit required per borrowed copy in INR (₹)"
    )
    max_active_loans = models.PositiveIntegerField(
        default=3, 
        help_text="Maximum concurrent active loans per student"
    )
    reservation_pickup_hours = models.PositiveIntegerField(
        default=48, 
        help_text="Pickup hold period once copy becomes ready for pickup"
    )
    allow_student_registration = models.BooleanField(
        default=True, 
        help_text="Allow students to register self-service accounts"
    )
    allow_reserving_available_books = models.BooleanField(
        default=False, 
        help_text="Allow reserving titles that currently have available copies on shelf"
    )
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_settings(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return f"{self.institution_name} - Policy Settings ({self.academic_year})"

    class Meta:
        verbose_name = "Library Settings"
        verbose_name_plural = "Library Settings"


class StudentProfile(models.Model):
    """
    Extends Django User model with student-specific academic information.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    roll_number = models.CharField(max_length=30, unique=True, help_text="e.g. SCS101")
    department = models.CharField(max_length=150, default="Department of Computer Science")
    academic_year = models.CharField(max_length=30, default="2025–2026")
    semester = models.CharField(max_length=50, default="6th Semester")
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    max_books_allowed = models.PositiveIntegerField(default=3)
    is_membership_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.roll_number})"

    @property
    def active_loans_count(self):
        return self.user.loans.filter(status__in=['ACTIVE', 'OVERDUE']).count()

    @property
    def outstanding_fine_balance(self):
        unpaid = self.user.loans.filter(status='RETURNED', fine_status='PARTIALLY_SETTLED')
        return sum(loan.remaining_fine_due for loan in unpaid)

    @property
    def deposits_currently_held(self):
        active = self.user.loans.filter(status__in=['ACTIVE', 'OVERDUE'])
        return sum(loan.deposit_amount for loan in active)

    @property
    def refunds_pending_payment(self):
        loans = self.user.loans.filter(status='RETURNED', refund_status='PENDING')
        return sum(loan.refund_due - loan.refund_paid for loan in loans)


class Category(models.Model):
    """
    Book classification category (e.g. Artificial Intelligence, Database Systems).
    """
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=60, default="bi-journal-code", help_text="Bootstrap Icons class name")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']


class Book(models.Model):
    """
    Bibliographic record of a book title. Physical copies are tracked in BookCopy.
    """
    title = models.CharField(max_length=255, db_index=True)
    author = models.CharField(max_length=255, db_index=True)
    isbn = models.CharField(max_length=30, unique=True, db_index=True)
    publisher = models.CharField(max_length=255, blank=True)
    edition = models.CharField(max_length=60, blank=True)
    publication_year = models.PositiveIntegerField(null=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='books')
    shelf_location = models.CharField(max_length=100, help_text="Primary shelf reference, e.g. CS-RACK-04")
    description = models.TextField(blank=True)
    cover_image = models.ImageField(upload_to='book_covers/', blank=True, null=True)
    is_active = models.BooleanField(default=True, help_text="Active in catalogue or archived")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} by {self.author}"

    class Meta:
        ordering = ['title']

    @property
    def total_copies_count(self):
        return self.copies.count()

    @property
    def available_copies_count(self):
        return self.copies.filter(status='AVAILABLE', condition__in=['NEW', 'GOOD', 'FAIR']).count()

    @property
    def on_loan_copies_count(self):
        return self.copies.filter(status='ON_LOAN').count()

    @property
    def reserved_copies_count(self):
        return self.copies.filter(status='RESERVED').count()

    @property
    def active_reservations_count(self):
        return self.reservations.filter(status__in=['PENDING', 'APPROVED', 'READY_FOR_PICKUP']).count()

    @property
    def is_available(self):
        return self.available_copies_count > 0


class BookCopy(models.Model):
    """
    Physical unit of a book with accession barcode, shelf location, and condition.
    """
    CONDITION_CHOICES = [
        ('NEW', 'New / Pristine'),
        ('GOOD', 'Good'),
        ('FAIR', 'Fair / Usable'),
        ('DAMAGED', 'Damaged'),
        ('LOST', 'Lost / Written Off'),
    ]

    STATUS_CHOICES = [
        ('AVAILABLE', 'Available on Shelf'),
        ('ON_LOAN', 'On Loan'),
        ('RESERVED', 'Reserved (Ready for Pickup)'),
        ('MAINTENANCE', 'In Maintenance / Repair'),
        ('LOST', 'Lost'),
    ]

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='copies')
    accession_number = models.CharField(max_length=50, unique=True, db_index=True, help_text="Unique accession number or barcode")
    shelf_location = models.CharField(max_length=100, blank=True)
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default='GOOD')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='AVAILABLE')
    added_date = models.DateField(auto_now_add=True)
    notes = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        if not self.shelf_location and self.book and self.book.shelf_location:
            self.shelf_location = self.book.shelf_location
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.accession_number} - {self.book.title} ({self.get_status_display()})"

    class Meta:
        verbose_name_plural = "Book Copies"
        ordering = ['accession_number']


class Loan(models.Model):
    """
    Tracks circulation of a physical copy to a student, security deposit,
    due date calculation, and automatic deposit-linked fine settlement.
    """
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('RETURNED', 'Returned'),
        ('OVERDUE', 'Overdue'),
    ]

    REFUND_STATUS_CHOICES = [
        ('NONE', 'Not Applicable'),
        ('PENDING', 'Pending Cash/Manual Refund'),
        ('PAID', 'Refund Disbursed'),
    ]

    FINE_STATUS_CHOICES = [
        ('NONE', 'No Fine Assessed'),
        ('SETTLED_FROM_DEPOSIT', 'Settled Fully from Deposit'),
        ('PARTIALLY_SETTLED', 'Deposit Exhausted, Outstanding Due'),
        ('FULLY_PAID', 'Fully Paid'),
    ]

    copy = models.ForeignKey(BookCopy, on_delete=models.PROTECT, related_name='loans')
    student = models.ForeignKey(User, on_delete=models.PROTECT, related_name='loans')
    issue_date = models.DateField(default=date.today)
    due_date = models.DateField()
    return_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    
    # Financial terms snapshotted at time of issue to ensure future policy edits
    # never modify terms of existing loans:
    deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("500.00"))
    daily_fine_rate = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("5.00"))

    # Settlement fields computed on return:
    overdue_days = models.PositiveIntegerField(default=0)
    fine_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), help_text="Total fine assessed")
    deposit_applied = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), help_text="Amount deducted from deposit towards fine")
    refund_due = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), help_text="Max(0, deposit - fine)")
    refund_paid = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), help_text="Actual cash refund disbursed to student")
    refund_status = models.CharField(max_length=20, choices=REFUND_STATUS_CHOICES, default='NONE')
    remaining_fine_due = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), help_text="Max(0, fine - deposit)")
    fine_collected = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), help_text="Cash fine collected for remaining balance")
    fine_status = models.CharField(max_length=30, choices=FINE_STATUS_CHOICES, default='NONE')

    issued_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='loans_issued')
    returned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='loans_received')
    receipt_number = models.CharField(max_length=64, unique=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Loan #{self.receipt_number} - {self.copy.accession_number} to {self.student.username}"

    class Meta:
        ordering = ['-issue_date', '-id']
        constraints = [
            # Ensure physical copy has at most 1 active/overdue loan at any moment
            models.UniqueConstraint(
                fields=['copy'],
                condition=models.Q(status__in=['ACTIVE', 'OVERDUE']),
                name='unique_active_loan_per_copy'
            )
        ]

    def save(self, *args, **kwargs):
        if not self.receipt_number:
            self.receipt_number = f"LN-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)

    @classmethod
    def calculate_settlement(cls, issue_date_val, due_date_val, return_date_val, deposit_val, fine_rate_val):
        """
        Pure calculation method for deposit-linked fine settlement.
        """
        deposit_val = Decimal(str(deposit_val))
        fine_rate_val = Decimal(str(fine_rate_val))
        
        # A book returned on or before its due date has no overdue fine
        if return_date_val <= due_date_val:
            overdue_days = 0
            fine_amount = Decimal("0.00")
        else:
            overdue_days = (return_date_val - due_date_val).days
            fine_amount = Decimal(overdue_days) * fine_rate_val

        deposit_applied = min(deposit_val, fine_amount)
        refund_due = max(Decimal("0.00"), deposit_val - fine_amount)
        remaining_fine_due = max(Decimal("0.00"), fine_amount - deposit_val)

        return {
            'overdue_days': overdue_days,
            'fine_amount': fine_amount,
            'deposit_applied': deposit_applied,
            'refund_due': refund_due,
            'remaining_fine_due': remaining_fine_due,
        }

    def execute_return_and_settlement(self, return_date_val, processed_by_user, notes=""):
        """
        Executes return of book, calculates fine and deposit allocation,
        updates physical copy status (or allocates to waiting reservation),
        and records financial transactions atomically.
        """
        if self.status == 'RETURNED':
            raise ValidationError("This loan has already been returned and settled.")

        with transaction.atomic():
            # Refresh and lock row
            loan = Loan.objects.select_for_update().get(pk=self.pk)
            copy = BookCopy.objects.select_for_update().get(pk=loan.copy.pk)

            calc = Loan.calculate_settlement(
                loan.issue_date,
                loan.due_date,
                return_date_val,
                loan.deposit_amount,
                loan.daily_fine_rate
            )

            loan.return_date = return_date_val
            loan.status = 'RETURNED'
            loan.returned_by = processed_by_user
            loan.overdue_days = calc['overdue_days']
            loan.fine_amount = calc['fine_amount']
            loan.deposit_applied = calc['deposit_applied']
            loan.refund_due = calc['refund_due']
            loan.remaining_fine_due = calc['remaining_fine_due']

            # Determine refund status
            if loan.refund_due > Decimal("0.00"):
                loan.refund_status = 'PENDING'
            else:
                loan.refund_status = 'NONE'

            # Determine fine status
            if loan.fine_amount == Decimal("0.00"):
                loan.fine_status = 'NONE'
            elif loan.remaining_fine_due == Decimal("0.00"):
                loan.fine_status = 'SETTLED_FROM_DEPOSIT'
            else:
                loan.fine_status = 'PARTIALLY_SETTLED'

            if notes:
                loan.notes = (loan.notes + "\n" + notes).strip()

            loan.save()
            self.refresh_from_db()

            # Record financial transaction if fine was deducted from deposit
            if loan.deposit_applied > Decimal("0.00"):
                FinancialTransaction.objects.create(
                    loan=loan,
                    student=loan.student,
                    transaction_type='FINE_DEDUCTED',
                    amount=loan.deposit_applied,
                    payment_mode='DEPOSIT_OFFSET',
                    reference_number=f"TXN-FINE-{uuid.uuid4().hex[:8].upper()}",
                    recorded_by=processed_by_user,
                    notes=f"Overdue fine of ₹{loan.deposit_applied} deducted from deposit for Loan #{loan.receipt_number}"
                )

            # Check FIFO reservation queue for this book title
            next_reservation = Reservation.objects.filter(
                book=copy.book,
                status='APPROVED',
                allocated_copy__isnull=True
            ).order_by('request_date').first()

            settings = LibrarySettings.get_settings()

            if next_reservation:
                # Allocate copy directly to next waiting student
                copy.status = 'RESERVED'
                copy.save()

                pickup_deadline = timezone.now() + timedelta(hours=settings.reservation_pickup_hours)
                next_reservation.status = 'READY_FOR_PICKUP'
                next_reservation.allocated_copy = copy
                next_reservation.pickup_deadline = pickup_deadline
                next_reservation.notification_sent = True
                next_reservation.save()

                Notification.objects.create(
                    recipient=next_reservation.student,
                    title="Book Ready for Pickup!",
                    message=f"The book '{copy.book.title}' is now ready for pickup. Please visit the library before {pickup_deadline.strftime('%d-%b-%Y %I:%M %p')}.",
                    notification_type='RESERVATION_READY',
                    link="/student/reservations/"
                )

                AuditLog.objects.create(
                    user=processed_by_user,
                    action="ALLOCATE_RESERVATION",
                    module="RESERVATIONS",
                    details=f"Copy {copy.accession_number} allocated to reservation #{next_reservation.id} for {next_reservation.student.username} until {pickup_deadline}."
                )
            else:
                # No waiting reservations; mark available
                copy.status = 'AVAILABLE'
                copy.save()

            # Send settlement notification to returning student
            Notification.objects.create(
                recipient=loan.student,
                title="Book Return Settled",
                message=f"Loan #{loan.receipt_number} for '{copy.book.title}' has been returned. Overdue: {loan.overdue_days} days. Fine: ₹{loan.fine_amount}. Refund Due: ₹{loan.refund_due}.",
                notification_type='RETURN_SETTLED',
                link="/student/loans/"
            )

            AuditLog.objects.create(
                user=processed_by_user,
                action="RETURN_BOOK",
                module="CIRCULATION",
                details=f"Returned Copy {copy.accession_number}. Fine: ₹{loan.fine_amount}, Refund Due: ₹{loan.refund_due}."
            )

            return loan


class Reservation(models.Model):
    """
    FIFO reservation queue for books currently checked out or requested by students.
    """
    STATUS_CHOICES = [
        ('PENDING', 'Pending Approval'),
        ('APPROVED', 'Approved (Waiting in Queue)'),
        ('READY_FOR_PICKUP', 'Ready for Pickup'),
        ('FULFILLED', 'Fulfilled (Book Issued)'),
        ('CANCELLED', 'Cancelled by User/Admin'),
        ('EXPIRED', 'Expired (Pickup Deadline Passed)'),
    ]

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='reservations')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reservations')
    allocated_copy = models.ForeignKey(BookCopy, on_delete=models.SET_NULL, null=True, blank=True, related_name='allocated_reservations')
    request_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='PENDING')
    queue_position = models.PositiveIntegerField(default=1)
    pickup_deadline = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reservations_approved')
    notification_sent = models.BooleanField(default=False)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    fulfilled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Reservation #{self.id} - {self.book.title} by {self.student.username} ({self.get_status_display()})"

    class Meta:
        ordering = ['request_date']
        constraints = [
            # Prevent duplicate active reservations for the same book by the same student
            models.UniqueConstraint(
                fields=['book', 'student'],
                condition=models.Q(status__in=['PENDING', 'APPROVED', 'READY_FOR_PICKUP']),
                name='unique_active_reservation_per_student_book'
            )
        ]

    def recalculate_queue_position(self):
        """
        Computes accurate FIFO position among approved reservations for the same book.
        """
        if self.status in ['APPROVED', 'PENDING']:
            earlier = Reservation.objects.filter(
                book=self.book,
                status__in=['PENDING', 'APPROVED'],
                request_date__lt=self.request_date
            ).count()
            self.queue_position = earlier + 1
            return self.queue_position
        return 0


class FinancialTransaction(models.Model):
    """
    Auditable ledger recording security deposits collected, fine deductions,
    cash refunds disbursed, and extra overdue fine payments.
    """
    TRANSACTION_TYPES = [
        ('DEPOSIT_COLLECTED', 'Security Deposit Collected'),
        ('FINE_DEDUCTED', 'Fine Deducted from Deposit'),
        ('REFUND_ISSUED', 'Refund Paid to Student'),
        ('FINE_COLLECTED_CASH', 'Outstanding Fine Paid (Cash/UPI)'),
    ]

    PAYMENT_MODES = [
        ('CASH', 'Cash'),
        ('UPI', 'UPI / Online Transfer'),
        ('DEPOSIT_OFFSET', 'Internal Offset Against Deposit'),
    ]

    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, null=True, blank=True, related_name='financial_transactions')
    student = models.ForeignKey(User, on_delete=models.PROTECT, related_name='financial_transactions')
    transaction_type = models.CharField(max_length=30, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_mode = models.CharField(max_length=20, choices=PAYMENT_MODES, default='CASH')
    reference_number = models.CharField(max_length=64, unique=True)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions_recorded')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.reference_number} - {self.get_transaction_type_display()} - ₹{self.amount}"

    class Meta:
        ordering = ['-created_at']


class Notification(models.Model):
    """
    Persistent in-app notification for library events.
    """
    NOTIFICATION_TYPES = [
        ('BOOK_ISSUED', 'Book Issued'),
        ('DUE_SOON', 'Due Date Approaching'),
        ('OVERDUE', 'Loan Overdue'),
        ('RESERVATION_APPROVED', 'Reservation Approved'),
        ('RESERVATION_READY', 'Ready for Pickup'),
        ('RESERVATION_EXPIRED', 'Reservation Expired'),
        ('RETURN_SETTLED', 'Loan Returned & Settled'),
        ('GENERAL', 'General Notice'),
    ]

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPES, default='GENERAL')
    is_read = models.BooleanField(default=False)
    link = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"To: {self.recipient.username} - {self.title}"

    class Meta:
        ordering = ['-created_at']


class AuditLog(models.Model):
    """
    Permanent audit log capturing administrative actions and security events.
    """
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    action = models.CharField(max_length=100)
    module = models.CharField(max_length=50)
    details = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {self.action} by {self.user.username if self.user else 'System'}"

    class Meta:
        ordering = ['-created_at']
