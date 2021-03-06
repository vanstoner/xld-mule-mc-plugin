#
# THIS CODE AND INFORMATION ARE PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND, EITHER EXPRESSED OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE IMPLIED WARRANTIES OF MERCHANTABILITY AND/OR FITNESS
# FOR A PARTICULAR PURPOSE. THIS CODE AND INFORMATION ARE NOT SUPPORTED BY XEBIALABS.
#

# -*- coding: utf-8 -*-
"""The module containing the code for GuessAuth."""
from requests import auth
from requests import cookies


class GuessAuth(auth.AuthBase):
    """Guesses the auth type by the WWW-Authentication header."""
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.auth = None
        self.pos = None

    def handle_401(self, r, **kwargs):
        """Resends a request with auth headers, if needed."""

        www_authenticate = r.headers.get('www-authenticate', '').lower()

        if 'basic' in www_authenticate:
            if self.pos is not None:
                r.request.body.seek(self.pos)

            # Consume content and release the original connection
            # to allow our new request to reuse the same one.
            r.content
            r.raw.release_conn()
            prep = r.request.copy()
            if not hasattr(prep, '_cookies'):
                prep._cookies = cookies.RequestsCookieJar()
            cookies.extract_cookies_to_jar(prep._cookies, r.request, r.raw)
            prep.prepare_cookies(prep._cookies)

            self.auth = auth.HTTPBasicAuth(self.username, self.password)
            prep = self.auth(prep)
            _r = r.connection.send(prep, **kwargs)
            _r.history.append(r)
            _r.request = prep

            return _r

        if 'digest' in www_authenticate:
            self.auth = auth.HTTPDigestAuth(self.username, self.password)
            # Digest auth would resend the request by itself. We can take a
            # shortcut here.
            return self.auth.handle_401(r, **kwargs)

    def __call__(self, request):
        if self.auth is not None:
            return self.auth(request)

        try:
            self.pos = request.body.tell()
        except AttributeError:
            pass

        request.register_hook('response', self.handle_401)
        return request
