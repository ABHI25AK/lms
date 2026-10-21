from decimal import Decimal
from datetime import date, timedelta
from django import forms
from django.contrib.auth.models import User
from .models import (
    Book, BookCopy, Category, Loan, Reservation,
    StudentProfile, LibrarySettings, FinancialTransaction
)

class StudentRegistrationForm(forms.ModelForm):
    """
    Secure student registration form. Users cannot assign themselves admin role.
    """
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter unique username'}))
    first_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}))
    last_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'College Email ID'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password (min 6 characters)'}))
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm Password'}))
    
    roll_number = forms.CharField(max_length=30, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. SCS140'}))
    semester = forms.CharField(max_length=50, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 6th Semester'}))
    phone = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+91 Mobile Number'}))
    address = forms.CharField(required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Hostel / Local Address'}))

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("This username is already registered.")
        return username

    def clean_roll_number(self):
        roll_number = self.cleaned_data['roll_number'].strip().upper()
        if StudentProfile.objects.filter(roll_number=roll_number).exists():
            raise forms.ValidationError("A student with this roll number is already registered.")
        return roll_number

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', "Passwords do not match.")
        if password and len(password) < 6:
            self.add_error('password', "Password must be at least 6 characters.")
        return cleaned_data


class StudentProfileForm(forms.ModelForm):
    """
    Form for students to update their contact details.
    """
    first_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control'}))

    class Meta:
        model = StudentProfile
        fields = ['phone', 'address']
        widgets = {
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class BookForm(forms.ModelForm):
    """
    Admin form for creating and updating bibliographic book records.
    """
    class Meta:
        model = Book
        fields = [
            'title', 'author', 'isbn', 'category', 'publisher',
            'edition', 'publication_year', 'shelf_location', 'description',
            'cover_image', 'is_active'
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Book Title'}),
            'author': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Author(s)'}),
            'isbn': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ISBN (e.g. 978-0132350884)'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'publisher': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Publisher Name'}),
            'edition': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 3rd Edition'}),
            'publication_year': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 2024'}),
            'shelf_location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. CS-RACK-B2'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Summary / Syllabus relevance'}),
            'cover_image': forms.FileInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class BookCopyForm(forms.ModelForm):
    """
    Admin form for adding physical copies of a book.
    """
    number_of_copies = forms.IntegerField(
        initial=1, min_value=1, max_value=20,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Number of copies to generate'}),
        help_text="Generate multiple sequential copies in one batch"
    )

    class Meta:
        model = BookCopy
        fields = ['book', 'accession_number', 'shelf_location', 'condition', 'status', 'notes']
        widgets = {
            'book': forms.Select(attrs={'class': 'form-select'}),
            'accession_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. CS-2025-0150 (Leave blank for auto-generate)'}),
            'shelf_location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Specific shelf compartment'}),
            'condition': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional remarks'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['accession_number'].required = False


class IssueBookForm(forms.Form):
    """
    Admin workflow form to issue a physical copy to a student.
    Enforces borrowing limit and copy availability.
    """
    student = forms.ModelChoiceField(
        queryset=User.objects.filter(is_staff=False, is_active=True).select_related('student_profile').order_by('username'),
        widget=forms.Select(attrs={'class': 'form-select select2-enable'}),
        help_text="Select student by username or name"
    )
    copy = forms.ModelChoiceField(
        queryset=BookCopy.objects.filter(status='AVAILABLE', condition__in=['NEW', 'GOOD', 'FAIR']).select_related('book').order_by('accession_number'),
        widget=forms.Select(attrs={'class': 'form-select select2-enable'}),
        help_text="Select available physical copy"
    )
    deposit_collected = forms.DecimalField(
        max_digits=10, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
        help_text="Mandatory refundable security deposit in INR (₹)"
    )
    payment_mode = forms.ChoiceField(
        choices=[('CASH', 'Cash'), ('UPI', 'UPI / Online Transfer')],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    notes = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Circulation remarks'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        settings = LibrarySettings.get_settings()
        self.fields['deposit_collected'].initial = settings.deposit_per_loan

    def clean(self):
        cleaned_data = super().clean()
        student = cleaned_data.get('student')
        copy = cleaned_data.get('copy')

        if student:
            # Check student active loans limit
            settings = LibrarySettings.get_settings()
            active_count = Loan.objects.filter(student=student, status__in=['ACTIVE', 'OVERDUE']).count()
            max_allowed = student.student_profile.max_books_allowed if hasattr(student, 'student_profile') else settings.max_active_loans
            if active_count >= max_allowed:
                raise forms.ValidationError(
                    f"Student {student.get_full_name() or student.username} has reached the maximum borrowing limit ({active_count}/{max_allowed} active loans)."
                )

            # Check if student has unpaid outstanding fine balance > 0
            unpaid_fines = Loan.objects.filter(student=student, status='RETURNED', fine_status='PARTIALLY_SETTLED').exists()
            if unpaid_fines:
                raise forms.ValidationError(
                    f"Student {student.username} has an outstanding overdue balance from previous loans. Please settle outstanding fines before issuing new books."
                )

        if copy:
            # Check copy availability
            if copy.status != 'AVAILABLE':
                raise forms.ValidationError(
                    f"Copy {copy.accession_number} is currently '{copy.get_status_display()}' and cannot be issued."
                )

            # Check if there is an approved FIFO reservation queue
            # If so, copy must go to the student at head of queue unless this issue is for them!
            earliest_res = Reservation.objects.filter(
                book=copy.book,
                status='APPROVED',
                allocated_copy__isnull=True
            ).order_by('request_date').first()

            if earliest_res and earliest_res.student != student:
                raise forms.ValidationError(
                    f"Book '{copy.book.title}' has an approved reservation waiting for student {earliest_res.student.username}. Priority must be respected."
                )

        return cleaned_data


class ReturnBookForm(forms.Form):
    """
    Admin workflow form to process return and calculate deposit-linked settlement.
    """
    loan = forms.ModelChoiceField(
        queryset=Loan.objects.filter(status__in=['ACTIVE', 'OVERDUE']).select_related('student', 'copy__book').order_by('receipt_number'),
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'loan-select'}),
        help_text="Select active loan receipt to return"
    )
    return_date = forms.DateField(
        initial=date.today,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'id': 'return-date-input'})
    )
    disburse_refund_now = forms.BooleanField(
        required=False, initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'refund-now-check'}),
        help_text="Disburse refundable deposit balance immediately in cash"
    )
    collect_remaining_fine_now = forms.BooleanField(
        required=False, initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'collect-fine-check'}),
        help_text="Collect any extra fine exceeding deposit in cash/UPI immediately"
    )
    notes = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Condition on return / settlement notes'})
    )


class LibrarySettingsForm(forms.ModelForm):
    """
    Admin settings form for configuring institution operational rules.
    """
    class Meta:
        model = LibrarySettings
        fields = [
            'institution_name', 'department_name', 'academic_year',
            'loan_period_days', 'daily_fine_rate', 'deposit_per_loan',
            'max_active_loans', 'reservation_pickup_hours',
            'allow_student_registration', 'allow_reserving_available_books'
        ]
        widgets = {
            'institution_name': forms.TextInput(attrs={'class': 'form-control'}),
            'department_name': forms.TextInput(attrs={'class': 'form-control'}),
            'academic_year': forms.TextInput(attrs={'class': 'form-control'}),
            'loan_period_days': forms.NumberInput(attrs={'class': 'form-control'}),
            'daily_fine_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.50'}),
            'deposit_per_loan': forms.NumberInput(attrs={'class': 'form-control', 'step': '10.00'}),
            'max_active_loans': forms.NumberInput(attrs={'class': 'form-control'}),
            'reservation_pickup_hours': forms.NumberInput(attrs={'class': 'form-control'}),
            'allow_student_registration': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'allow_reserving_available_books': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
