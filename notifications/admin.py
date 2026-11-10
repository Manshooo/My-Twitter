from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
	list_display = ('created_at', 'recipient', 'actor', 'verb', 'read_at')
	list_filter = ('verb',)
	raw_id_fields = ('recipient', 'actor', 'post')
	search_fields = ('recipient__user__username', 'actor__user__username')
