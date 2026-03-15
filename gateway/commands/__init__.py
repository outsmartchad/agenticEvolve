"""Command mixins for TelegramAdapter.

Each mixin contains a group of related command handlers.
TelegramAdapter inherits from all mixins to compose the full command set.
"""
from .admin import AdminMixin
from .pipelines import PipelineMixin
from .signals import SignalsMixin
from .cron import CronMixin
from .approval import ApprovalMixin
from .search import SearchMixin
from .media import MediaMixin
from .misc import MiscMixin

__all__ = [
    "AdminMixin",
    "PipelineMixin",
    "SignalsMixin",
    "CronMixin",
    "ApprovalMixin",
    "SearchMixin",
    "MediaMixin",
    "MiscMixin",
]
