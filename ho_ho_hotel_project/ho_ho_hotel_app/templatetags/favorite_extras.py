from django import template
from ho_ho_hotel_app.models import Favourite
from ho_ho_hotel_app.models import Room # Import Room just in case
import uuid

register = template.Library()

@register.simple_tag(takes_context=True)
def is_favorited(context, room_id):
    """
    Checks if the given room_id (UUID or string) is favorited by the current user.
    Returns True or False.
    """
    user = context.get('user')
    
    # 1. Ensure user is logged in
    if not user or not user.is_authenticated:
        return False
        
    # 2. Convert room_id to UUID object safely
    try:
        if isinstance(room_id, str):
            room_uuid = uuid.UUID(room_id)
        elif isinstance(room_id, uuid.UUID):
            room_uuid = room_id
        else:
            return False
    except ValueError:
        return False
    
    # 3. Perform the check in Python
    return Favourite.objects.filter(user=user, room_id=room_uuid).exists()