from django.contrib import admin
from django.urls import path
from app.views import (
    index,
    today_plan,
    achievements_page,
    delete_note,
    snooze_note,
    api_dashboard_stats,
    api_ai_recommendation,
    api_today_plan,
    api_achievements,
    api_notes_list,
    api_voice_note_parse,
    api_note_detail,
    api_snooze_note,
    api_mark_completed_note,
    api_mark_pending_note,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', index, name='home'),
    path('today-plan/', today_plan, name='today_plan'),
    path('achievements/', achievements_page, name='achievements'),
    path('delete/<int:note_id>/', delete_note, name='delete_note'),
    path('snooze/<int:note_id>/', snooze_note, name='snooze_note'),
    path('api/dashboard/stats/', api_dashboard_stats, name='api_dashboard_stats'),
    path('api/ai-recommendation/', api_ai_recommendation, name='api_ai_recommendation'),
    path('api/today-plan/', api_today_plan, name='api_today_plan'),
    path('api/achievements/', api_achievements, name='api_achievements'),
    path('api/notes/', api_notes_list, name='api_notes_list'),
    path('api/voice-note/parse/', api_voice_note_parse, name='api_voice_note_parse'),
    path('api/notes/<int:note_id>/', api_note_detail, name='api_note_detail'),
    path('api/notes/<int:note_id>/snooze/', api_snooze_note, name='api_snooze_note'),
    path('api/notes/<int:note_id>/complete/', api_mark_completed_note, name='api_mark_completed_note'),
    path('api/notes/<int:note_id>/pending/', api_mark_pending_note, name='api_mark_pending_note'),
]
