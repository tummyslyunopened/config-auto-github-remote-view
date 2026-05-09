from django.urls import path, include

urlpatterns = [
    path('', include('status.urls')),
]
