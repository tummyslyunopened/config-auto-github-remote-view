from django.urls import path

from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('fragment/', views.dashboard_fragment, name='dashboard_fragment'),
    path('api/', views.dashboard_json, name='dashboard_json'),
    path('queue/<str:item_id>/priority', views.queue_priority, name='queue_priority'),
    path('queue/<str:item_id>/pause',    views.queue_pause,    name='queue_pause'),
    path('queue/<str:item_id>/resume',   views.queue_resume,   name='queue_resume'),
    path('queue/<str:item_id>/cancel',   views.queue_cancel,   name='queue_cancel'),
]
