from django.contrib import admin
from .models import Event

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ['title', 'created_by', 'start_time', 'end_time', 'created_at']
    list_filter = ['start_time', 'created_by', 'created_at']
    search_fields = ['title', 'description', 'created_by__username']
    date_hierarchy = 'start_time'
    ordering = ['-start_time']
    
    fieldsets = (
        ('Event Information', {
            'fields': ('title', 'description')
        }),
        ('Schedule', {
            'fields': ('start_time', 'end_time')
        }),
        ('User', {
            'fields': ('created_by',)
        }),
    )