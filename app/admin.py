from django.contrib import admin

from .models import Achievement, Note


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'text',
        'priority',
        'category',
        'repeat_type',
        'repeat_interval',
        'remind_at',
        'next_reminder_date',
        'sent',
        'completed',
        'completed_at',
        'status_label',
        'snoozed_count',
        'last_snoozed_at',
        'created_at',
    )
    list_filter = ('priority', 'category', 'repeat_type', 'sent', 'completed', 'created_at')
    search_fields = ('text', 'description')
    readonly_fields = ('created_at', 'snoozed_count', 'last_snoozed_at', 'completed_at')
    ordering = ('-id',)



@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    list_display = ('id', 'icon', 'title', 'code', 'unlocked', 'unlocked_at', 'created_at')
    list_filter = ('unlocked', 'color', 'created_at')
    search_fields = ('title', 'description', 'code')
    readonly_fields = ('created_at', 'unlocked_at')
    ordering = ('id',)
