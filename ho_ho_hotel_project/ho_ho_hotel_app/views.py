from django.shortcuts import render, redirect, get_object_or_404
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_POST
from django.views.generic.edit import CreateView
import json, uuid, decimal
from django.urls import reverse_lazy
from django.views.generic import ListView, View, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin, AccessMixin
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin 
from django.views.generic import TemplateView, UpdateView, DeleteView, ListView
from django.http import Http404, HttpResponseForbidden, JsonResponse, HttpResponseBadRequest
from login_app.models import Hotel 
from .models import Room, Favourite, Review
from django.contrib import messages
from .models import Room, Review
from .forms import RoomForm, RoomSearchForm
from login_app.models import Hotel
from django.db.models import Q
from payment.models import Payment
from django.db.models import Avg
from decimal import Decimal, InvalidOperation

class HomePageView(View):

    def get(self, request, *args, **kwargs):

        return render(request, 'ho_ho_hotel_app/home-page.html')

class HotelOwnerRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            # User is logged in but is not a hotel owner
            messages.error(self.request, "You must be a registered hotel owner to access this page.")
            return redirect(reverse_lazy('home')) # Redirect to home or a suitable unauthorized page
        
        # User is not logged in
        return super().handle_no_permission()
    
    def test_func(self):
        # 🚨 Crucial check: must be logged in AND an owner
        return self.request.user.is_authenticated and self.request.user.is_hotel_owner

class RoomCreateView(HotelOwnerRequiredMixin, CreateView):
    """
    Allows a verified Hotel Owner to add a new room to their registered hotel.
    """
    model = Room
    form_class = RoomForm
    template_name = 'ho_ho_hotel_app/add_room.html'  # Adjust template path as needed
    
    # After successful creation, redirect to the owner's room list or dashboard
    success_url = reverse_lazy('home') # 🚨 **Update this URL name** to your owner dashboard

    def get_form_kwargs(self):
        """Pass the owner's Hotel object to the RoomForm for unique validation."""
        kwargs = super().get_form_kwargs()
        try:
            owner_hotel = Hotel.objects.get(owner=self.request.user)
            # Pass the hotel instance to the form's __init__ method
            kwargs['hotel'] = owner_hotel 
        except Hotel.DoesNotExist:
            # Handle the case where the owner has no hotel
            # (The form_valid check will also catch this, but better to prevent form display if possible)
            kwargs['hotel'] = None # Pass None if no hotel is found
            # You might want to add a message or redirect here if no hotel is mandatory for the view
        return kwargs

    def form_valid(self, form):
        # 1. Find the Hotel object linked to the currently logged-in user (owner)
        try:
            owner_hotel = Hotel.objects.get(owner=self.request.user)
        except Hotel.DoesNotExist:
            # ... (rest of your existing error handling)
            messages.error(self.request, "Error: You do not have a registered hotel linked to your account.")
            return redirect(reverse_lazy('home')) 
        
        # 2. Automatically set the foreign key ('hotel' field in the Room model)
        form.instance.hotel = owner_hotel
        
        response = super().form_valid(form)
        
        messages.success(self.request, f"Room {self.object.room_number} ({self.object.room_type}) successfully added!")
        
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add the owner's hotel name to the context for a friendlier template title
        try:
            owner_hotel = Hotel.objects.get(owner=self.request.user)
            context['hotel_name'] = owner_hotel.hotel_name
        except Hotel.DoesNotExist:
            context['hotel_name'] = "No Hotel Registered"
            
        context['title'] = 'Add New Room'
        return context
    
class OwnerRoomListView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):

    template_name = 'ho_ho_hotel_app/owner_room_list.html'

    def test_func(self):
        """
        UserPassesTestMixin method: Checks if the user is authorized.
        """
        # 1. Authorization Check: Ensure the user is designated as a hotel owner
        return self.request.user.is_hotel_owner

    def handle_no_permission(self):
        """
        Returns a 403 Forbidden response if test_func fails.
        """
        return HttpResponseForbidden("You are not authorized to view this page.")

    def get_context_data(self, **kwargs):
        """
        Populates the context dictionary with the Hotel and Room data.
        """
        context = super().get_context_data(**kwargs)
        user = self.request.user

        try:
            # 2. Data Fetching: Retrieve the Hotel object linked to the current user
            # Since owner is a OneToOneField, we use .get()
            owner_hotel = Hotel.objects.get(owner=user)
            context['hotel'] = owner_hotel
            context['hotel_registered'] = True
            
            # 3. Fetch Rooms: Get all rooms linked via the ForeignKey (related_name='rooms')
            # Filtering by the retrieved hotel object
            rooms = Room.objects.filter(hotel=owner_hotel).order_by('room_number')
            context['rooms'] = rooms

        except Hotel.DoesNotExist:
            # Handle case where a hotel owner hasn't registered their hotel yet
            context['hotel_registered'] = False
            context['message'] = 'You need to register your hotel details first before adding rooms.'

        return context
    
class OwnerRoomUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """
    Allows a hotel owner to edit an existing Room instance belonging to their hotel
     and view its customer reviews.
    """
    model = Room
    form_class = RoomForm 
    template_name = 'ho_ho_hotel_app/room_edit.html'
    context_object_name = 'room'
    
    # Redirect to the room list after successful update
    success_url = reverse_lazy('owner_room_list') 

    def test_func(self):
        """
        1. Checks if the user is a hotel owner.
        2. Checks if the specific room being edited belongs to the user's registered hotel.
        """
        # 1. Must be a hotel owner
        if not self.request.user.is_hotel_owner:
            return False
        
        # 2. The room must belong to the user's hotel
        try:
            # Get the Room object being updated
            room = self.get_object()
            
            # Use the reverse relationship from CustomUser (if defined), 
            # or try to fetch the Hotel linked to the user.
            owner_hotel = Hotel.objects.get(owner=self.request.user)
            
            # Check if the room's hotel foreign key matches the owner's hotel
            return room.hotel == owner_hotel
        except Hotel.DoesNotExist:
            # If the user is an owner but hasn't registered a hotel, they can't edit rooms
            return False
        except Room.DoesNotExist:
            # If the room PK is invalid
            return False

    def get_context_data(self, **kwargs):
        """
        Adds reviews and rating summary to the context.
        """
        context = super().get_context_data(**kwargs)
        room = self.object
        
        # Fetch all reviews for this specific room
        all_reviews = room.reviews.all().select_related('user').order_by('-created_at')
        
        # Calculate the average rating
        avg_rating_data = all_reviews.aggregate(Avg('rating'))
        avg_rating = avg_rating_data['rating__avg']
        
        context['reviews'] = all_reviews
        context['avg_rating'] = round(avg_rating, 2) if avg_rating is not None else 0.0
        context['review_count'] = all_reviews.count()
        
        return context

    def handle_no_permission(self):
        """Returns a 403 Forbidden response if test_func fails."""
        return HttpResponseForbidden("You are not authorized to edit this room or it does not belong to your hotel.")

class OwnerRoomDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """
    Allows a verified hotel owner to delete a Room instance belonging to their hotel.
    Requires a POST request (submitted via the modal form).
    """
    model = Room
    # Set this to a dummy template name if you use a modal on a list page.
    # Django will still check for it, but the POST submission won't render it.
    template_name = 'ho_ho_hotel_app/room_confirm_delete.html' 
    context_object_name = 'room'
    
    # Redirect to the room list after successful deletion
    success_url = reverse_lazy('owner_room_list') 

    def test_func(self):
        """
        1. Checks if the user is a hotel owner.
        2. Checks if the specific room being deleted belongs to the user's registered hotel.
        """
        user = self.request.user
        
        # 1. Must be a hotel owner
        if not hasattr(user, 'is_hotel_owner') or not user.is_hotel_owner:
            return False
        
        # 2. The room must belong to the user's hotel
        try:
            room = self.get_object()
            # Use filter().first() to avoid Hotel.DoesNotExist if the owner doesn't have a linked hotel
            owner_hotel = Hotel.objects.filter(owner=user).first()
            
            # Check if the hotel exists AND if the room is linked to that hotel
            return owner_hotel is not None and room.hotel == owner_hotel
        except Exception:
             # Catch any database errors or missing room instances
            return False

    def handle_no_permission(self):
        """Custom handler for failed permission check."""
        messages.error(self.request, "You are not authorized to delete this room or it does not belong to your hotel.")
        # Redirect back to the room list or dashboard instead of a generic 403 page
        return redirect(reverse_lazy('owner_room_list')) 

    def delete(self, request, *args, **kwargs):
        """Custom deletion logic to add a success message."""
        
        # Save details before deletion for the success message
        self.object = self.get_object()
        room_number = self.object.room_number
        room_type = self.object.room_type
        
        # Call the base DeleteView's delete method to perform the actual deletion
        response = super().delete(request, *args, **kwargs)
        
        # Add success message after deletion
        messages.success(request, f"Room {room_number} ({room_type}) has been successfully deleted.")
        
        return response
    
class RoomSearchView(ListView): # Or your actual search view class
    model = Room
    template_name = 'ho_ho_hotel_app/room_search_page.html' # Use your actual template path
    context_object_name = 'rooms'
    
    # ... your existing get_queryset logic for searching ...

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # 🌟 CRITICAL FIX: Add the list of favorited room IDs to the context 🌟
        if self.request.user.is_authenticated:
            # 1. Fetch the Room IDs the current user has favourited
            # We use 'room_id' and flat=True to get a simple list of UUIDs/strings
            favorited_room_ids = Favourite.objects.filter(
                user=self.request.user
            ).values_list('room_id', flat=True)

            # 2. Convert UUIDs to strings before passing to template
            # The template converts room.id to string using stringformat:"s", so we match it here
            context['favorited_room_ids'] = [str(uuid) for uuid in favorited_room_ids]
        else:
            context['favorited_room_ids'] = [] # Empty list for unauthenticated users

        return context

class RoomResultsView(ListView):
    """Displays available rooms matching the single search query across multiple fields."""
    model = Room
    template_name = 'ho_ho_hotel_app/room_results_list.html'
    context_object_name = 'rooms'
    paginate_by = 10 

    def get_queryset(self):
        # Initialize an empty queryset initially
        queryset = self.model.objects.none()
        
        form = RoomSearchForm(self.request.GET) 
        
        # Check if the form is submitted AND has a query value
        if form.is_valid():
            query = form.cleaned_data.get('query')
            
            # --- CRITICAL CHANGE: Only proceed if a valid query string exists ---
            if query:
                # 1. Start with only available rooms (as the base)
                queryset = self.model.objects.filter(is_available=True)
                
                # Initialize Q object for OR lookups
                q_objects = Q()
                
                # --- Build the OR conditions (String-based matches) ---
                
                # 1. Match Place/Hotel Name
                q_objects |= Q(hotel__hotel_name__icontains=query)
                q_objects |= Q(hotel__place__icontains=query)

                # 2. Match Room Type
                q_objects |= Q(room_type__icontains=query)

                # 3. Match Room Number
                q_objects |= Q(room_number__iexact=query) 
                
                # 4. Handle Price Lookup
                try:
                    search_price = Decimal(query.strip())
                    
                    # This line implements the 'less than or equal to' logic (your requirement)
                    q_objects |= Q(price_per_night__lte=search_price)
                except (decimal.InvalidOperation, ValueError):
                    pass

                # Apply the combined OR filters to the queryset
                queryset = queryset.filter(q_objects)
        
        # If no query was submitted or it was empty, the queryset remains empty (objects.none())
        return queryset.order_by('price_per_night', 'room_number')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        # NOTE: RoomSearchForm needs to be imported or defined here
        context['form'] = RoomSearchForm(self.request.GET) 
        context['title'] = 'Search Results' 

        return context
    
@method_decorator(require_POST, name='dispatch')
class ToggleFavouriteView(LoginRequiredMixin, View):
    def handle_no_permission(self):
        if self.request.is_ajax() or self.request.content_type == 'application/json':
            return JsonResponse({
                'status': 'error',
                'message': 'Authentication required. Please log in.'
            }, status=403)
        return super().handle_no_permission()


    def post(self, request, *args, **kwargs):
        
        if not request.content_type == 'application/json':
            return HttpResponseBadRequest("Invalid content type.")
        
        try:
            data = json.loads(request.body)
            room_id_str = data.get('room_id')
            
            if not room_id_str:
                return JsonResponse({'status': 'error', 'message': 'Missing room_id'}, status=400)
            
            room_id = uuid.UUID(room_id_str)
            
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON or UUID format'}, status=400)

        try:
            room = Room.objects.get(pk=room_id)
        except Room.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Room not found.'}, status=404)

        user = request.user

        try:
            favourite = Favourite.objects.get(user=user, room=room)
            favourite.delete()
            is_loved = False
            message = "Room removed from favourites."

        except Favourite.DoesNotExist:
            Favourite.objects.create(user=user, room=room)
            is_loved = True
            message = "Room added to favourites."

        return JsonResponse({
            'status': 'success',
            'is_loved': is_loved,
            'message': message
        })
    
class FavouriteRoomsView(LoginRequiredMixin, ListView):

    model = Room # We are ultimately displaying a list of Rooms
    template_name = 'ho_ho_hotel_app/favourite_rooms.html'
    context_object_name = 'favourite_rooms' # The variable name in the template
    paginate_by = 10 # Optional: Add pagination for long lists

    def get_queryset(self):

        user_favourites = Favourite.objects.filter(user=self.request.user)
        
        favourite_room_ids = user_favourites.values_list('room_id', flat=True)

        queryset = Room.objects.filter(id__in=favourite_room_ids)
        
        return queryset
    
class RoomDetailView(DetailView):
    model = Room
    template_name = 'ho_ho_hotel_app/room_detail.html'
    context_object_name = 'room'
    pk_url_kwarg = 'pk' # The URL pattern uses 'pk'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        room = self.object

        # 1. Review Data
        all_reviews = room.reviews.all().select_related('user')
        avg_rating = all_reviews.aggregate(Avg('rating'))['rating__avg']

        context['reviews'] = all_reviews
        context['avg_rating'] = avg_rating if avg_rating is not None else 0
        context['review_count'] = all_reviews.count()
        
        # 2. Review Eligibility Check (for the current user)
        context['can_review'] = False
        context['has_reviewed'] = False
        
        if self.request.user.is_authenticated and not self.request.user.is_anonymous:
            user = self.request.user
            
            # CRITICAL CHECK 1: Check for PAID booking using only the 'user' field,
            # as confirmed by the FieldError choices.
            has_paid_booking = Payment.objects.filter(
                user=user, 
                room=room, 
                status='PAID'
            ).exists()
            
            # CRITICAL CHECK 2: Has the user already left a review for this room?
            has_reviewed = Review.objects.filter(
                user=user, 
                room=room
            ).exists()
            
            context['has_reviewed'] = has_reviewed
            
            # User can review if they have paid AND they haven't reviewed yet
            if has_paid_booking and not has_reviewed:
                context['can_review'] = True
                
        return context


class ReviewSubmissionView(LoginRequiredMixin, View):
    """Handles POST request for submitting a new room review."""
    
    def post(self, request, room_id):
        # 1. Validate Room and Eligibility
        room = get_object_or_404(Room, id=room_id)
        
        # Re-run eligibility check upon POST
        user = request.user
        
        # Correct check using only the 'user' field
        has_paid_booking = Payment.objects.filter(
            user=user, 
            room=room, 
            status='PAID'
        ).exists()
        
        has_reviewed = Review.objects.filter(
            user=user, 
            room=room
        ).exists()

        if not has_paid_booking or has_reviewed:
            messages.error(request, "You are not authorized to leave a review for this room.")
            return redirect('room_detail', pk=room.id)
            
        # 2. Get Form Data
        try:
            rating = int(request.POST.get('rating')) 
            comment = request.POST.get('comment', '').strip()
            
            if not 1 <= rating <= 5:
                raise ValueError("Rating must be between 1 and 5.")

            # 3. Save Review
            Review.objects.create(
                user=user,
                room=room,
                hotel=room.hotel,
                rating=rating,
                comment=comment
            )
            messages.success(request, "Thank you for your review! It has been posted.")
            
        except ValueError as e:
            messages.error(request, f"Invalid data submitted: {e}")
        except Exception as e:
            messages.error(request, "An unexpected error occurred while submitting your review. Please try again.")
            print(f"REVIEW SUBMISSION ERROR: {e}")

        return redirect('room_detail', pk=room.id)