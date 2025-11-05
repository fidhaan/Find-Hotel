from django.db import models

from login_app.models import Hotel, CustomUser
from django.urls import reverse
import uuid

class Room(models.Model):
    # Link the room to the Hotel instance
    hotel = models.ForeignKey(
        Hotel, 
        on_delete=models.CASCADE, 
        related_name='rooms'
    )
    
    room_number = models.CharField(max_length=10)
    room_type = models.CharField(
        max_length=50, 
        help_text="e.g., 'Penthouse Suite', 'Family Room', 'Studio'"
    )
    price_per_night = models.DecimalField(max_digits=600, decimal_places=2)
    max_occupancy = models.PositiveSmallIntegerField(default=2)
    description = models.TextField(blank=True)
    is_available = models.BooleanField(default=True)
    id = models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False
    )

    photo = models.ImageField(
        upload_to='room_photos/',
        blank=True,
        null=True,
        help_text="Upload a photo of the room."
    )

    def get_absolute_url(self):
        # Assuming your URL pattern for a single room is named 'room_detail' 
        # and takes the room's ID as a keyword argument.
        return reverse('room_detail', kwargs={'id': self.id})
    
    class Meta:
        # Ensures no two rooms have the same number within the same hotel
        unique_together = ('hotel', 'room_number') 
        verbose_name = "Hotel Room"
        verbose_name_plural = "Hotel Rooms"

    def __str__(self):
        return f"Room {self.room_number} ({self.get_room_type_display()}) at {self.hotel.hotel_name}"
    
class Favourite(models.Model):
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    
    # 1. Link to the User (UUID Foreign Key)
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='favourites',  # Allows you to access: user.favourites.all()
        verbose_name=('User')
    )
    
    # 2. Link to the Room (UUID Foreign Key)
    room = models.ForeignKey(
        Room,
        on_delete=models.CASCADE,
        related_name='favorited_by', # Allows you to access: room.favorited_by.all()
        verbose_name=('Room')
    )
    
    # Timestamp of when the favorite was added
    added_on = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Favourite Room"
        verbose_name_plural = "Favourite Rooms"
        # CRITICAL: Ensures a user can only favourite a room once
        unique_together = ('user', 'room') 
        ordering = ['-added_on']

    def __str__(self):
        # Safely return the ID if related objects are not found
        try:
            return f"Favourite by {self.user.username} for {self.room.room_number}"
        except AttributeError:
            return f"Favourite object {self.id}"
    
class Review(models.Model):
    # Rating options (1 to 5 stars)
    RATING_CHOICES = [
        (1, '1 - Poor'),
        (2, '2 - Fair'),
        (3, '3 - Good'),
        (4, '4 - Very Good'),
        (5, '5 - Excellent'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Links
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='reviews')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='reviews')
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='reviews') # Redundant but useful for filtering/analytics
    
    # Content
    rating = models.IntegerField(choices=RATING_CHOICES, help_text="Rating from 1 to 5.")
    comment = models.TextField(blank=True, null=True, help_text="Detailed review comment.")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Room Review"
        verbose_name_plural = "Room Reviews"
        ordering = ['-created_at']
        # IMPORTANT: Ensures one review per user per room.
        unique_together = ('user', 'room') 

    def __str__(self):
        # Safely return the ID if related objects are not found
        try:
            return f"Review by {self.user.username} for Room {self.room.room_number} ({self.rating} stars)"
        except AttributeError:
            return f"Review object {self.id}"
