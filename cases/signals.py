from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import AuditLog, CommunicationLog, DocumentRequirement, FollowUpTask, Student, StudentNote


@receiver(post_delete, sender=Student)
@receiver(post_delete, sender=StudentNote)
@receiver(post_delete, sender=FollowUpTask)
@receiver(post_delete, sender=DocumentRequirement)
@receiver(post_delete, sender=CommunicationLog)
def log_delete(sender, instance, **kwargs):
    """Keep a lightweight delete trail even when the acting user is unavailable."""

    AuditLog.objects.create(
        action="deleted",
        model_name=sender.__name__,
        object_id=getattr(instance, "pk", None),
        object_repr=str(instance),
        details={},
    )
