from .models import AuditLog


def log_audit(actor, action, instance, details=None):
    AuditLog.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        model_name=instance.__class__.__name__,
        object_id=instance.pk,
        object_repr=str(instance),
        details=details or {},
    )
