from sqlalchemy import Column, Integer, String, Float, Text
from .database import Base

class Metric(Base):
    __tablename__ = "metrics"
    id = Column(Integer, primary_key=True)
    host = Column(String)
    cpu_percent = Column(Float)
    memory_percent = Column(Float)
    memory_used_gb = Column(Float)
    memory_total_gb = Column(Float)
    disk_percent = Column(Float)
    disk_used_gb = Column(Float)
    disk_total_gb = Column(Float)
    disk_units = Column(Text)  # JSON com unidades
    timestamp = Column(Integer)