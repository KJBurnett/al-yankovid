import re
from dataclasses import dataclass, field
from typing import Optional, Any

import signal_manager
import config


@dataclass
class YankRequest:
    url: str
    user_id: str
    batch_id: Optional[str]
    reply_context: Any  # SignalReplyContext | RocketChatReplyContext


@dataclass
class SignalReplyContext:
    process: Any
    group_id: Optional[str]
    recipient_number: Optional[str]
    user_id: str
    source_id: str
    service: str = "signal"

    def send(self, message, attachments=None):
        signal_manager.send_message(self.process, self.group_id, self.user_id, message, attachments)

    def upload_limit_mb(self) -> int:
        return config.UPLOAD_LIMIT_MB


@dataclass
class RocketChatReplyContext:
    manager: Any  # RocketChatManager
    room_id: str
    user_id: str    # RC username (folder/stats key)
    source_id: str  # RC immutable _id
    service: str = "rocketchat"

    def send(self, message, attachments=None):
        self.manager.send(self.room_id, message, attachments)

    def upload_limit_mb(self) -> int:
        return self.manager.max_upload_mb


def parse_command(message_text, is_mentioned, is_dm):
    """Classify an incoming message into a CommandIntent tuple.

    Returns one of:
      ('delete', url)
      ('yank', [urls])
      ('stats',)
      ('conversational',)
      ('greeting',)
      ('sites',)
      ('ignore',)
    """
    # Delete
    delete_match = re.search(r'(?:Al\s+delete|delete)\s+(https?://\S+)', message_text, re.IGNORECASE)
    if delete_match:
        return ('delete', delete_match.group(1))

    # URL extraction
    tokens = re.split(r'[\s,]+', message_text)
    urls = [t.strip('.,;') for t in tokens if re.match(r'https?://', t)]
    is_yank = bool(re.search(r'\b(?:Yank|Yoink)\b', message_text, re.IGNORECASE))

    if (is_yank or is_mentioned or is_dm) and urls:
        return ('yank', urls)

    # Stats
    if re.search(r'\b(Al,?\s+stats|stats,?\s+Al)\b', message_text, re.IGNORECASE) or \
       (is_mentioned and re.search(r'\bstats\b', message_text, re.IGNORECASE)):
        return ('stats',)

    # Conversational
    if re.search(r"\bAl,?\s+(how\s+are\s+you|how's\s+it\s+going|what's\s+up|howdy)\b", message_text, re.IGNORECASE) or \
       re.search(r"\b(how\s+are\s+you|how's\s+it\s+going|what's\s+up|howdy),?\s+Al\b", message_text, re.IGNORECASE) or \
       (is_mentioned and re.search(r"\b(how\s+are\s+you|how's\s+it\s+going|what's\s+up|howdy)\b", message_text, re.IGNORECASE)):
        return ('conversational',)

    # Greeting
    if re.search(r'\b(Al,?\s+(hi|hello|hey|yo|howdy)|(hi|hello|hey|yo|howdy)\s+,?Al)\b', message_text, re.IGNORECASE) or \
       (is_mentioned and re.search(r'\b(hi|hello|hey|yo|howdy)\b', message_text, re.IGNORECASE)):
        return ('greeting',)

    # Sites
    if re.search(r'\b(Al,?\s+sites|sites,?\s+Al)\b', message_text, re.IGNORECASE) or \
       (is_mentioned and re.search(r'\bsites\b', message_text, re.IGNORECASE)):
        return ('sites',)

    return ('ignore',)
