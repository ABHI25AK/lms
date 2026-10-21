from django.conf import settings
from .models import LibrarySettings, Notification, Loan

def library_global_context(request):
    """
    Injects institution branding, library global settings,
    and user-specific badges (such as unread notifications count) into all templates.
    """
    context = {
        'INSTITUTION_NAME': getattr(settings, 'INSTITUTION_NAME', 'ASM Nextgen Technical Campus'),
        'DEPARTMENT_NAME': getattr(settings, 'DEPARTMENT_NAME', 'Department of Computer Science'),
        'ACADEMIC_YEAR': getattr(settings, 'ACADEMIC_YEAR', '2025–2026'),
        'library_settings': LibrarySettings.get_settings(),
        'unread_notifications_count': 0,
        'user_active_loans_count': 0,
        'is_librarian': False,
        'student_profile': None,
    }

    if request.user.is_authenticated:
        context['unread_notifications_count'] = Notification.objects.filter(
            recipient=request.user, is_read=False
        ).count()
        context['is_librarian'] = request.user.is_staff or request.user.is_superuser
        
        if not context['is_librarian']:
            context['user_active_loans_count'] = Loan.objects.filter(
                student=request.user, status__in=['ACTIVE', 'OVERDUE']
            ).count()
            if hasattr(request.user, 'student_profile'):
                context['student_profile'] = request.user.student_profile

    return context
