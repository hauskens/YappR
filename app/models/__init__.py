from flask_sqlalchemy import SQLAlchemy

from .broadcaster import *
from .channel import *
from .content_queue_settings import *
from .auth import *
from .platform import *
from .transcription import *
from .user import *
from .video import *
from .chatlog import *
from .content_queue import *
from .timestamp_mapping import *

from .base import Base

db = SQLAlchemy(model_class=Base)
