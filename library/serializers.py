from decimal import Decimal
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    LibrarySettings, StudentProfile, Category, Book, BookCopy,
    Loan, Reservation, FinancialTransaction, Notification
)

class StudentProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentProfile
        fields = [
            'roll_number', 'department', 'academic_year', 'semester',
            'phone', 'address', 'max_books_allowed', 'is_membership_active',
            'active_loans_count', 'outstanding_fine_balance',
            'deposits_currently_held', 'refunds_pending_payment'
        ]


class UserSerializer(serializers.ModelSerializer):
    student_profile = StudentProfileSerializer(read_only=True)
    role = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'is_staff', 'role', 'student_profile']

    def get_role(self, obj):
        if obj.is_superuser or obj.is_staff:
            return "Librarian / Administrator"
        return "Student"


class CategorySerializer(serializers.ModelSerializer):
    books_count = serializers.IntegerField(source='books.count', read_only=True)

    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'description', 'icon', 'books_count']


class BookCopySerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    condition_display = serializers.CharField(source='get_condition_display', read_only=True)
    book_title = serializers.CharField(source='book.title', read_only=True)

    class Meta:
        model = BookCopy
        fields = [
            'id', 'book', 'book_title', 'accession_number',
            'shelf_location', 'condition', 'condition_display',
            'status', 'status_display', 'added_date', 'notes'
        ]


class BookSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    total_copies = serializers.IntegerField(source='total_copies_count', read_only=True)
    available_copies = serializers.IntegerField(source='available_copies_count', read_only=True)
    is_available = serializers.BooleanField(read_only=True)
    copies = BookCopySerializer(many=True, read_only=True)

    class Meta:
        model = Book
        fields = [
            'id', 'title', 'author', 'isbn', 'publisher', 'edition',
            'publication_year', 'category', 'category_name', 'shelf_location',
            'description', 'cover_image', 'is_active', 'total_copies',
            'available_copies', 'is_available', 'copies'
        ]


class LoanSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.get_full_name', read_only=True)
    student_username = serializers.CharField(source='student.username', read_only=True)
    student_roll = serializers.CharField(source='student.student_profile.roll_number', read_only=True)
    book_title = serializers.CharField(source='copy.book.title', read_only=True)
    book_isbn = serializers.CharField(source='copy.book.isbn', read_only=True)
    accession_number = serializers.CharField(source='copy.accession_number', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    fine_status_display = serializers.CharField(source='get_fine_status_display', read_only=True)
    refund_status_display = serializers.CharField(source='get_refund_status_display', read_only=True)

    class Meta:
        model = Loan
        fields = [
            'id', 'receipt_number', 'student', 'student_username', 'student_name', 'student_roll',
            'copy', 'accession_number', 'book_title', 'book_isbn', 'issue_date', 'due_date',
            'return_date', 'status', 'status_display', 'deposit_amount', 'daily_fine_rate',
            'overdue_days', 'fine_amount', 'deposit_applied', 'refund_due', 'refund_paid',
            'refund_status', 'refund_status_display', 'remaining_fine_due', 'fine_collected',
            'fine_status', 'fine_status_display', 'notes', 'created_at'
        ]


class ReservationSerializer(serializers.ModelSerializer):
    student_username = serializers.CharField(source='student.username', read_only=True)
    student_roll = serializers.CharField(source='student.student_profile.roll_number', read_only=True)
    book_title = serializers.CharField(source='book.title', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    allocated_accession = serializers.CharField(source='allocated_copy.accession_number', read_only=True)

    class Meta:
        model = Reservation
        fields = [
            'id', 'book', 'book_title', 'student', 'student_username', 'student_roll',
            'allocated_copy', 'allocated_accession', 'request_date', 'status', 'status_display',
            'queue_position', 'pickup_deadline', 'created_at'
        ]


class FinancialTransactionSerializer(serializers.ModelSerializer):
    student_username = serializers.CharField(source='student.username', read_only=True)
    transaction_type_display = serializers.CharField(source='get_transaction_type_display', read_only=True)
    payment_mode_display = serializers.CharField(source='get_payment_mode_display', read_only=True)
    loan_receipt = serializers.CharField(source='loan.receipt_number', read_only=True)

    class Meta:
        model = FinancialTransaction
        fields = [
            'id', 'reference_number', 'loan', 'loan_receipt', 'student', 'student_username',
            'transaction_type', 'transaction_type_display', 'amount', 'payment_mode',
            'payment_mode_display', 'notes', 'created_at'
        ]


class NotificationSerializer(serializers.ModelSerializer):
    notification_type_display = serializers.CharField(source='get_notification_type_display', read_only=True)

    class Meta:
        model = Notification
        fields = [
            'id', 'recipient', 'title', 'message', 'notification_type',
            'notification_type_display', 'is_read', 'link', 'created_at'
        ]


class LibrarySettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = LibrarySettings
        fields = '__all__'
