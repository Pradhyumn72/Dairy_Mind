"""
HTML page views for the DairyMind frontend.
Each view renders a template that extends base.html.
These are separate from the REST API views in views.py.
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.utils.decorators import method_decorator
from django.views import View


# ── Decorator shortcut ────────────────────────────────────────────────────────
_login = login_required(login_url='/login/')


@method_decorator(_login, name='dispatch')
class DashboardPageView(View):
    def get(self, request):
        return render(request, 'dashboard.html', {'page_title': 'Dashboard'})


@method_decorator(_login, name='dispatch')
class CattlePageView(View):
    def get(self, request):
        return render(request, 'cattle/index.html', {'page_title': 'Cattle Registry'})


@method_decorator(_login, name='dispatch')
class CattleAddPageView(View):
    """GET /cattle/add/ — render the add cattle form."""
    def get(self, request):
        return render(request, 'cattle/add.html', {
            'page_title': 'Add Cattle',
            'nav_cattle': 'active',
        })


@method_decorator(_login, name='dispatch')
class CattleEditPageView(View):
    """GET /cattle/<pk>/edit/ — render the edit cattle form."""
    def get(self, request, pk):
        return render(request, 'cattle/edit.html', {
            'page_title': 'Edit Cattle',
            'nav_cattle': 'active',
            'cattle_id': pk,
        })


@method_decorator(_login, name='dispatch')
class CattleDetailPageView(View):
    """GET /cattle/<pk>/ — cattle detail page."""
    def get(self, request, pk):
        return render(request, 'cattle/detail.html', {
            'page_title': 'Cattle Detail',
            'nav_cattle': 'active',
            'cattle_id': pk,
        })


@method_decorator(_login, name='dispatch')
class MilkPageView(View):
    def get(self, request):
        return render(request, 'milk/index.html', {'page_title': 'Milk Tracker'})


@method_decorator(_login, name='dispatch')
class MilkLogPageView(View):
    """GET /milk/log/ — log milk production form."""
    def get(self, request):
        return render(request, 'milk/log.html', {
            'page_title': 'Log Milk Production',
            'nav_milk': 'active',
        })


@method_decorator(_login, name='dispatch')
class HealthPageView(View):
    def get(self, request):
        return render(request, 'health/index.html', {'page_title': 'Health Alerts'})


@method_decorator(_login, name='dispatch')
class ForecastPageView(View):
    def get(self, request):
        return render(request, 'forecast/index.html', {'page_title': 'Production Forecast'})


@method_decorator(_login, name='dispatch')
class VetReportPageView(View):
    def get(self, request):
        return render(request, 'vetreport/index.html', {'page_title': 'Vet Reports'})


@method_decorator(_login, name='dispatch')
class VetReportUploadPageView(View):
    """GET /vet-reports/upload/ — upload a vet report."""
    def get(self, request):
        return render(request, 'vetreport/upload.html', {
            'page_title': 'Upload Vet Report',
            'nav_vetreports': 'active',
        })


@method_decorator(_login, name='dispatch')
class CostsPageView(View):
    def get(self, request):
        return render(request, 'costs/index.html', {'page_title': 'Cost Optimizer'})


@method_decorator(_login, name='dispatch')
class FeedLogAddPageView(View):
    """GET /costs/feed/add/ — log feed cost form."""
    def get(self, request):
        return render(request, 'costs/feed_add.html', {
            'page_title': 'Log Feed Cost',
            'nav_costs': 'active',
        })


@method_decorator(_login, name='dispatch')
class BreedingPageView(View):
    def get(self, request):
        return render(request, 'breeding/index.html', {'page_title': 'Breeding Manager'})


@method_decorator(_login, name='dispatch')
class HeatCycleAddPageView(View):
    """GET /breeding/heat-cycles/add/ — quick-add heat cycle, optionally pre-selected cattle."""
    def get(self, request):
        return render(request, 'breeding/heat_add.html', {
            'page_title': 'Add Heat Cycle',
            'nav_breeding': 'active',
        })


@method_decorator(_login, name='dispatch')
class SettingsPageView(View):
    def get(self, request):
        return render(request, 'settings/index.html', {'page_title': 'Settings'})


@method_decorator(_login, name='dispatch')
class LogoutPageView(View):
    def get(self, request):
        from django.contrib.auth import logout
        logout(request)
        return redirect('login')
