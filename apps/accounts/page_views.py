"""
HTML page views for the DairyMind frontend.
Each view renders a template that extends base.html.
These are separate from the REST API views in views.py.
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.utils.decorators import method_decorator
from django.views import View


class HomeRedirectView(View):
    """Redirect / to /dashboard/ or /login/ depending on auth state."""
    def get(self, request):
        if request.user.is_authenticated:
            return redirect('dashboard')
        return redirect('login')


@method_decorator(login_required(login_url='/login/'), name='dispatch')
class DashboardPageView(View):
    """GET / and GET /dashboard/ — main dashboard page."""
    def get(self, request):
        return render(request, 'dashboard.html', {
            'page_title': 'Dashboard',
            'nav_dashboard': 'active',
        })


@method_decorator(login_required(login_url='/login/'), name='dispatch')
class CattlePageView(View):
    def get(self, request):
        return render(request, 'cattle/index.html', {
            'page_title': 'Cattle Registry',
            'nav_cattle': 'active',
        })


@method_decorator(login_required(login_url='/login/'), name='dispatch')
class MilkPageView(View):
    def get(self, request):
        return render(request, 'milk/index.html', {
            'page_title': 'Milk Tracker',
            'nav_milk': 'active',
        })


@method_decorator(login_required(login_url='/login/'), name='dispatch')
class HealthPageView(View):
    def get(self, request):
        return render(request, 'health/index.html', {
            'page_title': 'Health Alerts',
            'nav_health': 'active',
        })


@method_decorator(login_required(login_url='/login/'), name='dispatch')
class ForecastPageView(View):
    def get(self, request):
        return render(request, 'forecast/index.html', {
            'page_title': 'Production Forecast',
            'nav_forecast': 'active',
        })


@method_decorator(login_required(login_url='/login/'), name='dispatch')
class VetReportPageView(View):
    def get(self, request):
        return render(request, 'vetreport/index.html', {
            'page_title': 'Vet Reports',
            'nav_vetreports': 'active',
        })


@method_decorator(login_required(login_url='/login/'), name='dispatch')
class CostsPageView(View):
    def get(self, request):
        return render(request, 'costs/index.html', {
            'page_title': 'Cost Optimizer',
            'nav_costs': 'active',
        })


@method_decorator(login_required(login_url='/login/'), name='dispatch')
class BreedingPageView(View):
    def get(self, request):
        return render(request, 'breeding/index.html', {
            'page_title': 'Breeding Manager',
            'nav_breeding': 'active',
        })


@method_decorator(login_required(login_url='/login/'), name='dispatch')
class SettingsPageView(View):
    def get(self, request):
        return render(request, 'settings/index.html', {
            'page_title': 'Settings',
            'nav_settings': 'active',
        })


class LoginPageView(View):
    """GET /login/ — login form page."""
    def get(self, request):
        if request.user.is_authenticated:
            return redirect('dashboard')
        return render(request, 'accounts/login.html', {
            'page_title': 'Sign In',
        })


@method_decorator(login_required(login_url='/login/'), name='dispatch')
class LogoutPageView(View):
    """GET /logout/ — logs out and redirects."""
    def get(self, request):
        from django.contrib.auth import logout
        logout(request)
        return redirect('login')
