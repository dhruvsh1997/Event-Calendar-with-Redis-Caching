from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('register/', views.register_view, name='register'),
    
    # API endpoints
    path('api/events/date/', views.get_events_for_date, name='get_events_for_date'),
    path('api/events/<int:event_id>/', views.get_event_detail, name='get_event_detail'),
    path('api/events/create/', views.create_event, name='create_event'),
    path('api/events/<int:event_id>/update/', views.update_event, name='update_event'),
    path('api/events/<int:event_id>/delete/', views.delete_event, name='delete_event'),
    path('api/events/search/', views.search_events, name='search_events'),
]