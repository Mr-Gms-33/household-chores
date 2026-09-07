from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied

from .models import Household


def get_user_household(user):
    """Return the signed-in user's household, or None if they are not a member."""
    if not getattr(user, "is_authenticated", False):
        return None
    return Household.objects.filter(members=user).first()


def household_required(view_func):
    """Require login and membership in a household; attach it as request.household."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        household = get_user_household(request.user)
        if household is None:
            raise PermissionDenied
        request.household = household
        return view_func(request, *args, **kwargs)

    return login_required(_wrapped)


class HouseholdRequiredMixin(LoginRequiredMixin):
    """CBV mixin that sets request.household or returns 403."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        household = get_user_household(request.user)
        if household is None:
            raise PermissionDenied
        request.household = household
        return super().dispatch(request, *args, **kwargs)
