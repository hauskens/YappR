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

from .base import Base

db = SQLAlchemy(model_class=Base)

if __name__ == "__main__":
    print("test")


def testies():
    print("testies")