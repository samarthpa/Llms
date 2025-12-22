from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime

Base = declarative_base()

class Website(Base):
    __tablename__ = 'websites'
    
    id = Column(Integer, primary_key=True)
    url = Column(String(500), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_checked = Column(DateTime, nullable=True)
    status = Column(String(50), default='pending')  # pending, processing, completed, error
    monitoring_enabled = Column(Boolean, default=False)
    check_interval = Column(Integer, default=3600)  # seconds, default 1 hour (more responsive)
    feed_urls = Column(Text, nullable=True)  # JSON array of RSS/Atom feed URLs
    feed_hashes = Column(Text, nullable=True)  # JSON object mapping feed URLs to hashes
    sitemap_urls = Column(Text, nullable=True)  # JSON array of URLs from sitemap
    
    pages = relationship("Page", back_populates="website", cascade="all, delete-orphan")
    generations = relationship("Generation", back_populates="website", cascade="all, delete-orphan")
    change_logs = relationship("ChangeLog", back_populates="website", cascade="all, delete-orphan")

class Page(Base):
    __tablename__ = 'pages'
    
    id = Column(Integer, primary_key=True)
    website_id = Column(Integer, ForeignKey('websites.id'), nullable=False)
    url = Column(String(1000), nullable=False)
    title = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    content_hash = Column(String(64), nullable=True)  # SHA256 hash
    last_updated = Column(DateTime, default=datetime.utcnow)
    discovered_at = Column(DateTime, default=datetime.utcnow)
    
    website = relationship("Website", back_populates="pages")

class Generation(Base):
    __tablename__ = 'generations'
    
    id = Column(Integer, primary_key=True)
    website_id = Column(Integer, ForeignKey('websites.id'), nullable=False)
    llms_txt_content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    version = Column(Integer, default=1)
    change_detected = Column(Boolean, default=False)
    
    website = relationship("Website", back_populates="generations")

class ChangeLog(Base):
    __tablename__ = 'change_log'
    
    id = Column(Integer, primary_key=True)
    website_id = Column(Integer, ForeignKey('websites.id'), nullable=False)
    change_type = Column(String(50), nullable=False)  # new_page, updated_page, removed_page, content_change
    page_url = Column(String(1000), nullable=True)
    detected_at = Column(DateTime, default=datetime.utcnow)
    description = Column(Text, nullable=True)
    
    website = relationship("Website", back_populates="change_logs")

def init_db(db_path='database.db'):
    engine = create_engine(f'sqlite:///{db_path}', echo=False)
    Base.metadata.create_all(engine)
    return engine

def get_session(engine):
    Session = sessionmaker(bind=engine)
    return Session()


