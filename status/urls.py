from django.urls import path

from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('fragment/', views.dashboard_fragment, name='dashboard_fragment'),
    path('api/', views.dashboard_json, name='dashboard_json'),
]
