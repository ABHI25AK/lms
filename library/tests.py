from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.core.management import call_command

from .models import (
    LibrarySettings, StudentProfile, Category, Book, BookCopy,
    Loan, Reservation, FinancialTransaction, Notification, AuditLog
)

class LibraryManagementSystemTests(TestCase):
    """
    Automated test suite verifying authentication, permissions, privacy,
    copy availability, issue/return workflows, deposit-linked settlements,
    FIFO reservation queues, and loan term preservation.
    """

    def setUp(self):
        # 1. Base Settings
        self.settings = LibrarySettings.get_settings()
        self.settings.loan_period_days = 14
        self.settings.daily_fine_rate = Decimal("5.00")
        self.settings.deposit_per_loan = Decimal("500.00")
        self.settings.max_active_loans = 3
        self.settings.reservation_pickup_hours = 48
        self.settings.save()

        # 2. Staff / Admin User
        self.admin_user = User.objects.create_user(
            username='admin_staff',
            password='password123',
            email='admin@asmnextgen.ac.in',
            is_staff=True,
            is_superuser=True
        )

        # 3. Student Users
        self.student1 = User.objects.create_user(
            username='abhishek',
            password='password123',
            email='scs101@asmnextgen.ac.in'
        )
        self.profile1 = StudentProfile.objects.create(
            user=self.student1,
            roll_number='SCS101',
            department='Department of Computer Science',
            max_books_allowed=3
        )

        self.student2 = User.objects.create_user(
            username='kunal',
            password='password123',
            email='scs104@asmnextgen.ac.in'
        )
        self.profile2 = StudentProfile.objects.create(
            user=self.student2,
            roll_number='SCS104',
            department='Department of Computer Science',
            max_books_allowed=3
        )

        # 4. Category & Book Title
        self.cat = Category.objects.create(
            name="Algorithms & Data Structures",
            slug="algorithms-ds"
        )
        self.book = Book.objects.create(
            title="Introduction to Algorithms (CLRS)",
            author="Thomas H. Cormen",
            isbn="978-0262033848",
            category=self.cat,
            shelf_location="CS-RACK-A1",
            is_active=True
        )

        # 5. Physical Copies
        self.copy1 = BookCopy.objects.create(
            book=self.book,
            accession_number="CS-2025-001",
            shelf_location="CS-RACK-A1-C1",
            condition="NEW",
            status="AVAILABLE"
        )
        self.copy2 = BookCopy.objects.create(
            book=self.book,
            accession_number="CS-2025-002",
            shelf_location="CS-RACK-A1-C2",
            condition="GOOD",
            status="AVAILABLE"
        )

        self.client = Client()

    # =========================================================================
    # 1. AUTHENTICATION & ROLE PERMISSIONS
    # =========================================================================

    def test_role_based_dashboard_access(self):
        """Admin can access admin dashboard; Student is forbidden/redirected."""
        # Unauthenticated redirects to login
        response = self.client.get(reverse('librarian_dashboard'))
        self.assertEqual(response.status_code, 302)

        # Student login -> cannot access librarian dashboard
        self.client.login(username='abhishek', password='password123')
        response = self.client.get(reverse('librarian_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('student_dashboard'))

        # Student accesses student dashboard -> 200 OK
        response = self.client.get(reverse('student_dashboard'))
        self.assertEqual(response.status_code, 200)

        # Admin login -> accesses librarian dashboard -> 200 OK
        self.client.login(username='admin_staff', password='password123')
        response = self.client.get(reverse('librarian_dashboard'))
        self.assertEqual(response.status_code, 200)

    # =========================================================================
    # 2. STUDENT RECORD PRIVACY
    # =========================================================================

    def test_student_record_privacy(self):
        """Student A must never view Student B's loan receipt or personal records."""
        today = date.today()
        # Create loan for Student 1
        loan1 = Loan.objects.create(
            copy=self.copy1,
            student=self.student1,
            issue_date=today,
            due_date=today + timedelta(days=14),
            status='ACTIVE',
            deposit_amount=Decimal("500.00"),
            receipt_number="LN-PRIVACY-001"
        )

        # Log in as Student 2
        self.client.login(username='kunal', password='password123')

        # Student 2 tries to access Student 1's loan receipt
        response = self.client.get(reverse('loan_receipt', kwargs={'receipt_number': loan1.receipt_number}))
        # Must be redirected with permission error
        self.assertRedirects(response, reverse('student_loans'))

        # Log in as Student 1 (owner) -> accesses receipt 200 OK
        self.client.login(username='abhishek', password='password123')
        response = self.client.get(reverse('loan_receipt', kwargs={'receipt_number': loan1.receipt_number}))
        self.assertEqual(response.status_code, 200)

    # =========================================================================
    # 3. BOOK SEARCH AND AVAILABILITY
    # =========================================================================

    def test_book_search_and_dynamic_availability(self):
        """Availability must strictly reflect physical copy statuses without drift."""
        self.assertEqual(self.book.total_copies_count, 2)
        self.assertEqual(self.book.available_copies_count, 2)
        self.assertTrue(self.book.is_available)

        # Issue one copy
        self.copy1.status = 'ON_LOAN'
        self.copy1.save()

        # Dynamic availability updates automatically
        self.book.refresh_from_db()
        self.assertEqual(self.book.total_copies_count, 2)
        self.assertEqual(self.book.available_copies_count, 1)

        # Search by ISBN and Title
        response = self.client.get(reverse('catalogue'), {'q': 'CLRS'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Introduction to Algorithms (CLRS)")

        response = self.client.get(reverse('catalogue'), {'q': '978-0262033848'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Introduction to Algorithms (CLRS)")

    # =========================================================================
    # 4. ISSUE WORKFLOW AND DUPLICATE PREVENTION
    # =========================================================================

    def test_issue_workflow_and_duplicate_prevention(self):
        """A physical copy cannot have more than one active loan simultaneously."""
        today = date.today()
        due_date = today + timedelta(days=14)

        # Initial successful loan
        loan = Loan.objects.create(
            copy=self.copy1,
            student=self.student1,
            issue_date=today,
            due_date=due_date,
            status='ACTIVE',
            deposit_amount=Decimal("500.00"),
            receipt_number="LN-TEST-001"
        )
        self.copy1.status = 'ON_LOAN'
        self.copy1.save()

        # Attempting to create a second concurrent active loan on the same physical copy
        with self.assertRaises(IntegrityError):
            Loan.objects.create(
                copy=self.copy1,
                student=self.student2,
                issue_date=today,
                due_date=due_date,
                status='ACTIVE',
                deposit_amount=Decimal("500.00"),
                receipt_number="LN-TEST-002"
            )

    # =========================================================================
    # 5. DEPOSIT-LINKED FINE SETTLEMENT: RETURN ON DUE DATE
    # =========================================================================

    def test_return_on_due_date_zero_fine(self):
        """A book returned on its due date has no overdue fine (overdue_days = 0, fine = 0, full refund)."""
        today = date.today()
        due_date = today

        calc = Loan.calculate_settlement(
            issue_date_val=today - timedelta(days=14),
            due_date_val=due_date,
            return_date_val=due_date,
            deposit_val=Decimal("500.00"),
            fine_rate_val=Decimal("5.00")
        )

        self.assertEqual(calc['overdue_days'], 0)
        self.assertEqual(calc['fine_amount'], Decimal("0.00"))
        self.assertEqual(calc['deposit_applied'], Decimal("0.00"))
        self.assertEqual(calc['refund_due'], Decimal("500.00"))
        self.assertEqual(calc['remaining_fine_due'], Decimal("0.00"))

    # =========================================================================
    # 6. DEPOSIT-LINKED FINE SETTLEMENT: FINE SMALLER THAN DEPOSIT
    # =========================================================================

    def test_return_fine_smaller_than_deposit(self):
        """Example from requirements: 4 days late, fine = ₹20, deposit applied = ₹20, refund due = ₹480."""
        today = date.today()
        due_date = today - timedelta(days=4)
        return_date = today

        calc = Loan.calculate_settlement(
            issue_date_val=due_date - timedelta(days=14),
            due_date_val=due_date,
            return_date_val=return_date,
            deposit_val=Decimal("500.00"),
            fine_rate_val=Decimal("5.00")
        )

        self.assertEqual(calc['overdue_days'], 4)
        self.assertEqual(calc['fine_amount'], Decimal("20.00"))
        self.assertEqual(calc['deposit_applied'], Decimal("20.00"))
        self.assertEqual(calc['refund_due'], Decimal("480.00"))
        self.assertEqual(calc['remaining_fine_due'], Decimal("0.00"))

    # =========================================================================
    # 7. DEPOSIT-LINKED FINE SETTLEMENT: FINE GREATER THAN DEPOSIT
    # =========================================================================

    def test_return_fine_greater_than_deposit(self):
        """110 days late: fine = 110 * 5 = ₹550. Deposit applied = ₹500, refund = 0, remaining fine = ₹50."""
        today = date.today()
        due_date = today - timedelta(days=110)
        return_date = today

        calc = Loan.calculate_settlement(
            issue_date_val=due_date - timedelta(days=14),
            due_date_val=due_date,
            return_date_val=return_date,
            deposit_val=Decimal("500.00"),
            fine_rate_val=Decimal("5.00")
        )

        self.assertEqual(calc['overdue_days'], 110)
        self.assertEqual(calc['fine_amount'], Decimal("550.00"))
        self.assertEqual(calc['deposit_applied'], Decimal("500.00"))
        self.assertEqual(calc['refund_due'], Decimal("0.00"))
        self.assertEqual(calc['remaining_fine_due'], Decimal("50.00"))

    # =========================================================================
    # 8. DUPLICATE RETURN AND SETTLEMENT PREVENTION
    # =========================================================================

    def test_duplicate_return_prevention(self):
        """Executing return_and_settlement on an already returned loan must raise a ValidationError."""
        today = date.today()
        loan = Loan.objects.create(
            copy=self.copy1,
            student=self.student1,
            issue_date=today - timedelta(days=14),
            due_date=today,
            status='ACTIVE',
            deposit_amount=Decimal("500.00"),
            receipt_number="LN-DUP-001"
        )
        self.copy1.status = 'ON_LOAN'
        self.copy1.save()

        # First return succeeds
        loan.execute_return_and_settlement(today, self.admin_user)
        self.assertEqual(loan.status, 'RETURNED')
        self.assertEqual(loan.copy.status, 'AVAILABLE')

        # Second return on same loan must raise ValidationError
        with self.assertRaises(ValidationError):
            loan.execute_return_and_settlement(today, self.admin_user)

    # =========================================================================
    # 9. RESERVATION QUEUE ORDERING AND EXPIRATION
    # =========================================================================

    def test_reservation_queue_ordering_and_expiration(self):
        """FIFO queue positions are ordered by request date. Expired reservations advance to next student."""
        # Student 1 reserves book
        res1 = Reservation.objects.create(
            book=self.book,
            student=self.student1,
            status='APPROVED'
        )
        # Student 2 reserves book afterwards
        res2 = Reservation.objects.create(
            book=self.book,
            student=self.student2,
            status='APPROVED'
        )

        self.assertEqual(res1.recalculate_queue_position(), 1)
        self.assertEqual(res2.recalculate_queue_position(), 2)

        # Allocate copy to Student 1
        self.copy1.status = 'RESERVED'
        self.copy1.save()
        res1.status = 'READY_FOR_PICKUP'
        res1.allocated_copy = self.copy1
        # Set pickup deadline in the past to simulate expiration
        res1.pickup_deadline = timezone.now() - timedelta(hours=2)
        res1.save()

        # Run scheduled reminder & expiration command
        call_command('process_library_reminders')

        # Res 1 should now be EXPIRED
        res1.refresh_from_db()
        self.assertEqual(res1.status, 'EXPIRED')
        self.assertIsNone(res1.allocated_copy)

        # Res 2 should now be advanced to READY_FOR_PICKUP with copy1 allocated!
        res2.refresh_from_db()
        self.assertEqual(res2.status, 'READY_FOR_PICKUP')
        self.assertEqual(res2.allocated_copy, self.copy1)

    # =========================================================================
    # 10. POLICY CHANGES DO NOT ALTER EXISTING LOAN TERMS
    # =========================================================================

    def test_policy_change_does_not_alter_existing_loans(self):
        """Snapshot policy preservation: later settings changes do not silently alter existing loan terms."""
        today = date.today()
        # Initial loan created with fine rate ₹5 and deposit ₹500
        loan = Loan.objects.create(
            copy=self.copy1,
            student=self.student1,
            issue_date=today - timedelta(days=20),
            due_date=today - timedelta(days=6),
            status='ACTIVE',
            deposit_amount=self.settings.deposit_per_loan, # ₹500
            daily_fine_rate=self.settings.daily_fine_rate, # ₹5
            receipt_number="LN-POLICY-001"
        )
        self.copy1.status = 'ON_LOAN'
        self.copy1.save()

        # Now, library admin changes global policy: fine increases to ₹25, deposit increases to ₹1000
        self.settings.daily_fine_rate = Decimal("25.00")
        self.settings.deposit_per_loan = Decimal("1000.00")
        self.settings.save()

        # Process return for the existing loan
        loan.execute_return_and_settlement(today, self.admin_user)

        # Loan must be settled according to its snapshotted rate (₹5/day * 6 days = ₹30 fine), NOT ₹25/day!
        self.assertEqual(loan.daily_fine_rate, Decimal("5.00"))
        self.assertEqual(loan.overdue_days, 6)
        self.assertEqual(loan.fine_amount, Decimal("30.00"))
        self.assertEqual(loan.deposit_applied, Decimal("30.00"))
        self.assertEqual(loan.refund_due, Decimal("470.00")) # 500 - 30
