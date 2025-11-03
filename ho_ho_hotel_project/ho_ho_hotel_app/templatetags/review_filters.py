from django import template
import math

register = template.Library()

@register.filter
def star_range(rating):
    """
    Generates a list of star states (full, half, empty) for display.
    Example: star_range(3.5) -> ['full', 'full', 'full', 'half', 'empty']
    """
    star_states = []
    # Ensure rating is treated as float for math operations
    rating = float(rating) if rating is not None else 0.0
    
    for i in range(1, 6):
        if i <= math.floor(rating):
            # Full star
            star_states.append('full')
        elif i == math.ceil(rating) and rating % 1 != 0:
            # Half star (only if current star is the ceiling and rating is not an integer)
            star_states.append('half')
        else:
            # Empty star
            star_states.append('empty')
            
    return star_states
