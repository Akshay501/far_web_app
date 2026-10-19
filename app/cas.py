"""
Clarkson single sign-on via CAS (protocol 3.0).

The app never sees a password. The flow:

  1. login_url()      send the browser to {CAS}/login?service=<callback>
  2. the person signs in at Clarkson
  3. CAS redirects the browser to the callback with ?ticket=ST-...
  4. validate_ticket() asks CAS, server to server, whether that ticket
     is genuine, and gets back the NetID (plus any released attributes)

Step 4 is the security of the whole scheme: the browser carries the
ticket but never the answer, so nobody can name themselves by editing
a URL. The NetID returned here is the only identity the app trusts.

Written directly against the protocol with `requests` rather than a
library: about forty lines, every failure mode visible, and faked in
tests by monkeypatching `requests.get` (the same seam as the Scopus
sync).
"""
import re
from urllib.parse import urlencode
import xml.etree.ElementTree as ET

import requests

CAS_NS = {'cas': 'http://www.yale.edu/tp/cas'}

# Clarkson's EMPLID is always exactly 7 digits (Josh Fiske, 2026-10-15).
# Strict on purpose: carLicense is a re-used LDAP field, and a licence
# plate such as ABC1234 must never be stored as someone's employee ID.
# [0-9], not \d, which would also accept non-ASCII digits. The default
# for EMPLOYEE_ID_PATTERN; other institutions set their own.
CLARKSON_EMPLOYEE_ID = re.compile(r'^[0-9]{7}$')

# Hard timeout on the validation call (stats-hang law): a slow or dead
# CAS server must cost one failed login, never a hung worker.
CAS_TIMEOUT = 10


class CASError(Exception):
    """The ticket could not be confirmed. Nobody is logged in."""


class CASUnavailable(CASError):
    """CAS could not be reached or gave no usable answer."""


def login_url(cas_server, service):
    return f"{cas_server.rstrip('/')}/login?{urlencode({'service': service})}"


def logout_url(cas_server, service=None):
    base = f"{cas_server.rstrip('/')}/logout"
    return f"{base}?{urlencode({'service': service})}" if service else base


def validate_ticket(cas_server, ticket, service):
    """
    Confirm a service ticket with CAS. Returns (netid, attributes).

    `service` must be exactly the URL sent in login_url — CAS refuses
    the ticket otherwise. Raises CASError if CAS rejects the ticket and
    CASUnavailable if CAS cannot be reached or answers with something
    unusable; in every failure case nobody is logged in.
    """
    try:
        resp = requests.get(
            f"{cas_server.rstrip('/')}/p3/serviceValidate",
            params={'ticket': ticket, 'service': service},
            timeout=CAS_TIMEOUT)
    except requests.RequestException as exc:
        raise CASUnavailable(f'Could not reach CAS: {exc.__class__.__name__}')

    if resp.status_code != 200:
        raise CASUnavailable(f'CAS answered HTTP {resp.status_code}')

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError:
        raise CASUnavailable('CAS returned a response that is not XML')

    failure = root.find('cas:authenticationFailure', CAS_NS)
    if failure is not None:
        code = failure.get('code', 'UNKNOWN')
        raise CASError(f'CAS rejected the ticket ({code})')

    success = root.find('cas:authenticationSuccess', CAS_NS)
    user = success.find('cas:user', CAS_NS) if success is not None else None
    netid = (user.text or '').strip().lower() if user is not None else ''
    if not netid:
        raise CASUnavailable('CAS returned no username')

    attributes = {}
    attrs = success.find('cas:attributes', CAS_NS)
    if attrs is not None:
        for el in attrs:
            name = el.tag.split('}', 1)[-1]
            value = (el.text or '').strip()
            if name in attributes:
                # Multi-valued (e.g. memberOf: one element per group).
                if not isinstance(attributes[name], list):
                    attributes[name] = [attributes[name]]
                attributes[name].append(value)
            else:
                attributes[name] = value

    return netid, attributes


def employee_id_from(attributes, name, pattern=CLARKSON_EMPLOYEE_ID):
    """The employee ID CAS released under attribute `name`, or None.

    Clarkson releases it as carLicense (confirmed by Prof. Brian). A
    repeated attribute arrives as a list: the same value repeated is
    fine, two DIFFERENT values are ambiguous and give None - the app
    never guesses which one is right. Blank, or anything that does not
    match `pattern`, gives None."""
    raw = (attributes or {}).get(name)
    values = raw if isinstance(raw, list) else [raw]
    values = {str(v).strip() for v in values if v is not None}
    values.discard('')
    if len(values) != 1:
        return None
    value = values.pop()
    return value if pattern.match(value) else None
