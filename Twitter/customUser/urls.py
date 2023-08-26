from django.urls import path
from .views import CustomSignUp

urlpatterns = [
	path('signup/', CustomSignUp.as_view(), name='signup')
]
