from django.conf import settings
from django_hosts import patterns, host

host_patterns = patterns('',
    host('', settings.ROOT_URLCONF, name='www'),
    host(r'^m', settings.ROOT_URLCONF, name='mobile'),
)