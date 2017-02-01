"""All utils for the WeGovNow extension."""

from django.utils.text import slugify
from django.contrib.sites.models import Site

from allauth_uwum.views import UWUMAdapter, UWUMView

from geokey.users.models import User


def get_uwum_view(request):
    """Get the UWUM view (with adapter) passing the request."""
    view = UWUMView()
    view.request = request
    view.adapter = UWUMAdapter(view.request)
    return view


def make_email(username):
    """Make email address."""
    return '{username}@user.{domain}'.format(
        username=slugify(username),
        domain=Site.objects.get_current().domain)


def generate_fake_email(username):
    """Generate fake email for the UWUM user."""
    email = make_email(username)

    suffix = 2
    while User.objects.filter(email=email).exists():
        email = make_email('%s %s' % (username, suffix))
        suffix += 1

    return email
