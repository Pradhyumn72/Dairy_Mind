"""
Authentication views for login, logout, and registration.
"""
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import transaction
from django.urls import reverse

from .models import Profile


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
        
    if request.method == "POST":
        u = request.POST.get("username")
        p = request.POST.get("password")
        user = authenticate(request, username=u, password=p)
        if user is not None:
            login(request, user)
            return redirect("dashboard")
        else:
            messages.error(request, "Invalid username or password.")
            
    return render(request, "accounts/login.html")


def logout_view(request):
    logout(request)
    return redirect("login")


@transaction.atomic
def register_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
        
    if request.method == "POST":
        u = request.POST.get("username")
        p = request.POST.get("password")
        e = request.POST.get("email", "")
        f = request.POST.get("farm_name", "")
        ph = request.POST.get("phone", "")
        
        if User.objects.filter(username=u).exists():
            messages.error(request, "Username already exists.")
        else:
            user = User.objects.create_user(username=u, password=p, email=e)
            # Profile is automatically created by the post_save signal
            user.profile.role = Profile.Role.OWNER
            user.profile.farm_name = f
            user.profile.phone = ph
            user.profile.save()
            
            login(request, user)
            messages.success(request, f"Welcome to DairyMind, {f}!")
            return redirect("dashboard")
            
    return render(request, "accounts/register.html")
