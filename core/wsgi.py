"""
WSGI config for core project.
Exposes application and app for Vercel serverless functions.
"""

import os
import shutil
from pathlib import Path
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

application = get_wsgi_application()
app = application

# Serverless cold-start database synchronization for Vercel
if 'VERCEL' in os.environ:
    from django.conf import settings
    db_config = settings.DATABASES.get('default', {})
    if db_config.get('ENGINE') == 'django.db.backends.sqlite3':
        db_path = Path(db_config.get('NAME', ''))
        repo_db = settings.BASE_DIR / 'db.sqlite3'
        if repo_db.exists():
            if not db_path.exists() or db_path.stat().st_size == 0:
                db_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(repo_db, db_path)
        else:
            from django.core.management import call_command
            try:
                call_command('migrate', interactive=False)
                call_command('seed_library_data')
            except Exception:
                pass
