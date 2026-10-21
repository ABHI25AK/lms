from django.urls import path
from . import views, api_views

urlpatterns = [
    # Public & Authentication
    path('', views.home, name='home'),
    path('catalogue/', views.catalogue, name='catalogue'),
    path('book/<int:pk>/', views.book_detail, name='book_detail'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('dashboard/', views.dashboard_redirect, name='dashboard_redirect'),
    path('receipt/<str:receipt_number>/', views.loan_receipt, name='loan_receipt'),
    path('api/docs/', views.api_documentation_view, name='api_docs'),

    # Student Portal
    path('student/dashboard/', views.student_dashboard, name='student_dashboard'),
    path('student/loans/', views.student_loans, name='student_loans'),
    path('student/reservations/', views.student_reservations, name='student_reservations'),
    path('student/reserve/<int:book_id>/', views.student_reserve_book, name='student_reserve_book'),
    path('student/reservation/cancel/<int:pk>/', views.student_cancel_reservation, name='student_cancel_reservation'),
    path('student/fines/', views.student_fines_deposits, name='student_fines_deposits'),
    path('student/notifications/', views.student_notifications, name='student_notifications'),
    path('student/notifications/read/<int:pk>/', views.mark_single_notification_read, name='mark_single_notification_read'),
    path('student/profile/', views.student_profile, name='student_profile'),

    # Librarian / Admin Portal
    path('librarian/dashboard/', views.librarian_dashboard, name='librarian_dashboard'),
    path('librarian/books/', views.admin_books, name='admin_books'),
    path('librarian/books/add/', views.admin_book_add, name='admin_book_add'),
    path('librarian/books/<int:pk>/edit/', views.admin_book_edit, name='admin_book_edit'),
    path('librarian/books/<int:pk>/', views.admin_book_detail, name='admin_book_detail'),
    path('librarian/books/<int:book_id>/add-copy/', views.admin_copy_add, name='admin_copy_add'),
    path('librarian/copies/<int:pk>/update/', views.admin_copy_update_status, name='admin_copy_update_status'),
    path('librarian/issue/', views.admin_issue_book, name='admin_issue_book'),
    path('librarian/return/', views.admin_return_book, name='admin_return_book'),
    path('librarian/refund/<int:pk>/disburse/', views.admin_disburse_refund, name='admin_disburse_refund'),
    path('librarian/fine/<int:pk>/collect/', views.admin_collect_fine, name='admin_collect_fine'),
    path('librarian/reservations/', views.admin_reservations, name='admin_reservations'),
    path('librarian/reservations/<int:pk>/<str:action>/', views.admin_reservation_action, name='admin_reservation_action'),
    path('librarian/students/', views.admin_students, name='admin_students'),
    path('librarian/students/<int:pk>/', views.admin_student_detail, name='admin_student_detail'),
    path('librarian/ledger/', views.admin_financial_ledger, name='admin_financial_ledger'),
    path('librarian/reports/', views.admin_reports, name='admin_reports'),
    path('librarian/categories/', views.admin_categories, name='admin_categories'),
    path('librarian/settings/', views.admin_settings, name='admin_settings'),
    path('librarian/audit/', views.admin_audit_logs, name='admin_audit_logs'),

    # REST API Endpoints
    path('api/profile/', api_views.CurrentUserProfileAPI.as_view(), name='api_profile'),
    path('api/books/', api_views.BookListAPI.as_view(), name='api_book_list'),
    path('api/books/<int:pk>/', api_views.BookDetailAPI.as_view(), name='api_book_detail'),
    path('api/copies/', api_views.BookCopyListCreateAPI.as_view(), name='api_copies'),
    path('api/students/', api_views.StudentListAPI.as_view(), name='api_students'),
    path('api/loans/', api_views.LoanListAPI.as_view(), name='api_loans'),
    path('api/loans/issue/', api_views.IssueBookAPI.as_view(), name='api_loan_issue'),
    path('api/loans/<int:pk>/return/', api_views.ReturnBookAPI.as_view(), name='api_loan_return'),
    path('api/reservations/', api_views.ReservationListCreateAPI.as_view(), name='api_reservations'),
    path('api/finances/', api_views.FinancialTransactionListAPI.as_view(), name='api_finances'),
    path('api/notifications/', api_views.NotificationListAPI.as_view(), name='api_notifications'),
    path('api/dashboard/stats/', api_views.DashboardStatsAPI.as_view(), name='api_dashboard_stats'),
]
