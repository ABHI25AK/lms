from django.contrib import admin
from .models import (
    LibrarySettings, StudentProfile, Category, Book, BookCopy,
    Loan, Reservation, FinancialTransaction, Notification, AuditLog
)

@admin.register(LibrarySettings)
class LibrarySettingsAdmin(admin.ModelAdmin):
    list_display = ('institution_name', 'department_name', 'academic_year', 'loan_period_days', 'daily_fine_rate', 'deposit_per_loan')

@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'roll_number', 'department', 'semester', 'is_membership_active')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'roll_number')
    list_filter = ('department', 'semester', 'is_membership_active')

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'icon')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)

class BookCopyInline(admin.TabularInline):
    model = BookCopy
    extra = 1

@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'isbn', 'category', 'shelf_location', 'total_copies_count', 'available_copies_count', 'is_active')
    search_fields = ('title', 'author', 'isbn')
    list_filter = ('category', 'is_active')
    inlines = [BookCopyInline]

@admin.register(BookCopy)
class BookCopyAdmin(admin.ModelAdmin):
    list_display = ('accession_number', 'book', 'shelf_location', 'condition', 'status')
    search_fields = ('accession_number', 'book__title', 'shelf_location')
    list_filter = ('status', 'condition')

@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ('receipt_number', 'student', 'copy', 'issue_date', 'due_date', 'return_date', 'status', 'fine_amount', 'refund_due')
    search_fields = ('receipt_number', 'student__username', 'copy__accession_number', 'copy__book__title')
    list_filter = ('status', 'refund_status', 'fine_status')

@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ('id', 'book', 'student', 'status', 'queue_position', 'pickup_deadline', 'request_date')
    search_fields = ('book__title', 'student__username')
    list_filter = ('status',)

@admin.register(FinancialTransaction)
class FinancialTransactionAdmin(admin.ModelAdmin):
    list_display = ('reference_number', 'student', 'transaction_type', 'amount', 'payment_mode', 'created_at')
    search_fields = ('reference_number', 'student__username')
    list_filter = ('transaction_type', 'payment_mode')

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'title', 'notification_type', 'is_read', 'created_at')
    search_fields = ('recipient__username', 'title')
    list_filter = ('notification_type', 'is_read')

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('action', 'module', 'user', 'ip_address', 'created_at')
    search_fields = ('action', 'details', 'user__username')
    list_filter = ('module', 'created_at')
