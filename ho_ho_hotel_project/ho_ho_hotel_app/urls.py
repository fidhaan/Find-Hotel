from django.urls import path

from . import views

urlpatterns=[
    path('', views.HomePageView.as_view(), name='home'),
    path('owner/rooms/add/', views.RoomCreateView.as_view(), name='add_room'),
    path('rooms/edit/<uuid:pk>/', views.OwnerRoomUpdateView.as_view(), name='owner_room_edit'),
    path('rooms/delete/<uuid:pk>/', views.OwnerRoomDeleteView.as_view(), name='owner_room_delete'),
    path('rooms/search/', views.RoomSearchView.as_view(), name='room_search'),
    path('rooms/results/', views.RoomResultsView.as_view(), name='room_results'),
    path('favourites/toggle/', views.ToggleFavouriteView.as_view(), name='toggle_favourite'),
    path('favourites/', views.FavouriteRoomsView.as_view(), name='user_favourites'),
    path('room/<uuid:pk>/', views.RoomDetailView.as_view(), name='room_detail'),
    path('room/<uuid:room_id>/review/submit/', views.ReviewSubmissionView.as_view(), name='submit_review'),
    path('owner/rooms/', views.OwnerRoomListView.as_view(), name='owner_room_list')
]