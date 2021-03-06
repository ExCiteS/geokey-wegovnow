"""All middleware for the WeGovNow extension."""

from importlib import import_module
from datetime import datetime
from pytz import utc

from django.core.urlresolvers import reverse
from django.shortcuts import redirect
from django.http import JsonResponse, HttpResponseRedirect
from django.contrib.auth import logout as auth_logout
from django.contrib import messages

from allauth.account.adapter import get_adapter
from allauth.socialaccount import providers
from allauth.socialaccount.models import SocialApp, SocialAccount, SocialToken
from allauth.socialaccount.providers.oauth2.client import OAuth2Error
from rest_framework import status

from geokey.users.views import AccountDisconnect

from geokey_wegovnow.utils import (
    get_uwum_view,
    generate_display_name,
    generate_fake_email,
)


class UWUMMiddleware(object):
    """UWUM middleware."""

    def _get_uwum_access_token(self, request):
        """Get the UWUM access token."""
        try:
            access_token = SocialToken.objects.filter(
                account__user=request.user,
                account__provider='uwum'
            ).latest('id')
        except SocialToken.DoesNotExist:
            return None

        if access_token.expires_at <= datetime.utcnow().replace(tzinfo=utc):
            # Refresh token if it has expired
            return self._refresh_uwum_access_token(request, access_token)
        else:
            # Otherwise validate it
            return self._validate_uwum_access_token(request, access_token)

    def _validate_uwum_access_token(self, request, access_token):
        """Validate the UWUM access token."""
        view = get_uwum_view(request)

        response = view.adapter.validate_user(access_token)
        if response.status_code == 200:
            response = response.json()
            extra_data = access_token.account.extra_data

            """
            Tricky part - compare current UWUM name not with display name, but
            with the previous UWUM name saved in the extra data of a social
            account. If it does not match, change it, but also update the extra
            data.

            Why? Because UWUM allows member names to be any, and GeoKey
            requires display names to be unique. That's why our display name
            (to avoid duplicates) can have a suffix (e.g. Ben 2, Kathy 17)
            added. Comparing generated display names would be way too
            difficult, but comparing previously set actual UWUM name (saved in
            the extra data) with the new one is a peace of cake!

            P.S. Ignore user emails - they're all fake. Get from extra data!
            """
            current_name = extra_data.get('member', {}).get('name')
            uwum_name = response.get('member', {}).get('name')
            if current_name != uwum_name:
                extra_data['member']['name'] = uwum_name
                access_token.account.extra_data = extra_data
                access_token.account.save()

                request.user.display_name = generate_display_name(uwum_name)
                request.user.email = generate_fake_email(uwum_name)
                request.user.save()

            self._update_uwum_notify_email(request, access_token)

            return access_token

        # Even if validation fails, try to refresh the token (last chance)
        return self._refresh_uwum_access_token(request, access_token)

    def _refresh_uwum_access_token(self, request, access_token):
        """Refresh the access token."""
        view = get_uwum_view(request)
        client = view.get_client(view.request, access_token.app)

        try:
            refreshed_token = client.refresh_access_token(
                access_token.token_secret)
        except OAuth2Error:
            return None

        refreshed_token = view.adapter.parse_token(refreshed_token)
        access_token.token = refreshed_token.token
        if refreshed_token.token_secret:
            access_token.token_secret = refreshed_token.token_secret
        access_token.expires_at = refreshed_token.expires_at
        access_token.save()

        return access_token

    def _update_uwum_notify_email(self, request, access_token):
        """
        Update the UWUM notify email.

        For WeGovNow project GeoKey users will store only fake emails within
        their user model instances. Actual email addresses will be updated, but
        stored in the extra data of a social account. This is only because
        GeoKey does not allow to have duplicate email addresses on the system,
        but UWUM does.
        """
        view = get_uwum_view(request)
        notify_email = view.adapter.get_notify_email(access_token)
        extra_data = access_token.account.extra_data

        if notify_email and extra_data['member']['email'] != notify_email:
            extra_data['member']['email'] = notify_email
            access_token.account.extra_data = extra_data
            access_token.account.save()

    def _validate_uwum_user(self, request):
        """Validate the UWUM user."""
        if hasattr(request, 'user') and not request.user.is_anonymous():
            # Do not validate UWUM users validated on the OAuth2 REST API
            # Do not validate twice - UWUM access token is attached to request
            if (not hasattr(request.user, 'uwum') and
                    not hasattr(request, 'uwum_access_token')):
                request.uwum_access_token = self._get_uwum_access_token(
                    request)

    def process_request(self, request):
        """
        Process the request.

        We can intercept anything before the request is being passed to the
        view. If something must be passed manually, it should be attached to
        the request. If the request is public API, it does not have a user but
        only the access token in the header (that's why there's additional user
        validation when processing the response).
        """
        self._validate_uwum_user(request)

        # Get the UWUM provider from the registry
        provider = providers.registry.by_id('uwum')

        try:
            # Look up the current UWUM social app
            app = SocialApp.objects.get_current(provider.id, request)
            # Get the client ID of that app
            client_id = app.client_id
        except SocialApp.DoesNotExist:
            client_id = None

        # Attach the client ID to the request (make available for the view)
        request.client_id = client_id

    def process_response(self, request, response):
        """
        Process the response.

        We can intercept anything after the response is generated by the view.
        It is also neccessary to valide the UWUM user one more time (though the
        method skips validation if it has been already done when processing the
        request) because public API requests have users added after the request
        is processed.
        """
        self._validate_uwum_user(request)

        # If user is signed in, `uwum_access_token` will always be present...
        if hasattr(request, 'uwum_access_token'):
            # ...but it can be `None` - that means user signed out of UWUM
            if not request.uwum_access_token:
                if request.META['PATH_INFO'].startswith('/api/'):
                    # For public API we just return the error response
                    return JsonResponse(
                        {'error': 'Invalid UWUM access token used'},
                        status=status.HTTP_401_UNAUTHORIZED)
                else:
                    # But for frontend views we need to log user out of GeoKey
                    auth_logout(request)
                    adapter = get_adapter(request)
                    return redirect(adapter.get_logout_redirect_url(request))

        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        """
        Process the view.

        Here it is possible to know what class is being used for the view. In
        this case, additional functionality intercept the "disconnecting social
        account" view, so that UWUM accounts could not be disconnected.
        """
        try:
            module = import_module(view_func.__module__)
            class_name = getattr(module, view_func.__name__)

            # Do not allow to disconnect UWUM account
            if issubclass(class_name, AccountDisconnect):
                try:
                    account = SocialAccount.objects.get(
                        pk=view_kwargs.get('account_id'),
                        user=request.user)
                    if account.provider == 'uwum':
                        messages.error(
                            request,
                            'The UWUM account cannot be disconnected.')
                        return HttpResponseRedirect(
                            reverse('admin:userprofile'))
                except:
                    pass
        except:
            pass
