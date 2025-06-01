import json
import logging
from datetime import datetime, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
from django.utils import timezone
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from .models import Event
import calendar

# Configure logger
logger = logging.getLogger('events.views')

def register_view(request):
    logger.info(f"User registration attempt. Method: {request.method}")
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get('username')
            logger.info(f"New user registered: {username}")
            messages.success(request, f'Account created for {username}!')
            return redirect('login')
        else:
            logger.warning(f"Registration form invalid for user: {request.POST.get('username')}")
    else:
        form = UserCreationForm()
        logger.debug("Rendering registration form")
    return render(request, 'events/register.html', {'form': form})

@login_required
def dashboard_view(request):
    logger.debug(f"Dashboard view accessed by user: {request.user.username}")
    current_date = timezone.now().date()
    current_month = current_date.month
    current_year = current_date.year
    
    # Get upcoming events (cached)
    cache_key = f"upcoming_events_{request.user.id}"
    upcoming_events = cache.get(cache_key)
    
    if upcoming_events is None:
        logger.info(f"Cache miss for upcoming events for user {request.user.id}")
        upcoming_events = Event.objects.filter(
            created_by=request.user,
            start_time__gte=timezone.now()
        ).order_by('start_time')[:5]
        cache.set(cache_key, list(upcoming_events.values()), 300)  # Cache for 5 minutes
        logger.debug(f"Cached upcoming events for user {request.user.id}")
    else:
        logger.debug(f"Cache hit for upcoming events for user {request.user.id}")
        # Convert back to Event objects for template
        upcoming_events = Event.objects.filter(
            id__in=[event['id'] for event in upcoming_events]
        ).order_by('start_time')
    
    context = {
        'upcoming_events': upcoming_events,
        'current_month': current_month,
        'current_year': current_year,
        'current_date': current_date,
    }
    logger.debug("Rendering dashboard template")
    return render(request, 'events/dashboard.html', context)

@login_required
@require_http_methods(["GET"])
def get_events_for_date(request):
    logger.debug(f"Fetching events for user: {request.user.username}")
    date_str = request.GET.get('date')
    if not date_str:
        logger.warning("Date parameter missing in get_events_for_date")
        return JsonResponse({'error': 'Date parameter required'}, status=400)
    
    try:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        logger.debug(f"Parsed date: {selected_date}")
    except ValueError as e:
        logger.error(f"Invalid date format: {date_str}. Error: {str(e)}")
        return JsonResponse({'error': 'Invalid date format'}, status=400)
    
    # Try to get from cache first
    cache_key = f"events_date_{request.user.id}_{date_str}"
    events_data = cache.get(cache_key)
    
    if events_data is None:
        logger.info(f"Cache miss for events on {date_str} for user {request.user.id}")
        print("Cache miss - fetch from database")
        events = Event.objects.filter(
            created_by=request.user,
            start_time__date=selected_date
        ).order_by('start_time')
        
        events_data = []
        for event in events:
            events_data.append({
                'id': event.id,
                'title': event.title,
                'description': event.description,
                'start_time': event.start_time.strftime('%H:%M'),
                'end_time': event.end_time.strftime('%H:%M'),
                'start_datetime': event.start_time.isoformat(),
                'end_datetime': event.end_time.isoformat(),
            })
        
        # Cache for 5 minutes
        cache.set(cache_key, events_data, 300)
        logger.debug(f"Cached events for {date_str} for user {request.user.id}")
    else:   
        logger.debug(f"Cache hit for events on {date_str} for user {request.user.id}")
        print("Cache Hit - return cached data")
    
    return JsonResponse({'events': events_data})

@login_required
def get_event_detail(request, event_id):
    logger.debug(f"Fetching event detail for event_id: {event_id}, user: {request.user.username}")
    # Try cache first
    cache_key = f"event_detail_{event_id}_{request.user.id}"
    event_data = cache.get(cache_key)

    if event_data is None:
        logger.info(f"Cache miss for event detail {event_id} for user {request.user.id}")
        event = get_object_or_404(Event, id=event_id, created_by=request.user)
        event_data = {
            'id': event.id,
            'title': event.title,
            'description': event.description,
            'start_time': event.start_time.strftime('%Y-%m-%d %H:%M'),
            'end_time': event.end_time.strftime('%Y-%m-%d %H:%M'),
            'created_at': event.created_at.strftime('%Y-%m-%d %H:%M'),
        }
        cache.set(cache_key, event_data, 300)
        logger.debug(f"Cached event detail {event_id} for user {request.user.id}")
    else:
        logger.debug(f"Cache hit for event detail {event_id} for user {request.user.id}")
    
    return JsonResponse(event_data)

@login_required
@require_http_methods(["POST"])
def create_event(request):
    logger.debug(f"Creating new event for user: {request.user.username}")
    try:
        data = json.loads(request.body)
        logger.debug(f"Received event data: {data}")
        
        # Create new event
        event = Event.objects.create(
            title=data['title'],
            description=data.get('description', ''),
            start_time=datetime.fromisoformat(data['start_time']),
            end_time=datetime.fromisoformat(data['end_time']),
            created_by=request.user
        )
        logger.info(f"Created event {event.id} for user {request.user.id}")
        
        # Invalidate related caches
        invalidate_user_caches(request.user.id, event.start_time.date())
        
        return JsonResponse({
            'success': True,
            'event': {
                'id': event.id,
                'title': event.title,
                'description': event.description,
                'start_time': event.start_time.isoformat(),
                'end_time': event.end_time.isoformat(),
            }
        })
    except Exception as e:
        logger.error(f"Error creating event: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

@login_required
@require_http_methods(["POST"])
def update_event(request, event_id):
    logger.debug(f"Updating event {event_id} for user: {request.user.username}")
    try:
        event = get_object_or_404(Event, id=event_id, created_by=request.user)
        data = json.loads(request.body)
        logger.debug(f"Received update data for event {event_id}: {data}")
        
        old_date = event.start_time.date()
        
        # Update event
        event.title = data['title']
        event.description = data.get('description', '')
        event.start_time = datetime.fromisoformat(data['start_time'])
        event.end_time = datetime.fromisoformat(data['end_time'])
        event.save()
        logger.info(f"Updated event {event_id} for user {request.user.id}")
        
        # Invalidate caches for both old and new dates
        invalidate_user_caches(request.user.id, old_date)
        invalidate_user_caches(request.user.id, event.start_time.date())
        
        return JsonResponse({'success': True})
    except Exception as e:
        logger.error(f"Error updating event {event_id}: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

@login_required
@require_http_methods(["DELETE"])
def delete_event(request, event_id):
    logger.debug(f"Deleting event {event_id} for user: {request.user.username}")
    try:
        event = get_object_or_404(Event, id=event_id, created_by=request.user)
        event_date = event.start_time.date()
        event.delete()
        logger.info(f"Deleted event {event_id} for user {request.user.id}")
        
        # Invalidate related caches
        invalidate_user_caches(request.user.id, event_date)
        
        return JsonResponse({'success': True})
    except Exception as e:
        logger.error(f"Error deleting event {event_id}: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

@login_required
def search_events(request):
    query = request.GET.get('q', '')
    logger.debug(f"Searching events with query '{query}' for user: {request.user.username}")
    if not query:
        logger.warning("Empty search query received")
        return JsonResponse({'events': []})
    
    # Try cache first
    cache_key = f"search_{request.user.id}_{hash(query)}"
    results = cache.get(cache_key)
    
    if results is None:
        logger.info(f"Cache miss for search query '{query}' for user {request.user.id}")
        events = Event.objects.filter(
            created_by=request.user
        ).filter(
            Q(title__icontains=query) | Q(description__icontains=query)
        ).order_by('-start_time')[:10]
        
        results = []
        for event in events:
            results.append({
                'id': event.id,
                'title': event.title,
                'description': event.description[:100] + '...' if len(event.description) > 100 else event.description,
                'start_time': event.start_time.strftime('%Y-%m-%d %H:%M'),
                'end_time': event.end_time.strftime('%Y-%m-%d %H:%M'),
            })
        
        cache.set(cache_key, results, 300)
        logger.debug(f"Cached search results for query '{query}' for user {request.user.id}")
    else:
        logger.debug(f"Cache hit for search query '{query}' for user {request.user.id}")
    
    return JsonResponse({'events': results})

def invalidate_user_caches(user_id, event_date):
    """Invalidate all relevant caches for a user when events change"""
    logger.debug(f"Invalidating caches for user {user_id} for date {event_date}")
    # Invalidate upcoming events cache
    cache.delete(f"upcoming_events_{user_id}")
    logger.debug(f"Deleted upcoming events cache for user {user_id}")
    
    # Invalidate specific date cache
    cache.delete(f"events_date_{user_id}_{event_date}")
    logger.debug(f"Deleted date-specific cache for user {user_id} on {event_date}")
    
    # Invalidate event detail caches (this is more complex in real scenarios)
    # For simplicity, we could use a pattern-based deletion or cache versioning