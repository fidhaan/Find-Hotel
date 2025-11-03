from django.urls import path, include

from . import views

from django.contrib.auth import views as auth_views

urlpatterns=[

    path('register/', views.RegistrationView.as_view(), name='register'),

    path('login/', views.CustomLoginView.as_view(), name='login'),

    path('logout/', views.CustomLogoutView.as_view(), name='logout'),

    path('profile/', views.UserProfileView.as_view(), name='profile'),

    path('profile/password_change/', views.CustomPasswordChangeView.as_view(), name='password_change'),

    path('profile/edit/', views.UserUpdateView.as_view(), name='profile_edit'),

    path('profile/delete/', views.UserDeleteView.as_view(), name='profile_delete'),

    path('profile/password_request/', 
         views.SecurePasswordRequestView.as_view(), 
         name='secure_password_request'),
         
    path('profile/verify-change/', 
         views.OTPProtectedPasswordChangeView.as_view(), 
         name='otp_protected_password_change'), 

    path('reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='registration/password_reset_done.html'
    ), name='password_reset_done'),
    
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='registration/password_reset_confirm.html'
    ), name='password_reset_confirm'),
    
    path('reset/complete/', auth_views.PasswordResetCompleteView.as_view(
        template_name='registration/password_reset_complete.html'
    ), name='password_reset_complete'),

    path('register/owner/', views.HotelOwnerRegistrationView.as_view(), name='owner_register')
]
