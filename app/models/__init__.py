"""
Models Package
Exports all models for easy access
"""
from app.models.base import BaseModel
from app.models.user import User
from app.models.user_gkach import UserGkach
from app.models.gkach_transaction import GkachTransaction
from app.models.ad import Ad
from app.models.cart import CartItem
from app.models.delivery import Delivery
from app.models.batch import Batch
from app.models.batch_click import BatchClick
from app.models.message import Message
from app.models.ad_interactions import AdLike, AdStar, AdComment, AdRating
from app.models.story import Story
from app.models.party import Party, PartyParticipant
from app.models.konferans import KonferansRoom, KonferansRecording
from app.models.charity import CharityDonation, CharityCause

try:
    from app.models.app_installation import AppInstallation
    _HAS_APPINSTALL = True
except Exception:
    AppInstallation = None
    _HAS_APPINSTALL = False

__all__ = [
    'BaseModel',
    'User',
    'UserGkach',
    'GkachTransaction',
    'Ad',
    'CartItem',
    'Delivery',
    'Batch',
    'BatchClick',
    'Message',
    'AdLike',
    'AdStar',
    'AdComment',
    'AdRating',
    'Story',
    'Party',
    'PartyParticipant',
    'KonferansRoom',
    'KonferansRecording',
]

if _HAS_APPINSTALL:
    __all__.append('AppInstallation')
__all__.extend(['CharityDonation', 'CharityCause'])


def __getattr__(name):
    """Lazy import for AppInstallation to avoid circular imports"""
    if name == 'AppInstallation':
        try:
            from app.models.app_installation import AppInstallation
            return AppInstallation
        except Exception as exc:
            raise ImportError(f"AppInstallation unavailable: {exc}") from exc
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
