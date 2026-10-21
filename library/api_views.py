from decimal import Decimal
from datetime import date, timedelta
from django.db import transaction
from django.db.models import Count, Sum, Q
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework import generics, permissions, status, views
from rest_framework.response import Response

from .models import (
    LibrarySettings, StudentProfile, Category, Book, BookCopy,
    Loan, Reservation, FinancialTransaction, Notification, AuditLog
)
from .serializers import (
    UserSerializer, CategorySerializer, BookSerializer, BookCopySerializer,
    LoanSerializer, ReservationSerializer, FinancialTransactionSerializer,
    NotificationSerializer, LibrarySettingsSerializer
)

class IsLibrarian(permissions.BasePermission):
    """
    Allows access only to staff or librarians.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser))


class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Allows access to object owners or library administrators.
    """
    def has_object_permission(self, request, view, obj):
        if request.user.is_staff or request.user.is_superuser:
            return True
        if hasattr(obj, 'student'):
            return obj.student == request.user
        if hasattr(obj, 'recipient'):
            return obj.recipient == request.user
        if hasattr(obj, 'user'):
            return obj.user == request.user
        return False


class CurrentUserProfileAPI(views.APIView):
    """
    Returns authenticated user's profile and active roles.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)


class BookListAPI(generics.ListCreateAPIView):
    """
    List books with search & category filters. Admin can create new books.
    """
    serializer_class = BookSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsLibrarian()]
        return [permissions.AllowAny()]

    def get_queryset(self):
        qs = Book.objects.filter(is_active=True).select_related('category').prefetch_related('copies')
        q = self.request.query_params.get('search')
        category_slug = self.request.query_params.get('category')
        available_only = self.request.query_params.get('available')

        if q:
            qs = qs.filter(
                Q(title__icontains=q) |
                Q(author__icontains=q) |
                Q(isbn__icontains=q) |
                Q(shelf_location__icontains=q)
            )
        if category_slug:
            qs = qs.filter(category__slug=category_slug)
        if available_only in ['true', '1']:
            qs = [b for b in qs if b.is_available]
        return qs


class BookDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve book details. Admin can update or archive.
    """
    queryset = Book.objects.all().select_related('category').prefetch_related('copies')
    serializer_class = BookSerializer

    def get_permissions(self):
        if self.request.method in ['PUT', 'PATCH', 'DELETE']:
            return [IsLibrarian()]
        return [permissions.AllowAny()]


class BookCopyListCreateAPI(generics.ListCreateAPIView):
    """
    List physical copies or add new copies (Admin only).
    """
    permission_classes = [IsLibrarian]
    serializer_class = BookCopySerializer

    def get_queryset(self):
        qs = BookCopy.objects.all().select_related('book')
        book_id = self.request.query_params.get('book_id')
        status_filter = self.request.query_params.get('status')
        if book_id:
            qs = qs.filter(book_id=book_id)
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs


class StudentListAPI(generics.ListAPIView):
    """
    List student accounts (Admin only).
    """
    permission_classes = [IsLibrarian]
    serializer_class = UserSerializer

    def get_queryset(self):
        return User.objects.filter(is_staff=False).select_related('student_profile').order_by('username')


class LoanListAPI(generics.ListAPIView):
    """
    List loans. Students see their own; Admins see all.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = LoanSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Loan.objects.all().select_related('student', 'copy__book')
        if not (user.is_staff or user.is_superuser):
            qs = qs.filter(student=user)
        
        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param.upper())
        return qs


class IssueBookAPI(views.APIView):
    """
    Issue a physical copy to a student (Admin only).
    """
    permission_classes = [IsLibrarian]

    def post(self, request):
        student_id = request.data.get('student_id')
        accession_number = request.data.get('accession_number')
        payment_mode = request.data.get('payment_mode', 'CASH')
        notes = request.data.get('notes', '')

        if not student_id or not accession_number:
            return Response(
                {'error': "Both student_id and accession_number are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            student = User.objects.get(pk=student_id, is_staff=False)
            copy = BookCopy.objects.select_for_update().get(accession_number=accession_number)
        except User.DoesNotExist:
            return Response({'error': "Student not found."}, status=status.HTTP_404_NOT_FOUND)
        except BookCopy.DoesNotExist:
            return Response({'error': "Copy with this accession number not found."}, status=status.HTTP_404_NOT_FOUND)

        settings = LibrarySettings.get_settings()

        # Check student active loans limit
        active_loans = Loan.objects.filter(student=student, status__in=['ACTIVE', 'OVERDUE']).count()
        max_allowed = student.student_profile.max_books_allowed if hasattr(student, 'student_profile') else settings.max_active_loans
        if active_loans >= max_allowed:
            return Response(
                {'error': f"Student has reached max borrowing limit ({active_loans}/{max_allowed})."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check availability
        if copy.status != 'AVAILABLE':
            # Check if allocated to this student via reservation
            res = Reservation.objects.filter(allocated_copy=copy, student=student, status='READY_FOR_PICKUP').first()
            if not res:
                return Response({'error': f"Copy is currently {copy.get_status_display()}."}, status=status.HTTP_400_BAD_REQUEST)

        # Check reservation priority queue
        pending_res = Reservation.objects.filter(
            book=copy.book, status='APPROVED', allocated_copy__isnull=True
        ).order_by('request_date').first()
        if pending_res and pending_res.student != student:
            return Response(
                {'error': f"A prior approved reservation exists for student {pending_res.student.username}."},
                status=status.HTTP_400_BAD_REQUEST
            )

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
                deposit_amount=settings.deposit_per_loan,
                daily_fine_rate=settings.daily_fine_rate,
                issued_by=request.user,
                notes=notes
            )

            FinancialTransaction.objects.create(
                loan=loan,
                student=student,
                transaction_type='DEPOSIT_COLLECTED',
                amount=loan.deposit_amount,
                payment_mode=payment_mode,
                reference_number=f"TXN-DEP-{timezone.now().strftime('%Y%m%d%H%M%S')}-{student.id}",
                recorded_by=request.user,
                notes="Security deposit collected at counter"
            )

            # If this loan fulfilled a reservation, mark it fulfilled
            res = Reservation.objects.filter(book=copy.book, student=student, status__in=['PENDING', 'APPROVED', 'READY_FOR_PICKUP']).first()
            if res:
                res.status = 'FULFILLED'
                res.fulfilled_at = timezone.now()
                res.save()

            Notification.objects.create(
                recipient=student,
                title="Book Issued",
                message=f"'{copy.book.title}' has been issued to you. Due date: {due_date.strftime('%d-%b-%Y')}.",
                notification_type='BOOK_ISSUED',
                link="/student/loans/"
            )

            AuditLog.objects.create(
                user=request.user,
                action="ISSUE_BOOK",
                module="CIRCULATION",
                details=f"Issued copy {copy.accession_number} to {student.username}. Due: {due_date}."
            )

        return Response(LoanSerializer(loan).data, status=status.HTTP_201_CREATED)


class ReturnBookAPI(views.APIView):
    """
    Return a loan and compute deposit-linked fine settlement (Admin only).
    """
    permission_classes = [IsLibrarian]

    def post(self, request, pk):
        try:
            loan = Loan.objects.get(pk=pk)
        except Loan.DoesNotExist:
            return Response({'error': "Loan not found."}, status=status.HTTP_404_NOT_FOUND)

        if loan.status == 'RETURNED':
            return Response({'error': "Loan has already been returned and settled."}, status=status.HTTP_400_BAD_REQUEST)

        return_date_str = request.data.get('return_date')
        if return_date_str:
            try:
                return_date_val = date.fromisoformat(return_date_str)
            except ValueError:
                return Response({'error': "Invalid date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return_date_val = date.today()

        disburse_refund = request.data.get('disburse_refund', True)
        collect_fine = request.data.get('collect_fine', True)
        notes = request.data.get('notes', '')

        with transaction.atomic():
            loan.execute_return_and_settlement(return_date_val, request.user, notes)

            # Disburse cash refund if applicable
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
                    notes=f"Refund of ₹{loan.refund_due} paid in cash on return."
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
                    notes=f"Outstanding fine of ₹{loan.remaining_fine_due} collected in cash."
                )

        return Response(LoanSerializer(loan).data)


class ReservationListCreateAPI(generics.ListCreateAPIView):
    """
    List reservations or create a new reservation.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ReservationSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Reservation.objects.all().select_related('book', 'student', 'allocated_copy')
        if not (user.is_staff or user.is_superuser):
            qs = qs.filter(student=user)
        return qs

    def create(self, request, *args, **kwargs):
        book_id = request.data.get('book')
        if not book_id:
            return Response({'error': "Book ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            book = Book.objects.get(pk=book_id, is_active=True)
        except Book.DoesNotExist:
            return Response({'error': "Book not found."}, status=status.HTTP_404_NOT_FOUND)

        student = request.user
        if student.is_staff:
            return Response({'error': "Staff cannot reserve books for personal accounts."}, status=status.HTTP_400_BAD_REQUEST)

        # Check duplicate active reservation
        exists = Reservation.objects.filter(
            book=book,
            student=student,
            status__in=['PENDING', 'APPROVED', 'READY_FOR_PICKUP']
        ).exists()
        if exists:
            return Response({'error': "You already have an active reservation for this book."}, status=status.HTTP_400_BAD_REQUEST)

        # Check available copies policy
        settings = LibrarySettings.get_settings()
        if not settings.allow_reserving_available_books and book.is_available:
            return Response(
                {'error': "This book currently has physical copies available on shelf for direct issue. Reservation is only for checked-out titles."},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            res = Reservation.objects.create(
                book=book,
                student=student,
                status='PENDING'
            )
            res.recalculate_queue_position()
            res.save()

            Notification.objects.create(
                recipient=student,
                title="Reservation Requested",
                message=f"Your reservation request for '{book.title}' is queued (Position #{res.queue_position}). You will be alerted when approved.",
                notification_type='GENERAL',
                link="/student/reservations/"
            )

            AuditLog.objects.create(
                user=student,
                action="RESERVE_BOOK",
                module="RESERVATIONS",
                details=f"Student {student.username} requested reservation for '{book.title}'."
            )

        return Response(ReservationSerializer(res).data, status=status.HTTP_201_CREATED)


class FinancialTransactionListAPI(generics.ListAPIView):
    """
    List financial transactions (Students see own; Admin sees all).
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = FinancialTransactionSerializer

    def get_queryset(self):
        user = self.request.user
        qs = FinancialTransaction.objects.all().select_related('student', 'loan')
        if not (user.is_staff or user.is_superuser):
            qs = qs.filter(student=user)
        return qs


class NotificationListAPI(generics.ListAPIView):
    """
    List authenticated user's notifications.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user).order_by('-created_at')


class DashboardStatsAPI(views.APIView):
    """
    Returns real-time computed statistics and Chart.js datasets.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        today = date.today()

        if user.is_staff or user.is_superuser:
            # Admin metrics
            total_titles = Book.objects.filter(is_active=True).count()
            total_copies = BookCopy.objects.count()
            available_copies = BookCopy.objects.filter(status='AVAILABLE', condition__in=['NEW', 'GOOD', 'FAIR']).count()
            active_students = StudentProfile.objects.filter(is_membership_active=True).count()
            active_loans = Loan.objects.filter(status='ACTIVE').count()
            overdue_loans = Loan.objects.filter(status='OVERDUE').count()
            pending_reservations = Reservation.objects.filter(status__in=['PENDING', 'APPROVED']).count()
            
            # Financial metrics
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

            # Chart 1: Most borrowed titles
            top_books = (
                Book.objects.annotate(loan_count=Count('copies__loans'))
                .order_by('-loan_count')[:6]
                .values('title', 'loan_count')
            )

            # Chart 2: Borrowings by Category
            cat_stats = (
                Category.objects.annotate(loan_count=Count('books__copies__loans'))
                .values('name', 'loan_count')
            )

            # Chart 3: Copy inventory by status
            copy_statuses = (
                BookCopy.objects.values('status')
                .annotate(count=Count('id'))
            )

            return Response({
                'role': 'admin',
                'total_titles': total_titles,
                'total_copies': total_copies,
                'available_copies': available_copies,
                'active_students': active_students,
                'active_loans': active_loans,
                'overdue_loans': overdue_loans,
                'pending_reservations': pending_reservations,
                'deposits_held': float(deposits_held),
                'fines_assessed': float(fines_assessed),
                'fines_collected': float(fines_collected),
                'refunds_pending': float(refunds_pending),
                'charts': {
                    'top_books': list(top_books),
                    'category_distribution': list(cat_stats),
                    'copy_statuses': list(copy_statuses),
                }
            })
        else:
            # Student metrics
            active_loans = Loan.objects.filter(student=user, status__in=['ACTIVE', 'OVERDUE']).count()
            overdue_loans = Loan.objects.filter(student=user, status='OVERDUE').count()
            active_reservations = Reservation.objects.filter(student=user, status__in=['PENDING', 'APPROVED', 'READY_FOR_PICKUP']).count()
            
            deposits_held = Loan.objects.filter(student=user, status__in=['ACTIVE', 'OVERDUE']).aggregate(s=Sum('deposit_amount'))['s'] or Decimal("0.00")
            outstanding_fines = Loan.objects.filter(student=user, status='RETURNED', fine_status='PARTIALLY_SETTLED').aggregate(s=Sum('remaining_fine_due'))['s'] or Decimal("0.00")
            refunds_due = (
                (Loan.objects.filter(student=user, status='RETURNED', refund_status='PENDING').aggregate(s=Sum('refund_due'))['s'] or Decimal("0.00")) -
                (Loan.objects.filter(student=user, status='RETURNED', refund_status='PENDING').aggregate(s=Sum('refund_paid'))['s'] or Decimal("0.00"))
            )

            upcoming_dues = (
                Loan.objects.filter(student=user, status='ACTIVE')
                .order_by('due_date')[:5]
                .values('id', 'receipt_number', 'due_date', 'copy__book__title', 'copy__accession_number')
            )

            return Response({
                'role': 'student',
                'active_loans': active_loans,
                'overdue_loans': overdue_loans,
                'active_reservations': active_reservations,
                'deposits_held': float(deposits_held),
                'outstanding_fines': float(outstanding_fines),
                'refunds_due': float(refunds_due),
                'upcoming_dues': list(upcoming_dues),
            })
