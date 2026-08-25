"""
Django HTML authentication views — login, logout, register.
These render templates and use Django's session auth.
REST API auth views are in api_views.py.
"""
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages
from django.db import transaction
from django.shortcuts import render, redirect


def login_view(request):
    """GET /login/  POST /login/ — sign-in form."""
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        # Only attempt auth when both fields are present
        if not username or not password:
            messages.error(request, "Please enter both username and password.")
        else:
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                next_url = request.GET.get("next", "/")
                return redirect(next_url)
            else:
                messages.error(request, "Incorrect username or password. Please try again.")

    return render(request, "accounts/login.html")


def logout_view(request):
    """GET /logout/ — clear session and redirect to login."""
    logout(request)
    return redirect("login")


from django.contrib.auth.decorators import login_required

@login_required(login_url='/login/')
@transaction.atomic
def profile_view(request):
    """GET/POST /profile/ — view and edit farmer profile details."""
    user    = request.user
    profile = user.profile

    if request.method == "POST":
        import re
        errors = []

        first_name = request.POST.get("first_name", "").strip()
        last_name  = request.POST.get("last_name", "").strip()
        email      = request.POST.get("email", "").strip()
        farm_name  = request.POST.get("farm_name", "").strip()
        phone      = request.POST.get("phone", "").strip()
        new_pw     = request.POST.get("new_password", "")
        confirm_pw = request.POST.get("confirm_password", "")

        # Validation
        if first_name and not re.match(r"^[A-Za-z\s]+$", first_name):
            errors.append("First name must contain only letters.")
        if last_name and not re.match(r"^[A-Za-z\s]+$", last_name):
            errors.append("Last name must contain only letters.")
        if email and email != user.email:
            if User.objects.filter(email=email).exclude(pk=user.pk).exists():
                errors.append("This email is already in use by another account.")
        if new_pw:
            if len(new_pw) < 8:
                errors.append("New password must be at least 8 characters.")
            elif new_pw != confirm_pw:
                errors.append("Passwords do not match.")

        if errors:
            for err in errors:
                messages.error(request, err)
        else:
            # Update Django User fields
            if first_name:
                user.first_name = first_name
            if last_name is not None:
                user.last_name = last_name
            if email:
                user.email = email
            if new_pw:
                user.set_password(new_pw)
            user.save()

            # Update Profile fields
            profile.farm_name = farm_name
            profile.phone     = phone
            profile.save(update_fields=["farm_name", "phone"])

            if new_pw:
                # Re-login after password change so session stays valid
                from django.contrib.auth import update_session_auth_hash
                update_session_auth_hash(request, user)

            messages.success(request, "Profile updated successfully!")
            return redirect("profile-page")

    return render(request, "accounts/profile.html", {
        "page_title": "My Profile",
    })


@transaction.atomic
def register_view(request):
    """GET /register/  POST /register/ — sign-up form."""
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        first_name    = request.POST.get("first_name", "").strip()
        last_name     = request.POST.get("last_name", "").strip()
        email         = request.POST.get("email", "").strip()
        username      = request.POST.get("username", "").strip()
        password      = request.POST.get("password", "")
        password_conf = request.POST.get("confirm_password", "")
        farm_name     = request.POST.get("farm_name", "").strip()

        # ── Validation ────────────────────────────────────────────────────────
        import re
        errors = []

        # First name: letters and spaces only
        if not first_name:
            errors.append("First name is required.")
        elif not re.match(r"^[A-Za-z\s]+$", first_name):
            errors.append("First name must contain only letters.")

        # Last name: letters and spaces only (optional but validate if provided)
        if last_name and not re.match(r"^[A-Za-z\s]+$", last_name):
            errors.append("Last name must contain only letters.")

        if not email:
            errors.append("Email is required.")

        # Username: alphanumeric + underscore only, 3–30 chars
        if not username:
            errors.append("Username is required.")
        elif not re.match(r"^[A-Za-z0-9_]{3,30}$", username):
            errors.append("Username must be 3–30 characters and contain only letters, numbers, or underscores.")

        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if password != password_conf:
            errors.append("Passwords do not match.")
        if username and User.objects.filter(username=username).exists():
            errors.append(f"Username '{username}' is already taken.")
        if email and User.objects.filter(email=email).exists():
            errors.append("An account with this email already exists.")

        if errors:
            for err in errors:
                messages.error(request, err)
            # Re-render with entered values preserved
            return render(request, "accounts/login.html", {
                "signup_active": True,
                "prefill": {
                    "first_name": first_name,
                    "last_name":  last_name,
                    "email":      email,
                    "username":   username,
                    "farm_name":  farm_name,
                },
            })

        # ── Create user ───────────────────────────────────────────────────────
        user = User.objects.create_user(
            username=username,
            password=password,
            email=email,
            first_name=first_name,
            last_name=last_name,
        )

        # Update profile (auto-created by post_save signal in models.py)
        profile = user.profile
        profile.farm_name = farm_name
        profile.save(update_fields=["farm_name"])

        login(request, user)
        messages.success(request, f"Welcome to DairyMind{', ' + farm_name if farm_name else ''}! Your account is ready.")
        return redirect("dashboard")

    return render(request, "accounts/login.html")
