from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime

# Настройка подключения к базе данных SQLite
# Важно: имя файла базы данных должно отличаться от DATABASE в app.py,
# если вы хотите полностью перейти на ORM и не смешивать старые и новые данные.
# Пусть будет 'events_orm.db'
DATABASE_URL = 'sqlite:///events_orm.db'
engine = create_engine(DATABASE_URL, echo=False) # echo=True для логирования SQL-запросов (полезно для отладки)
Base = declarative_base()
Session = sessionmaker(bind=engine)


class Venue(Base):
    __tablename__ = 'venues'
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True) # Имя площадки, например "Филармония"
    original_id = Column(String(50), nullable=False, unique=True) # Ваш 'id' из VENUES, например "filarmoniya"
    url = Column(String(255), nullable=False)

    events = relationship("Event", back_populates="venue") # Связь с мероприятиями

    def __repr__(self):
        return f"<Venue(name='{self.name}', original_id='{self.original_id}')>"


class Event(Base):
    __tablename__ = 'events'
    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    original_date_str = Column(String(255), nullable=False) # "15 мая 19:00"
    parsed_datetime = Column(DateTime) # datetime object for sorting
    ticket_link = Column(String(255))
    image_url = Column(String(255))

    # Foreign Key для связи с таблицей площадок
    venue_id = Column(Integer, ForeignKey('venues.id'), nullable=False)
    venue = relationship("Venue", back_populates="events") # Связь с площадкой

    # Уникальный ключ для предотвращения дубликатов
    unique_key = Column(String(255), unique=True, nullable=False)

    __table_args__ = (
        UniqueConstraint('title', 'parsed_datetime', 'venue_id', name='_event_venue_date_uc'),
    )


    def __repr__(self):
        return f"<Event(title='{self.title}', date='{self.parsed_datetime}', venue='{self.venue.name if self.venue else 'N/A'})>"


def create_db_tables():
    """Создает все таблицы, определенные в Base."""
    Base.metadata.create_all(engine)
    print("База данных 'events_orm.db' и таблицы успешно созданы/обновлены.")

# При первом запуске этого файла или вызове create_db_tables()
# таблицы будут созданы.
if __name__ == '__main__':
    create_db_tables()