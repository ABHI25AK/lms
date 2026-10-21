from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from library.models import Loan, Reservation, Notification, AuditLog, LibrarySettings

class Command(BaseCommand):
    help = "Daily scheduled cron job to generate due-soon alerts, flag overdue loans, and expire uncollected reservations."

    def handle(self, *args, **options):
        today = date.today()
        now = timezone.now()
        settings = LibrarySettings.get_settings()

        self.stdout.write(self.style.NOTICE(f"Running automated library reminders and queue processing for {today}..."))

        reminders_sent = 0
        overdue_flagged = 0
        reservations_expired = 0

        # 1. Due Soon Reminders (Loans due in next 2 calendar days)
        due_soon_threshold = today + timedelta(days=2)
        loans_due_soon = Loan.objects.filter(
            status='ACTIVE',
            due_date__gte=today,
            due_date__lte=due_soon_threshold
        ).select_related('student', 'copy__book')

        for loan in loans_due_soon:
            days_left = (loan.due_date - today).days
            day_str = "today" if days_left == 0 else ("tomorrow" if days_left == 1 else f"in {days_left} days")
            
            # Avoid sending duplicate notifications on the same day
            already_notified_today = Notification.objects.filter(
                recipient=loan.student,
                notification_type='DUE_SOON',
                created_at__date=today,
                message__contains=loan.copy.accession_number
            ).exists()

            if not already_notified_today:
                Notification.objects.create(
                    recipient=loan.student,
                    title="Upcoming Due Date Reminder",
                    message=f"Reminder: '{loan.copy.book.title}' (Copy {loan.copy.accession_number}) is due {day_str} ({loan.due_date.strftime('%d-%b-%Y')}). Please return on time to avoid fine deductions.",
                    notification_type='DUE_SOON',
                    link="/student/loans/"
                )
                reminders_sent += 1

        # 2. Flag Overdue Loans (Loans where due_date < today and not yet returned)
        loans_overdue = Loan.objects.filter(
            status__in=['ACTIVE', 'OVERDUE'],
            due_date__lt=today
        ).select_related('student', 'copy__book')

        for loan in loans_overdue:
            if loan.status != 'OVERDUE':
                loan.status = 'OVERDUE'
                loan.save(update_fields=['status'])
                overdue_flagged += 1

            overdue_days = (today - loan.due_date).days
            current_penalty = overdue_days * loan.daily_fine_rate

            already_alerted_today = Notification.objects.filter(
                recipient=loan.student,
                notification_type='OVERDUE',
                created_at__date=today,
                message__contains=loan.copy.accession_number
            ).exists()

            if not alerted_today if 'alerted_today' in locals() else not already_alerted_today:
                Notification.objects.create(
                    recipient=loan.student,
                    title="Loan Overdue Notice",
                    message=f"Overdue Notice: '{loan.copy.book.title}' (Copy {loan.copy.accession_number}) was due on {loan.due_date.strftime('%d-%b-%Y')} ({overdue_days} days ago). Current calculated penalty: ₹{current_penalty}.",
                    notification_type='OVERDUE',
                    link="/student/loans/"
                )
                reminders_sent += 1

        # 3. Process Expired Reservations
        expired_reservations = Reservation.objects.filter(
            status='READY_FOR_PICKUP',
            pickup_deadline__lt=now
        ).select_related('book', 'student', 'allocated_copy')

        for res in expired_reservations:
            copy = res.allocated_copy
            res.status = 'EXPIRED'
            res.allocated_copy = None
            res.save()
            reservations_expired += 1

            Notification.objects.create(
                recipient=res.student,
                title="Reservation Expired",
                message=f"Your reservation for '{res.book.title}' has expired because the pickup deadline ({res.pickup_deadline.strftime('%d-%b-%Y %I:%M %p')}) has passed.",
                notification_type='RESERVATION_EXPIRED',
                link="/student/reservations/"
            )

            AuditLog.objects.create(
                user=None,
                action="EXPIRE_RESERVATION",
                module="RESERVATIONS",
                details=f"Reservation #{res.id} for student {res.student.username} expired. Pickup deadline was {res.pickup_deadline}."
            )

            # Check if another student is waiting in FIFO queue
            if copy:
                next_in_queue = Reservation.objects.filter(
                    book=copy.book,
                    status='APPROVED',
                    allocated_copy__isnull=True
                ).order_by('request_date').first()

                if next_in_queue:
                    new_deadline = now + timedelta(hours=settings.reservation_pickup_hours)
                    next_in_queue.status = 'READY_FOR_PICKUP'
                    next_in_queue.allocated_copy = copy
                    next_in_queue.pickup_deadline = new_deadline
                    next_in_queue.notification_sent = True
                    next_in_queue.save()

                    copy.status = 'RESERVED'
                    copy.save()

                    Notification.objects.create(
                        recipient=next_in_queue.student,
                        title="Book Ready for Pickup!",
                        message=f"Good news! '{copy.book.title}' is now ready for pickup. Please collect it from the counter before {new_deadline.strftime('%d-%b-%Y %I:%M %p')}.",
                        notification_type='RESERVATION_READY',
                        link="/student/reservations/"
                    )

                    AuditLog.objects.create(
                        user=None,
                        action="REALLOCATE_RESERVATION",
                        module="RESERVATIONS",
                        details=f"Reallocated Copy {copy.accession_number} to reservation #{next_in_queue.id} ({next_in_queue.student.username}) after previous reservation expired."
                    )
                else:
                    copy.status = 'AVAILABLE'
                    copy.save()

        self.stdout.write(self.style.SUCCESS(
            f"Processing complete: {reminders_sent} notifications created, "
            f"{overdue_flagged} loans marked overdue, {reservations_expired} expired reservations handled."
        ))
