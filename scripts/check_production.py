import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django
from django.db import connection
from django.db.utils import OperationalError
from django.conf import settings
from redis import Redis
from celery import Celery

# Initialize Django to access models and settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dairymind.settings.production')
django.setup()

from django.contrib.auth import get_user_model

# Terminal colors
GREEN = '\033[92m'
RED = '\033[91m'
RESET = '\033[0m'

def print_result(check_name, passed, error_msg=""):
    if passed:
        print(f"{check_name.ljust(40)} [{GREEN}PASS{RESET}]")
    else:
        print(f"{check_name.ljust(40)} [{RED}FAIL{RESET}] {error_msg}")
        
def run_checks():
    failed = False
    
    # 1. Environment Variables
    required_envs = ['DB_NAME', 'DB_USER', 'DB_PASSWORD', 'REDIS_URL', 'GEMINI_API_KEY', 'SECRET_KEY']
    for env in required_envs:
        is_set = os.environ.get(env) is not None
        print_result(f"Env Var: {env}", is_set)
        if not is_set: failed = True
        
    debug_val = os.environ.get('DEBUG', 'True')
    debug_passed = debug_val.lower() in ('false', '0', 'f')
    print_result("Env Var: DEBUG=False", debug_passed, f"(Currently {debug_val})")
    if not debug_passed: failed = True
    
    # 2. Database Connection
    try:
        connection.ensure_connection()
        print_result("Database Connection", True)
    except Exception as e:
        print_result("Database Connection", False, str(e))
        failed = True
        
    # 3. Redis Connection
    redis_url = os.environ.get('REDIS_URL', getattr(settings, 'CELERY_BROKER_URL', 'redis://localhost:6379/0'))
    try:
        client = Redis.from_url(redis_url)
        if client.ping():
            print_result("Redis Connection", True)
        else:
            print_result("Redis Connection", False, "Ping failed")
            failed = True
    except Exception as e:
        print_result("Redis Connection", False, str(e))
        failed = True
        
    # 4. Celery Worker Ping
    try:
        app = Celery('dairymind', broker=redis_url)
        # timeout set to 2s
        result = app.control.ping(timeout=2.0)
        if result:
            print_result("Celery Worker Ping", True)
        else:
            print_result("Celery Worker Ping", False, "No active workers found (Make sure celery worker is running)")
            failed = True
    except Exception as e:
        print_result("Celery Worker Ping", False, str(e))
        failed = True

    # 5. Static Files Directory
    static_root = getattr(settings, 'STATIC_ROOT', None)
    if static_root and os.path.exists(static_root) and os.path.isdir(static_root) and len(os.listdir(static_root)) > 0:
        print_result("Static Files (STATIC_ROOT)", True)
    else:
        print_result("Static Files (STATIC_ROOT)", False, "Directory missing or empty. Did you run collectstatic?")
        failed = True
        
    # 6. Superuser exists
    User = get_user_model()
    try:
        if User.objects.filter(is_superuser=True).exists():
            print_result("Superuser Check", True)
        else:
            print_result("Superuser Check", False, "No superuser found in database")
            failed = True
    except Exception as e:
        print_result("Superuser Check", False, str(e))
        failed = True

    print("-" * 50)
    if failed:
        print(f"{RED}Production readiness checks FAILED.{RESET}")
        sys.exit(1)
    else:
        print(f"{GREEN}All systems GO! Production readiness checks PASSED.{RESET}")
        sys.exit(0)

if __name__ == "__main__":
    run_checks()
