from django.db import models
from django.conf import settings
import uuid
# We assume the Room model is available in the 'ho_ho_hotel_app'
# You may need to adjust this import based on your actual structure
from ho_ho_hotel_app.models import Room 

class Payment(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending Payment'),
        ('PAID', 'Payment Successful'),
        ('FAILED', 'Payment Failed'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Link to the user making the payment
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payments')
    
    # Link to the room being booked
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='payments')

    # Razorpay Details
    razorpay_order_id = models.CharField(max_length=100, unique=True, blank=True, null=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=250, blank=True, null=True)

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='INR')
    
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)
        verbose_name = "Room Payment"

    def __str__(self):
        return f"Payment for Room {self.room.room_number} - Status: {self.status}"
