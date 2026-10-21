import uuid
from decimal import Decimal
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from library.models import (
    LibrarySettings, StudentProfile, Category, Book, BookCopy,
    Loan, Reservation, FinancialTransaction, Notification, AuditLog
)

class Command(BaseCommand):
    help = "Seeds the database with 30+ Computer Science books, physical copies, students, loans, reservations, and financial ledger data."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Initializing seed process for ASM Nextgen Technical Campus Library..."))

        # 1. Initialize Settings
        settings = LibrarySettings.get_settings()
        settings.institution_name = "ASM Nextgen Technical Campus"
        settings.department_name = "Department of Computer Science"
        settings.academic_year = "2025–2026"
        settings.loan_period_days = 14
        settings.daily_fine_rate = Decimal("5.00")
        settings.deposit_per_loan = Decimal("500.00")
        settings.max_active_loans = 3
        settings.reservation_pickup_hours = 48
        settings.allow_student_registration = True
        settings.allow_reserving_available_books = False
        settings.save()
        self.stdout.write(self.style.SUCCESS("[OK] Library settings configured."))

        # 2. Create Users
        # Admin / Chief Librarian
        admin_user, _ = User.objects.get_or_create(
            username='admin',
            defaults={
                'first_name': 'Chief',
                'last_name': 'Librarian',
                'email': 'librarian@asmnextgen.ac.in',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        admin_user.set_password('admin123')
        admin_user.save()

        # Faculty Advisor / Librarian Asst
        faculty_user, _ = User.objects.get_or_create(
            username='apeksha_pande',
            defaults={
                'first_name': 'Prof. Apeksha',
                'last_name': 'Pande',
                'email': 'apeksha.pande@asmnextgen.ac.in',
                'is_staff': True,
                'is_superuser': False,
            }
        )
        faculty_user.set_password('admin123')
        faculty_user.save()

        # Fictional Student Accounts (Academic Year 2025-2026 Project Team & Classmates)
        students_data = [
            {'username': 'abhishek', 'first_name': 'Abhishek', 'last_name': 'Kamble', 'roll': 'SCS101', 'email': 'scs101@asmnextgen.ac.in', 'sem': '6th Semester', 'phone': '+91 98765 43210'},
            {'username': 'kunal', 'first_name': 'Kunal', 'last_name': 'Ambhore', 'roll': 'SCS104', 'email': 'scs104@asmnextgen.ac.in', 'sem': '6th Semester', 'phone': '+91 98765 43211'},
            {'username': 'arpit', 'first_name': 'Arpit', 'last_name': 'Sharma', 'roll': 'SCS106', 'email': 'scs106@asmnextgen.ac.in', 'sem': '6th Semester', 'phone': '+91 98765 43212'},
            {'username': 'vishweshwar', 'first_name': 'Vishweshwar', 'last_name': 'Gaikwad', 'roll': 'SCS123', 'email': 'scs123@asmnextgen.ac.in', 'sem': '6th Semester', 'phone': '+91 98765 43213'},
            {'username': 'neha', 'first_name': 'Neha', 'last_name': 'Patel', 'roll': 'SCS130', 'email': 'scs130@asmnextgen.ac.in', 'sem': '6th Semester', 'phone': '+91 98765 43214'},
            {'username': 'rohit', 'first_name': 'Rohit', 'last_name': 'Deshmukh', 'roll': 'SCS135', 'email': 'scs135@asmnextgen.ac.in', 'sem': '6th Semester', 'phone': '+91 98765 43215'},
        ]

        created_students = {}
        for s in students_data:
            u, _ = User.objects.get_or_create(
                username=s['username'],
                defaults={
                    'first_name': s['first_name'],
                    'last_name': s['last_name'],
                    'email': s['email'],
                    'is_staff': False,
                    'is_superuser': False,
                }
            )
            u.set_password('student123')
            u.save()
            StudentProfile.objects.update_or_create(
                user=u,
                defaults={
                    'roll_number': s['roll'],
                    'department': 'Department of Computer Science',
                    'academic_year': '2025–2026',
                    'semester': s['sem'],
                    'phone': s['phone'],
                    'address': 'ASM Campus Hostel / Pune',
                    'max_books_allowed': 3,
                    'is_membership_active': True,
                }
            )
            created_students[s['username']] = u

        self.stdout.write(self.style.SUCCESS(f"[OK] Created {len(students_data)} student accounts & 2 staff accounts."))

        # 3. Create Categories
        categories_data = [
            ("Artificial Intelligence & ML", "ai-ml", "bi-cpu", "Machine learning algorithms, deep neural architectures, and intelligent systems."),
            ("Algorithms & Data Structures", "algorithms-ds", "bi-diagram-3", "Core algorithmic paradigms, computational complexity, and abstract data types."),
            ("Database Systems", "database-systems", "bi-database", "Relational calculus, SQL optimization, ACID transactions, and NoSQL stores."),
            ("Operating Systems & Architecture", "os-architecture", "bi-motherboard", "Kernel internals, concurrent processes, memory virtualization, and hardware interfaces."),
            ("Computer Networks & Security", "networks-security", "bi-shield-check", "TCP/IP protocol stacks, socket programming, cryptography, and network defense."),
            ("Software Engineering & Design", "software-engineering", "bi-code-slash", "Object-oriented design patterns, refactoring, agile delivery, and system architecture."),
            ("Web & Cloud Computing", "web-cloud", "bi-cloud-check", "Full-stack web architectures, distributed microservices, and containerization."),
        ]

        category_objs = {}
        for name, slug, icon, desc in categories_data:
            cat, _ = Category.objects.update_or_create(
                slug=slug,
                defaults={'name': name, 'icon': icon, 'description': desc}
            )
            category_objs[slug] = cat

        self.stdout.write(self.style.SUCCESS(f"[OK] Created {len(category_objs)} academic categories."))

        # 4. Create 32 Real Computer Science Titles
        books_data = [
            {
                'title': 'Introduction to Algorithms (CLRS)',
                'author': 'Thomas H. Cormen, Charles E. Leiserson, Ronald L. Rivest, Clifford Stein',
                'isbn': '978-0262033848',
                'publisher': 'MIT Press',
                'edition': '4th Edition',
                'year': 2022,
                'category': 'algorithms-ds',
                'shelf': 'CS-RACK-A1',
                'copies_count': 5,
                'desc': 'Comprehensive textbook on modern algorithms covering dynamic programming, graph algorithms, and greedy techniques.'
            },
            {
                'title': 'Design Patterns: Elements of Reusable Object-Oriented Software',
                'author': 'Erich Gamma, Richard Helm, Ralph Johnson, John Vlissides',
                'isbn': '978-0201633610',
                'publisher': 'Addison-Wesley',
                'edition': '1st Edition',
                'year': 1994,
                'category': 'software-engineering',
                'shelf': 'CS-RACK-A2',
                'copies_count': 4,
                'desc': 'The foundational GoF reference presenting 23 classic design patterns for robust object-oriented software engineering.'
            },
            {
                'title': 'Clean Code: A Handbook of Agile Software Craftsmanship',
                'author': 'Robert C. Martin',
                'isbn': '978-0132350884',
                'publisher': 'Prentice Hall',
                'edition': '1st Edition',
                'year': 2008,
                'category': 'software-engineering',
                'shelf': 'CS-RACK-A2',
                'copies_count': 4,
                'desc': 'Best practices for writing readable, maintainable, and test-driven code with practical case studies.'
            },
            {
                'title': 'Operating System Concepts (Dinosaur Book)',
                'author': 'Abraham Silberschatz, Peter B. Galvin, Greg Gagne',
                'isbn': '978-1119800361',
                'publisher': 'Wiley',
                'edition': '10th Edition',
                'year': 2018,
                'category': 'os-architecture',
                'shelf': 'CS-RACK-B1',
                'copies_count': 5,
                'desc': 'Classic operating systems reference covering process synchronization, memory paging, file systems, and virtualization.'
            },
            {
                'title': 'Database System Concepts',
                'author': 'Abraham Silberschatz, Henry F. Korth, S. Sudarshan',
                'isbn': '978-0078022159',
                'publisher': 'McGraw-Hill',
                'edition': '7th Edition',
                'year': 2019,
                'category': 'database-systems',
                'shelf': 'CS-RACK-B2',
                'copies_count': 5,
                'desc': 'Authoritative guide to relational database engines, query optimization, ACID transactions, and distributed data.'
            },
            {
                'title': 'Computer Networks: A Top-Down Approach',
                'author': 'James F. Kurose, Keith W. Ross',
                'isbn': '978-0136681557',
                'publisher': 'Pearson',
                'edition': '8th Edition',
                'year': 2021,
                'category': 'networks-security',
                'shelf': 'CS-RACK-C1',
                'copies_count': 4,
                'desc': 'Principles of network architectures starting from the application layer down to physical transport and routing protocols.'
            },
            {
                'title': 'Artificial Intelligence: A Modern Approach',
                'author': 'Stuart Russell, Peter Norvig',
                'isbn': '978-0134610993',
                'publisher': 'Pearson',
                'edition': '4th Edition',
                'year': 2020,
                'category': 'ai-ml',
                'shelf': 'CS-RACK-C2',
                'copies_count': 4,
                'desc': 'The gold standard reference on modern artificial intelligence, probabilistic reasoning, machine learning, and agents.'
            },
            {
                'title': 'Deep Learning',
                'author': 'Ian Goodfellow, Yoshua Bengio, Aaron Courville',
                'isbn': '978-0262035613',
                'publisher': 'MIT Press',
                'edition': '1st Edition',
                'year': 2016,
                'category': 'ai-ml',
                'shelf': 'CS-RACK-C2',
                'copies_count': 3,
                'desc': 'Comprehensive text on deep feedforward networks, convolution, sequence modeling, and generative adversarial nets.'
            },
            {
                'title': 'Hands-On Machine Learning with Scikit-Learn, Keras, and TensorFlow',
                'author': 'Aurélien Géron',
                'isbn': '978-1098125974',
                'publisher': "O'Reilly Media",
                'edition': '3rd Edition',
                'year': 2022,
                'category': 'ai-ml',
                'shelf': 'CS-RACK-C3',
                'copies_count': 4,
                'desc': 'Practical, hands-on implementation guide for training neural networks and deploying real-world machine learning models.'
            },
            {
                'title': 'Computer Systems: A Programmer\'s Perspective',
                'author': 'Randal E. Bryant, David R. O\'Hallaron',
                'isbn': '978-0134092669',
                'publisher': 'Pearson',
                'edition': '3rd Edition',
                'year': 2015,
                'category': 'os-architecture',
                'shelf': 'CS-RACK-B1',
                'copies_count': 3,
                'desc': 'Bridges the gap between hardware architecture and systems programming, covering memory hierarchy, assembly, and linking.'
            },
            {
                'title': 'Designing Data-Intensive Applications',
                'author': 'Martin Kleppmann',
                'isbn': '978-1449373320',
                'publisher': "O'Reilly Media",
                'edition': '1st Edition',
                'year': 2017,
                'category': 'database-systems',
                'shelf': 'CS-RACK-B2',
                'copies_count': 4,
                'desc': 'The big ideas behind reliable, scalable, and maintainable distributed data systems, replication, and consensus.'
            },
            {
                'title': 'Modern Operating Systems',
                'author': 'Andrew S. Tanenbaum, Herbert Bos',
                'isbn': '978-0133591620',
                'publisher': 'Pearson',
                'edition': '4th Edition',
                'year': 2014,
                'category': 'os-architecture',
                'shelf': 'CS-RACK-B1',
                'copies_count': 3,
                'desc': 'In-depth coverage of contemporary OS architectures, multimedia operating systems, and virtualization.'
            },
            {
                'title': 'Compilers: Principles, Techniques, and Tools (Dragon Book)',
                'author': 'Alfred V. Aho, Monica S. Lam, Ravi Sethi, Jeffrey D. Ullman',
                'isbn': '978-0321486813',
                'publisher': 'Pearson',
                'edition': '2nd Edition',
                'year': 2006,
                'category': 'software-engineering',
                'shelf': 'CS-RACK-A3',
                'copies_count': 3,
                'desc': 'Classic compilation theory covering lexical analysis, parsing, syntax-directed translation, and code optimization.'
            },
            {
                'title': 'The C Programming Language (ANSI C)',
                'author': 'Brian W. Kernighan, Dennis M. Ritchie',
                'isbn': '978-0131103627',
                'publisher': 'Prentice Hall',
                'edition': '2nd Edition',
                'year': 1988,
                'category': 'software-engineering',
                'shelf': 'CS-RACK-A3',
                'copies_count': 5,
                'desc': 'The authoritative, definitive reference on C programming written by its creators.'
            },
            {
                'title': 'Head First Design Patterns',
                'author': 'Eric Freeman, Elisabeth Robson',
                'isbn': '978-1492078005',
                'publisher': "O'Reilly Media",
                'edition': '2nd Edition',
                'year': 2020,
                'category': 'software-engineering',
                'shelf': 'CS-RACK-A2',
                'copies_count': 4,
                'desc': 'Visually rich and brain-friendly explanation of core software design patterns for object-oriented systems.'
            },
            {
                'title': 'Fluent Python: Clear, Concise, and Effective Programming',
                'author': 'Luciano Ramalho',
                'isbn': '978-1492056355',
                'publisher': "O'Reilly Media",
                'edition': '2nd Edition',
                'year': 2022,
                'category': 'software-engineering',
                'shelf': 'CS-RACK-A4',
                'copies_count': 3,
                'desc': 'Guides seasoned developers through the Python language idiom, metaclasses, decorators, and concurrency.'
            },
            {
                'title': 'Distributed Systems: Principles and Paradigms',
                'author': 'Maarten van Steen, Andrew S. Tanenbaum',
                'isbn': '978-1530281756',
                'publisher': 'CreateSpace',
                'edition': '3rd Edition',
                'year': 2017,
                'category': 'web-cloud',
                'shelf': 'CS-RACK-D1',
                'copies_count': 3,
                'desc': 'Foundations of distributed systems including communication architectures, fault tolerance, and security.'
            },
            {
                'title': 'Computer Architecture: A Quantitative Approach',
                'author': 'John L. Hennessy, David A. Patterson',
                'isbn': '978-0128119051',
                'publisher': 'Morgan Kaufmann',
                'edition': '6th Edition',
                'year': 2017,
                'category': 'os-architecture',
                'shelf': 'CS-RACK-B3',
                'copies_count': 3,
                'desc': 'The seminal computer engineering guide to instruction-level parallelism, memory hierarchies, and domain-specific hardware.'
            },
            {
                'title': 'Cryptography and Network Security',
                'author': 'William Stallings',
                'isbn': '978-0134444284',
                'publisher': 'Pearson',
                'edition': '7th Edition',
                'year': 2017,
                'category': 'networks-security',
                'shelf': 'CS-RACK-C1',
                'copies_count': 4,
                'desc': 'Principles and practices of public key cryptography, hash algorithms, IPsec, SSL/TLS, and cyber security.'
            },
            {
                'title': 'Web Application Security: Exploitation and Countermeasures',
                'author': 'Andrew Hoffman',
                'isbn': '978-1492053118',
                'publisher': "O'Reilly Media",
                'edition': '1st Edition',
                'year': 2020,
                'category': 'networks-security',
                'shelf': 'CS-RACK-C1',
                'copies_count': 3,
                'desc': 'Detailed walkthrough of modern web vulnerabilities including CSRF, XSS, SSRF, and defense mechanisms.'
            },
            {
                'title': 'Learning SQL: Generate, Manipulate, and Retrieve Data',
                'author': 'Alan Beaulieu',
                'isbn': '978-1492057611',
                'publisher': "O'Reilly Media",
                'edition': '3rd Edition',
                'year': 2020,
                'category': 'database-systems',
                'shelf': 'CS-RACK-B2',
                'copies_count': 4,
                'desc': 'Step-by-step introduction to SQL querying, joins, grouping, window functions, and transaction statements.'
            },
            {
                'title': 'Site Reliability Engineering: How Google Runs Production Systems',
                'author': 'Niall Richard Murphy, Betsy Beyer, Chris Jones, Jennifer Petoff',
                'isbn': '978-1491929124',
                'publisher': "O'Reilly Media",
                'edition': '1st Edition',
                'year': 2016,
                'category': 'web-cloud',
                'shelf': 'CS-RACK-D1',
                'copies_count': 3,
                'desc': 'Key engineering principles behind building and operating planet-scale cloud infrastructure with zero downtime.'
            },
            {
                'title': 'Kubernetes in Action',
                'author': 'Marko Luksa',
                'isbn': '978-1617293726',
                'publisher': 'Manning',
                'edition': '1st Edition',
                'year': 2018,
                'category': 'web-cloud',
                'shelf': 'CS-RACK-D2',
                'copies_count': 3,
                'desc': 'Comprehensive developer guide to container orchestration, service discovery, pods, and cluster deployments.'
            },
            {
                'title': 'Natural Language Processing with Transformers',
                'author': 'Lewis Tunstall, Leandro von Werra, Thomas Wolf',
                'isbn': '978-1098103248',
                'publisher': "O'Reilly Media",
                'edition': '1st Edition',
                'year': 2022,
                'category': 'ai-ml',
                'shelf': 'CS-RACK-C3',
                'copies_count': 3,
                'desc': 'Building language models with Hugging Face transformers, fine-tuning BERT, GPT, and modern attention architectures.'
            },
            {
                'title': 'Reinforcement Learning: An Introduction',
                'author': 'Richard S. Sutton, Andrew G. Barto',
                'isbn': '978-0262039246',
                'publisher': 'MIT Press',
                'edition': '2nd Edition',
                'year': 2018,
                'category': 'ai-ml',
                'shelf': 'CS-RACK-C3',
                'copies_count': 3,
                'desc': 'Foundational textbook on Markov decision processes, Monte Carlo methods, and Q-learning in artificial intelligence.'
            },
            {
                'title': 'Refactoring: Improving the Design of Existing Code',
                'author': 'Martin Fowler',
                'isbn': '978-0134757599',
                'publisher': 'Addison-Wesley',
                'edition': '2nd Edition',
                'year': 2018,
                'category': 'software-engineering',
                'shelf': 'CS-RACK-A2',
                'copies_count': 3,
                'desc': 'Handbook of proven code transformation techniques to eliminate code smells and improve software architecture.'
            },
            {
                'title': 'Introduction to the Theory of Computation',
                'author': 'Michael Sipser',
                'isbn': '978-1133187790',
                'publisher': 'Cengage Learning',
                'edition': '3rd Edition',
                'year': 2012,
                'category': 'algorithms-ds',
                'shelf': 'CS-RACK-A1',
                'copies_count': 4,
                'desc': 'Clear introduction to formal languages, automata theory, Turing machines, and NP-completeness.'
            },
            {
                'title': 'Python Crash Course: A Hands-On, Project-Based Introduction',
                'author': 'Eric Matthes',
                'isbn': '978-1718502703',
                'publisher': 'No Starch Press',
                'edition': '3rd Edition',
                'year': 2023,
                'category': 'software-engineering',
                'shelf': 'CS-RACK-A4',
                'copies_count': 5,
                'desc': 'Fast-paced, thorough introduction to Python programming with web application and data analysis projects.'
            },
            {
                'title': 'Pattern Recognition and Machine Learning',
                'author': 'Christopher M. Bishop',
                'isbn': '978-0387310732',
                'publisher': 'Springer',
                'edition': '1st Edition',
                'year': 2006,
                'category': 'ai-ml',
                'shelf': 'CS-RACK-C2',
                'copies_count': 3,
                'desc': 'Rigorous probabilistic formulation of pattern classification, graphical models, and Bayesian inference.'
            },
            {
                'title': 'Cloud Native Patterns: Designing Scalable Apps',
                'author': 'Cornelia Davis',
                'isbn': '978-1617294297',
                'publisher': 'Manning',
                'edition': '1st Edition',
                'year': 2019,
                'category': 'web-cloud',
                'shelf': 'CS-RACK-D2',
                'copies_count': 3,
                'desc': 'Architectural patterns for microservices, circuit breakers, and event-driven architectures on cloud platforms.'
            },
            {
                'title': 'The Pragmatic Programmer: Your Journey To Mastery',
                'author': 'David Thomas, Andrew Hunt',
                'isbn': '978-0135957059',
                'publisher': 'Addison-Wesley',
                'edition': '20th Anniversary Edition',
                'year': 2019,
                'category': 'software-engineering',
                'shelf': 'CS-RACK-A2',
                'copies_count': 4,
                'desc': 'Timeless professional software development advice from career wisdom to technical methodologies.'
            },
            {
                'title': 'Structure and Interpretation of Computer Programs',
                'author': 'Harold Abelson, Gerald Jay Sussman',
                'isbn': '978-0262510875',
                'publisher': 'MIT Press',
                'edition': '2nd Edition',
                'year': 1996,
                'category': 'software-engineering',
                'shelf': 'CS-RACK-A3',
                'copies_count': 3,
                'desc': 'Legendary MIT computer science curriculum on computational processes, abstraction, and functional interpreters.'
            }
        ]

        book_objs = []
        copy_objs = []
        copy_counter = 101

        for bdata in books_data:
            book, _ = Book.objects.update_or_create(
                isbn=bdata['isbn'],
                defaults={
                    'title': bdata['title'],
                    'author': bdata['author'],
                    'publisher': bdata['publisher'],
                    'edition': bdata['edition'],
                    'publication_year': bdata['year'],
                    'category': category_objs[bdata['category']],
                    'shelf_location': bdata['shelf'],
                    'description': bdata['desc'],
                    'is_active': True,
                }
            )
            book_objs.append(book)

            # Create physical copies
            for i in range(1, bdata['copies_count'] + 1):
                accession_num = f"CS-2025-{copy_counter:04d}"
                copy_counter += 1
                copy, _ = BookCopy.objects.update_or_create(
                    accession_number=accession_num,
                    defaults={
                        'book': book,
                        'shelf_location': f"{bdata['shelf']}-C{i}",
                        'condition': 'GOOD' if i > 1 else 'NEW',
                        'status': 'AVAILABLE',
                    }
                )
                copy_objs.append(copy)

        self.stdout.write(self.style.SUCCESS(f"[OK] Created {len(book_objs)} book titles with {len(copy_objs)} physical copies."))

        # 5. Create Realistic Sample Circulation Data
        # We will create:
        # a) Active on-time loans
        # b) Overdue active loan
        # c) Returned loan with NO overdue fine (₹0 fine, ₹500 refund due/paid)
        # d) Returned loan with overdue fine (e.g. 4 days late: ₹20 fine deducted from deposit, ₹480 refund due)
        # e) Returned loan with fine exceeding deposit (e.g. ₹550 fine: ₹500 deposit applied, ₹50 outstanding fine due)
        # f) Reservations in queue and one READY_FOR_PICKUP

        today = date.today()
        student_abhi = created_students['abhishek']
        student_kunal = created_students['kunal']
        student_arpit = created_students['arpit']
        student_vishwa = created_students['vishweshwar']
        student_neha = created_students['neha']

        # a) Active Loan 1: Abhishek borrowed Introduction to Algorithms (CLRS) 5 days ago
        clrs_copy = BookCopy.objects.filter(book__isbn='978-0262033848', status='AVAILABLE').first()
        if clrs_copy:
            clrs_copy.status = 'ON_LOAN'
            clrs_copy.save()
            loan1 = Loan.objects.create(
                copy=clrs_copy,
                student=student_abhi,
                issue_date=today - timedelta(days=5),
                due_date=today + timedelta(days=9),
                status='ACTIVE',
                deposit_amount=Decimal("500.00"),
                daily_fine_rate=Decimal("5.00"),
                issued_by=admin_user,
                receipt_number=f"LN-{today.strftime('%Y%m%d')}-ABHI01",
                notes="Issued for CS Core Algorithm Lab assignment."
            )
            # Record deposit transaction
            FinancialTransaction.objects.create(
                loan=loan1,
                student=student_abhi,
                transaction_type='DEPOSIT_COLLECTED',
                amount=Decimal("500.00"),
                payment_mode='CASH',
                reference_number=f"TXN-DEP-{uuid.uuid4().hex[:8].upper()}",
                recorded_by=admin_user,
                notes="Security deposit collected at circulation counter"
            )
            Notification.objects.create(
                recipient=student_abhi,
                title="Book Issued Successfully",
                message=f"You have borrowed '{clrs_copy.book.title}' (Acc: {clrs_copy.accession_number}). Due date is {(today + timedelta(days=9)).strftime('%d-%b-%Y')}.",
                notification_type='BOOK_ISSUED',
                link="/student/loans/"
            )

        # b) Overdue Loan: Kunal borrowed Operating System Concepts 20 days ago (due 6 days ago!)
        os_copy = BookCopy.objects.filter(book__isbn='978-1119800361', status='AVAILABLE').first()
        if os_copy:
            os_copy.status = 'ON_LOAN'
            os_copy.save()
            loan_overdue = Loan.objects.create(
                copy=os_copy,
                student=student_kunal,
                issue_date=today - timedelta(days=20),
                due_date=today - timedelta(days=6),
                status='OVERDUE',
                deposit_amount=Decimal("500.00"),
                daily_fine_rate=Decimal("5.00"),
                issued_by=admin_user,
                receipt_number=f"LN-{(today - timedelta(days=20)).strftime('%Y%m%d')}-KUN01",
                notes="Overdue notice active."
            )
            FinancialTransaction.objects.create(
                loan=loan_overdue,
                student=student_kunal,
                transaction_type='DEPOSIT_COLLECTED',
                amount=Decimal("500.00"),
                payment_mode='UPI',
                reference_number=f"TXN-DEP-{uuid.uuid4().hex[:8].upper()}",
                recorded_by=admin_user,
                notes="Security deposit collected via UPI"
            )
            Notification.objects.create(
                recipient=student_kunal,
                title="Book Overdue Alert!",
                message=f"Your loan for '{os_copy.book.title}' was due on {(today - timedelta(days=6)).strftime('%d-%b-%Y')}. Overdue penalty of ₹5/day is accumulating.",
                notification_type='OVERDUE',
                link="/student/loans/"
            )

        # c) Returned Loan: Arpit borrowed Clean Code and returned on due date (₹0 fine, ₹500 refund due & disbursed)
        clean_copy = BookCopy.objects.filter(book__isbn='978-0132350884', status='AVAILABLE').first()
        if clean_copy:
            loan_returned_ok = Loan.objects.create(
                copy=clean_copy,
                student=student_arpit,
                issue_date=today - timedelta(days=14),
                due_date=today,
                return_date=today,
                status='RETURNED',
                deposit_amount=Decimal("500.00"),
                daily_fine_rate=Decimal("5.00"),
                overdue_days=0,
                fine_amount=Decimal("0.00"),
                deposit_applied=Decimal("0.00"),
                refund_due=Decimal("500.00"),
                refund_paid=Decimal("500.00"),
                refund_status='PAID',
                fine_status='NONE',
                issued_by=admin_user,
                returned_by=admin_user,
                receipt_number=f"LN-{(today - timedelta(days=14)).strftime('%Y%m%d')}-ARP01",
                notes="Returned in excellent condition. Refund disbursed in cash."
            )
            # Transaction 1: Deposit collected
            FinancialTransaction.objects.create(
                loan=loan_returned_ok,
                student=student_arpit,
                transaction_type='DEPOSIT_COLLECTED',
                amount=Decimal("500.00"),
                payment_mode='CASH',
                reference_number=f"TXN-DEP-{uuid.uuid4().hex[:8].upper()}",
                recorded_by=admin_user,
                notes="Deposit collected at issue"
            )
            # Transaction 2: Refund issued
            FinancialTransaction.objects.create(
                loan=loan_returned_ok,
                student=student_arpit,
                transaction_type='REFUND_ISSUED',
                amount=Decimal("500.00"),
                payment_mode='CASH',
                reference_number=f"TXN-REF-{uuid.uuid4().hex[:8].upper()}",
                recorded_by=admin_user,
                notes="Full security deposit refunded on timely return"
            )

        # d) Returned Loan: Vishweshwar returned Database System Concepts 4 days late
        # Fine: 4 days * 5 = ₹20. Deposit applied: ₹20. Refund due: ₹480 (pending manual pickup).
        db_copy = BookCopy.objects.filter(book__isbn='978-0078022159', status='AVAILABLE').first()
        if db_copy:
            loan_returned_fine = Loan.objects.create(
                copy=db_copy,
                student=student_vishwa,
                issue_date=today - timedelta(days=18),
                due_date=today - timedelta(days=4),
                return_date=today,
                status='RETURNED',
                deposit_amount=Decimal("500.00"),
                daily_fine_rate=Decimal("5.00"),
                overdue_days=4,
                fine_amount=Decimal("20.00"),
                deposit_applied=Decimal("20.00"),
                refund_due=Decimal("480.00"),
                refund_paid=Decimal("0.00"),
                refund_status='PENDING',
                fine_status='SETTLED_FROM_DEPOSIT',
                issued_by=admin_user,
                returned_by=admin_user,
                receipt_number=f"LN-{(today - timedelta(days=18)).strftime('%Y%m%d')}-VIS01",
                notes="Overdue fine of ₹20 adjusted against deposit. ₹480 cash refund pending collection."
            )
            FinancialTransaction.objects.create(
                loan=loan_returned_fine,
                student=student_vishwa,
                transaction_type='DEPOSIT_COLLECTED',
                amount=Decimal("500.00"),
                payment_mode='CASH',
                reference_number=f"TXN-DEP-{uuid.uuid4().hex[:8].upper()}",
                recorded_by=admin_user,
                notes="Deposit collected at issue"
            )
            FinancialTransaction.objects.create(
                loan=loan_returned_fine,
                student=student_vishwa,
                transaction_type='FINE_DEDUCTED',
                amount=Decimal("20.00"),
                payment_mode='DEPOSIT_OFFSET',
                reference_number=f"TXN-FINE-{uuid.uuid4().hex[:8].upper()}",
                recorded_by=admin_user,
                notes="₹20 fine deducted from deposit (4 days overdue)"
            )
            Notification.objects.create(
                recipient=student_vishwa,
                title="Book Return Settled",
                message="Return settled for Database System Concepts. Overdue: 4 days. Fine ₹20 deducted from deposit. Please collect your ₹480 balance refund from the library counter.",
                notification_type='RETURN_SETTLED',
                link="/student/fines/"
            )

        # 6. Create Realistic Reservations
        # Book: Deep Learning
        dl_book = Book.objects.get(isbn='978-0262035613')
        
        # Reservation 1: Neha is waiting in queue (APPROVED)
        r1 = Reservation.objects.create(
            book=dl_book,
            student=student_neha,
            status='APPROVED',
            queue_position=1,
            approved_by=admin_user
        )

        # Book: Designing Data-Intensive Applications
        ddia_book = Book.objects.get(isbn='978-1449373320')
        ddia_copy = ddia_book.copies.first()
        ddia_copy.status = 'RESERVED'
        ddia_copy.save()

        # Reservation 2: Abhishek has a reservation READY_FOR_PICKUP
        pickup_deadline = timezone.now() + timedelta(hours=36)
        r2 = Reservation.objects.create(
            book=ddia_book,
            student=student_abhi,
            allocated_copy=ddia_copy,
            status='READY_FOR_PICKUP',
            queue_position=1,
            pickup_deadline=pickup_deadline,
            approved_by=admin_user,
            notification_sent=True
        )
        Notification.objects.create(
            recipient=student_abhi,
            title="Book Ready for Pickup!",
            message=f"'{ddia_book.title}' has been allocated to you (Copy: {ddia_copy.accession_number}). Please pick it up before {pickup_deadline.strftime('%d-%b-%Y %I:%M %p')}.",
            notification_type='RESERVATION_READY',
            link="/student/reservations/"
        )

        # 7. Add Audit Logs
        AuditLog.objects.create(
            user=admin_user,
            action="SYSTEM_INIT",
            module="SETTINGS",
            details="Database seeded with initial catalog of 32 Computer Science titles, copies, and student records."
        )
        AuditLog.objects.create(
            user=admin_user,
            action="ISSUE_BOOK",
            module="CIRCULATION",
            details=f"Issued copy {clrs_copy.accession_number if clrs_copy else 'CS-2025-0101'} to student {student_abhi.username} with deposit ₹500."
        )
        AuditLog.objects.create(
            user=admin_user,
            action="SETTLE_RETURN",
            module="CIRCULATION",
            details=f"Settled return for student {student_vishwa.username}. Fine assessed ₹20, balance refund due ₹480."
        )

        self.stdout.write(self.style.SUCCESS("[OK] Seeded sample loans, reservations, financial transactions, and notifications."))
        self.stdout.write(self.style.SUCCESS("=== SEEDING COMPLETED SUCCESSFULLY ==="))
        self.stdout.write(self.style.NOTICE("""
Dev Login Credentials:
- Administrator / Librarian: username: 'admin' | password: 'admin123'
- Faculty Librarian:        username: 'apeksha_pande' | password: 'admin123'
- Student 1 (Lead Author):  username: 'abhishek' | password: 'student123' (Roll: SCS101)
- Student 2 (Co-Author):    username: 'kunal'    | password: 'student123' (Roll: SCS104)
- Student 3 (Co-Author):    username: 'arpit'    | password: 'student123' (Roll: SCS106)
- Student 4 (Co-Author):    username: 'vishweshwar' | password: 'student123' (Roll: SCS123)
"""))
