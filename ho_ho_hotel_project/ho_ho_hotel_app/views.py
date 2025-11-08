from django.shortcuts import render, redirect, get_object_or_404
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_POST
from django.views.generic.edit import CreateView
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
import json, uuid, decimal

class HomePageView(View):
    
    def get(self, request, *args, **kwargs):
        return render(request, 'ho_ho_hotel_app/home-page.html')

class HotelOwnerRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    
    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            messages.error(self.request, "You must be a registered hotel owner to access this page.")
            return redirect(reverse_lazy('home'))
        return super().handle_no_permission()    
    
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_hotel_owner

class RoomCreateView(HotelOwnerRequiredMixin, CreateView):
    
    model = Room
    form_class = RoomForm
    template_name = 'ho_ho_hotel_app/add_room.html'    
    success_url = reverse_lazy('home')
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        try:
            owner_hotel = Hotel.objects.get(owner=self.request.user)
            kwargs['hotel'] = owner_hotel 
        except Hotel.DoesNotExist:
            kwargs['hotel'] = None
        return kwargs
    
    def form_valid(self, form):
        try:
            owner_hotel = Hotel.objects.get(owner=self.request.user)
        except Hotel.DoesNotExist:
            messages.error(self.request, "Error: You do not have a registered hotel linked to your account.")
            return redirect(reverse_lazy('home'))     
        form.instance.hotel = owner_hotel        
        response = super().form_valid(form)        
        messages.success(self.request, f"Room {self.object.room_number} ({self.object.room_type}) successfully added!")        
        return response
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
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
        
        return self.request.user.is_hotel_owner

    def handle_no_permission(self):
        
        return HttpResponseForbidden("You are not authorized to view this page.")

    def get_context_data(self, **kwargs):
        
        context = super().get_context_data(**kwargs)
        user = self.request.user

        try:
            owner_hotel = Hotel.objects.get(owner=user)
            context['hotel'] = owner_hotel
            context['hotel_registered'] = True
            rooms = Room.objects.filter(hotel=owner_hotel).order_by('room_number')
            context['rooms'] = rooms
        except Hotel.DoesNotExist:
            context['hotel_registered'] = False
            context['message'] = 'You need to register your hotel details first before adding rooms.'

        return context
    
class OwnerRoomUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    
    model = Room
    form_class = RoomForm 
    template_name = 'ho_ho_hotel_app/room_edit.html'
    context_object_name = 'room'    
    success_url = reverse_lazy('owner_room_list') 

    def test_func(self):        
        if not self.request.user.is_hotel_owner:
            return False        
        
        try:
            room = self.get_object()
            owner_hotel = Hotel.objects.get(owner=self.request.user)
            return room.hotel == owner_hotel
        except Hotel.DoesNotExist:
            return False
        except Room.DoesNotExist:
            return False

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        room = self.object
        all_reviews = room.reviews.all().select_related('user').order_by('-created_at')
        avg_rating_data = all_reviews.aggregate(Avg('rating'))
        avg_rating = avg_rating_data['rating__avg']
        context['reviews'] = all_reviews
        context['avg_rating'] = round(avg_rating, 2) if avg_rating is not None else 0.0
        context['review_count'] = all_reviews.count()
        return context

    def handle_no_permission(self):
        return HttpResponseForbidden("You are not authorized to edit this room or it does not belong to your hotel.")

class OwnerRoomDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    
    model = Room
    template_name = 'ho_ho_hotel_app/room_confirm_delete.html' 
    context_object_name = 'room'
    success_url = reverse_lazy('owner_room_list') 

    def test_func(self):
        user = self.request.user
        if not hasattr(user, 'is_hotel_owner') or not user.is_hotel_owner:
            return False
        try:
            room = self.get_object()
            owner_hotel = Hotel.objects.filter(owner=user).first()
            return owner_hotel is not None and room.hotel == owner_hotel
        except Exception:
            return False

    def handle_no_permission(self):
        messages.error(self.request, "You are not authorized to delete this room or it does not belong to your hotel.")
        return redirect(reverse_lazy('owner_room_list')) 

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        room_number = self.object.room_number
        room_type = self.object.room_type
        response = super().delete(request, *args, **kwargs)
        messages.success(request, f"Room {room_number} ({room_type}) has been successfully deleted.")
        return response
    
class RoomSearchView(ListView):
    
    model = Room
    template_name = 'ho_ho_hotel_app/room_search_page.html' 
    context_object_name = 'rooms'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            favorited_room_ids = Favourite.objects.filter(
                user=self.request.user
            ).values_list('room_id', flat=True)
            context['favorited_room_ids'] = [str(uuid) for uuid in favorited_room_ids]
        else:
            context['favorited_room_ids'] = []
        return context

class RoomResultsView(ListView):
    
    model = Room
    template_name = 'ho_ho_hotel_app/room_results_list.html'
    context_object_name = 'rooms'
    paginate_by = 10 

    def get_queryset(self):
        
        queryset = self.model.objects.none()        
        form = RoomSearchForm(self.request.GET)         
        if form.is_valid():
            query = form.cleaned_data.get('query')                        
            if query:
                queryset = self.model.objects.filter(is_available=True)
                q_objects = Q()
                q_objects |= Q(hotel__hotel_name__icontains=query)
                q_objects |= Q(hotel__place__icontains=query)
                q_objects |= Q(room_type__icontains=query)
                q_objects |= Q(room_number__iexact=query)                 
                
                try:
                    search_price = Decimal(query.strip())
                    q_objects |= Q(price_per_night__lte=search_price)
                except (decimal.InvalidOperation, ValueError):
                    pass
                
                queryset = queryset.filter(q_objects)
        
        
        return queryset.order_by('price_per_night', 'room_number')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
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

    model = Room 
    template_name = 'ho_ho_hotel_app/favourite_rooms.html'
    context_object_name = 'favourite_rooms' 
    paginate_by = 10 

    def get_queryset(self):

        user_favourites = Favourite.objects.filter(user=self.request.user)
        
        favourite_room_ids = user_favourites.values_list('room_id', flat=True)

        queryset = Room.objects.filter(id__in=favourite_room_ids)
        
        return queryset
    
class RoomDetailView(DetailView):
    model = Room
    template_name = 'ho_ho_hotel_app/room_detail.html'
    context_object_name = 'room'
    pk_url_kwarg = 'pk' 

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        room = self.object

        
        all_reviews = room.reviews.all().select_related('user')
        avg_rating = all_reviews.aggregate(Avg('rating'))['rating__avg']

        context['reviews'] = all_reviews
        context['avg_rating'] = avg_rating if avg_rating is not None else 0
        context['review_count'] = all_reviews.count()
        
        context['can_review'] = False
        context['has_reviewed'] = False
        
        if self.request.user.is_authenticated and not self.request.user.is_anonymous:
            user = self.request.user
            
          
            has_paid_booking = Payment.objects.filter(
                user=user, 
                room=room, 
                status='PAID'
            ).exists()
            
           
            has_reviewed = Review.objects.filter(
                user=user, 
                room=room
            ).exists()
            
            context['has_reviewed'] = has_reviewed
            
          
            if has_paid_booking and not has_reviewed:
                context['can_review'] = True
                
        return context


class ReviewSubmissionView(LoginRequiredMixin, View):
   
    
    def post(self, request, room_id):
       
        room = get_object_or_404(Room, id=room_id)
        
        
        user = request.user
        
        
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
            
        
        try:
            rating = int(request.POST.get('rating')) 
            comment = request.POST.get('comment', '').strip()
            
            if not 1 <= rating <= 5:
                raise ValueError("Rating must be between 1 and 5.")

            
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