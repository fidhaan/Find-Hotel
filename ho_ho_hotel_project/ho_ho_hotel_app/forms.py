from django import forms
from .models import Room
from django.core.exceptions import ValidationError

class RoomForm(forms.ModelForm):
    # Add an initializer to accept the 'hotel' instance
    def __init__(self, *args, **kwargs):
        # Pop the 'hotel' argument if present, it's not a model field
        self.hotel = kwargs.pop('hotel', None) 
        super().__init__(*args, **kwargs)

    # Custom clean method for room_number field
    def clean_room_number(self):
        room_number = self.cleaned_data.get('room_number')

        if self.hotel and room_number:
            # Check if a room with this number already exists for the given hotel
            if Room.objects.filter(hotel=self.hotel, room_number=room_number).exists():
                raise ValidationError(
                    f"A room with number '{room_number}' already exists for this hotel."
                )
        return room_number

    class Meta:
        model = Room
        # Exclude 'hotel' because the view sets it automatically based on the logged-in owner
        fields = [
            'room_number', 
            'room_type', 
            'price_per_night', 
            'max_occupancy', 
            'description', 
            'photo', 
            'is_available'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Describe amenities, views, and unique features.'}),
            'price_per_night': forms.NumberInput(attrs={'placeholder': 'Enter price (e.g., 150.00)'}),
        }
        labels = {
            'is_available': 'Ready for Booking',
        }

class RoomSearchForm(forms.Form):
    """Form with a single field for searching across multiple room attributes."""
    
    query = forms.CharField(
        max_length=100,
        required=False,
        label='Search Rooms',
        # 🌟 ADD THIS: Set the Bootstrap class for proper rendering 🌟
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter place, room number, type, or max price...',
            'class': 'form-control' # <--- CRITICAL ADDITION
        })
    )