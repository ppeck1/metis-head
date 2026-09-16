"""Read-only, provider-neutral external service connectors."""

from .calendar import CalendarConnector, CalendarEvent, CalendarTransport
from .contacts import Contact, ContactLookup, ContactResolution, ContactsConnector, ContactsTransport
from .contracts import (
    ConnectorError,
    ConnectorResult,
    ConnectorTransportError,
    ErrorCode,
    Freshness,
    Provenance,
    ResultStatus,
)
from .gmail import GmailConnector, GmailMessage, GmailSearchHit, GmailTransport
from .google_access import (
    GoogleAccount,
    GoogleBrokerRestoration,
    GoogleCalendar,
    GoogleReadBroker,
    GoogleReadGrant,
    GoogleRestoredAccount,
)
from .atlas import AtlasReadConnector, ProjectEvidence, ProjectIdentity, ProjectResolution, ProjectStatus
from .google_api import GOOGLE_READ_SCOPES, GoogleApiTransport, transports_from_connections
from .google_metadata import GOOGLE_ACCESS_METADATA_VERSION, GoogleAccountPolicy

__all__ = [
    "CalendarConnector",
    "CalendarEvent",
    "CalendarTransport",
    "Contact",
    "ContactLookup",
    "ContactResolution",
    "ContactsConnector",
    "ContactsTransport",
    "ConnectorError",
    "ConnectorResult",
    "ConnectorTransportError",
    "ErrorCode",
    "Freshness",
    "GmailConnector",
    "GmailMessage",
    "GmailSearchHit",
    "GmailTransport",
    "GoogleAccount",
    "GoogleCalendar",
    "GoogleBrokerRestoration",
    "GoogleReadBroker",
    "GoogleReadGrant",
    "GoogleRestoredAccount",
    "GoogleAccountPolicy",
    "GOOGLE_ACCESS_METADATA_VERSION",
    "AtlasReadConnector",
    "ProjectIdentity",
    "ProjectEvidence",
    "ProjectResolution",
    "ProjectStatus",
    "GOOGLE_READ_SCOPES",
    "GoogleApiTransport",
    "Provenance",
    "ResultStatus",
    "transports_from_connections",
]
