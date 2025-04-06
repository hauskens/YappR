import enum
from sqlalchemy import Engine, ForeignKey, String, Integer, Enum, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable
from flask import Flask
from flask_sqlalchemy import SQLAlchemy


class Base(DeclarativeBase):
    pass


class Broadcaster(Base):
    __tablename__: str = "broadcaster"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(250), unique=True)


class Platforms(Base):
    __tablename__: str = "platforms"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(250), unique=True)
    url: Mapped[str] = mapped_column(String(1000))


class VideoType(enum.Enum):
    Unknown = "unknown"
    VOD = "vod"
    Clip = "clip"
    Edit = "edit"


class Channels(Base):
    __tablename__: str = "channels"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(250))
    broadcaster_id: Mapped[str] = mapped_column(ForeignKey("broadcaster.id"))
    broadcaster: Mapped["Broadcaster"] = relationship()
    platform_id: Mapped[int] = mapped_column(ForeignKey("platforms.id"))
    platform: Mapped["Platforms"] = relationship()
    main_video_type: Mapped[str] = mapped_column(
        Enum(VideoType), default=VideoType.Unknown
    )


class Video(Base):
    __tablename__: str = "video"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(250))
    video_type: Mapped[str] = mapped_column(Enum(VideoType))
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"))
    channel: Mapped["Channels"] = relationship()
    platform_ref: Mapped[str] = mapped_column(String(), unique=True)


# def init() -> Engine:
#     engine = create_engine("sqlite:///testdb.sqlite", echo=True)
#     Base.metadata.create_all(engine)
#     return engine


db = SQLAlchemy(model_class=Base)
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///project.db"
db.init_app(app)
with app.app_context():
    db.create_all()


@app.route("/broadcasters")
def broadcaster_list():
    broadcasters = db.session.execute(
        select(Broadcaster).order_by(Broadcaster.name)
    ).first()
    # return f"{broadcasters.}"
    return "uhh"


@app.route("/broadcaster/<name>")
def check(name: str):
    # return "Flask is working"
    # broadcasters = db.session.execute(db.select(Broadcaster)).scalars()
    broadcaster = db.get_or_404(Broadcaster, name)

    return broadcaster


@app.route("/create/<name>")
def create_broadcaster(name: str):
    db.session.add(Broadcaster(name=name))
    db.session.commit()
    return name


# engine = create_engine("sqlite+pysqlite:///:memory:", echo=True)

# with Session(engine) as session:
#     testBroadcaster = Broadcaster(name="testies")
#     session.add(testBroadcaster)
#     session.commit()

# session = Session(engine)
# test = select(Broadcaster).where(Broadcaster.name.in_(["testies"]))
#
# bc = session.scalars(test).one_or_none()
# if bc:
#     bc.name = "buhh"
#     # session.commit()
#
# test2 = select(Broadcaster)
# for t in session.scalars(test2):
#     print(f"hello {t.name}")

# print(CreateTable(Video.__table__).compile(dialect=postgresql.dialect()))
if __name__ == "__main__":
    app.run()
