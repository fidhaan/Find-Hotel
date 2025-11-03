from django.urls import path
from . import views
from .views import CreateOrderView, PaymentVerifyView

urlpatterns = [
    # 1. URL to initiate the checkout process and create the Razorpay order.
    # It expects the UUID of the room being booked.
    path('checkout/<uuid:room_id>/', views.CreateOrderView.as_view(), name='checkout_room'),
    path('orders/', views.UserOrderView.as_view(), name='user_orders'),
    path('verify/', views.PaymentVerifyView.as_view(), name='payment_verify'),
]