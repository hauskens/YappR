import enum
from collections.abc import Sequence
from sqlalchemy import Engine, ForeignKey, String, Integer, Enum, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable
from flask import Flask, flash, render_template, request, redirect, url_for
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


def get_broadcasters() -> Sequence[Broadcaster]:
    return (
        db.session.execute(select(Broadcaster).order_by(Broadcaster.name))
        .scalars()
        .all()
    )


db = SQLAlchemy(model_class=Base)
app = Flask(__name__, static_url_path="")
app.secret_key = "omgtesties"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///project.db"
db.init_app(app)
with app.app_context():
    db.create_all()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/broadcasters")
def broadcasters():
    broadcasters = get_broadcasters()
    return render_template("broadcasters.html", broadcasters=broadcasters)


@app.route("/broadcaster_create", methods=["POST"])
def broadcaster_create():
    name = request.form["name"]
    existing_broadcasters = get_broadcasters()
    for broadcaster in existing_broadcasters:
        if broadcaster.name.lower() == name.lower():
            flash("This broadcaster already exists", "error")
            return render_template(
                "broadcasters.html",
                form=request.form,
                broadcasters=existing_broadcasters,
            )
    db.session.add(Broadcaster(name=name))
    db.session.commit()
    return redirect(url_for("broadcasters"))


# engine = create_engine("sqlite+pysqlite:///:memory:", echo=True)

if __name__ == "__main__":
    app.run(debug=True)
