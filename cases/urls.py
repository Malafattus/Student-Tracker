from django.urls import path

from .views import (
    AddStudentCommunicationView,
    AddStudentDocumentView,
    AddStudentNoteView,
    AddStudentTaskView,
    DashboardView,
    ReportsView,
    StudentCreateView,
    StudentDetailView,
    StudentListView,
    StudentUpdateView,
    TaskListView,
    UserManagementView,
    UserUpdateView,
)

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("students/", StudentListView.as_view(), name="student_list"),
    path("students/new/", StudentCreateView.as_view(), name="student_create"),
    path("students/<int:pk>/", StudentDetailView.as_view(), name="student_detail"),
    path("students/<int:pk>/edit/", StudentUpdateView.as_view(), name="student_update"),
    path("students/<int:pk>/notes/add/", AddStudentNoteView.as_view(), name="student_note_add"),
    path("students/<int:pk>/tasks/add/", AddStudentTaskView.as_view(), name="student_task_add"),
    path("students/<int:pk>/documents/add/", AddStudentDocumentView.as_view(), name="student_document_add"),
    path(
        "students/<int:pk>/communications/add/",
        AddStudentCommunicationView.as_view(),
        name="student_communication_add",
    ),
    path("tasks/", TaskListView.as_view(), name="task_list"),
    path("reports/", ReportsView.as_view(), name="reports"),
    path("users/", UserManagementView.as_view(), name="user_management"),
    path("users/<int:pk>/edit/", UserUpdateView.as_view(), name="user_update"),
]
