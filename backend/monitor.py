from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from models import Website, Page, Generation, ChangeLog
from crawler import WebCrawler
from generator import LLMsTxtGenerator
from feed_monitor import FeedMonitor
from utils import get_content_hash
from typing import List, Dict
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ChangeMonitor:
    def __init__(self, db_session: Session):
        self.db_session = db_session
        self.generator = LLMsTxtGenerator()
    
    def check_website(self, website: Website) -> bool:
        """Check a website for changes and update if needed"""
        logger.info(f"Checking website: {website.url}")
        
        try:
            # Update last_checked timestamp
            try:
                website.last_checked = datetime.utcnow()
                website.status = 'processing'
                self.db_session.commit()
            except Exception:
                self.db_session.rollback()
                raise
            
            changes_detected = False
            
            try:
                feed_monitor = FeedMonitor(website.url)
                
                if hasattr(website, 'feed_urls'):
                    if not website.feed_urls:
                        feeds = feed_monitor.find_feeds()
                        if feeds:
                            website.feed_urls = json.dumps(feeds)
                            logger.info(f"Discovered {len(feeds)} feeds for {website.url}")
                    else:
                        feeds = json.loads(website.feed_urls)
                    
                    feed_hashes = json.loads(website.feed_hashes) if hasattr(website, 'feed_hashes') and website.feed_hashes else {}
                    for feed_url in feeds:
                        last_hash = feed_hashes.get(feed_url)
                        has_changes, new_hash, new_entries = feed_monitor.check_feed_changes(feed_url, last_hash)
                        
                        if has_changes:
                            changes_detected = True
                            feed_hashes[feed_url] = new_hash
                            logger.info(f"Feed {feed_url} has new entries: {len(new_entries)}")
                            
                            for entry in new_entries[:5]:
                                self.db_session.add(ChangeLog(
                                    website_id=website.id,
                                    change_type='new_page',
                                    page_url=entry.get('url', ''),
                                    description=f"New content in feed: {entry.get('title', 'New entry')}"
                                ))
                    
                    if hasattr(website, 'feed_hashes'):
                        website.feed_hashes = json.dumps(feed_hashes)
                
                if hasattr(website, 'sitemap_urls'):
                    last_sitemap_urls = json.loads(website.sitemap_urls) if website.sitemap_urls else None
                    sitemap_changed, new_sitemap_urls = feed_monitor.check_sitemap_changes(last_sitemap_urls)
                    
                    if sitemap_changed:
                        changes_detected = True
                        website.sitemap_urls = json.dumps(new_sitemap_urls)
                        logger.info(f"Sitemap has {len(new_sitemap_urls) - (len(last_sitemap_urls) if last_sitemap_urls else 0)} new URLs")
                
                if changes_detected:
                    logger.info(f"Feeds/sitemap detected changes, doing full crawl for {website.url}")
            except Exception as e:
                logger.warning(f"Feed/sitemap monitoring failed (continuing with full crawl): {e}")
            
            crawler = WebCrawler(website.url, max_depth=3, max_pages=100)
            current_pages = crawler.crawl()
            
            existing_pages = {page.url: page for page in website.pages}
            current_urls = {page['url'] for page in current_pages}
            
            changes_detected = False
            change_logs = []
            
            for page_data in current_pages:
                url = page_data['url']
                if url not in existing_pages:
                    new_page = Page(
                        website_id=website.id,
                        url=url,
                        title=page_data.get('title'),
                        description=page_data.get('description'),
                        content_hash=page_data.get('content_hash'),
                        discovered_at=datetime.utcnow()
                    )
                    self.db_session.add(new_page)
                    self.db_session.flush()
                    existing_pages[url] = new_page
                    changes_detected = True
                    
                    change_logs.append(ChangeLog(
                        website_id=website.id,
                        change_type='new_page',
                        page_url=url,
                        description=f"New page discovered: {page_data.get('title', url)}"
                    ))
                    logger.info(f"New page discovered: {url}")
            
            for url, page in existing_pages.items():
                if url not in current_urls:
                    changes_detected = True
                    change_logs.append(ChangeLog(
                        website_id=website.id,
                        change_type='removed_page',
                        page_url=url,
                        description=f"Page removed: {page.title or url}"
                    ))
                    logger.info(f"Page removed: {url}")
            
            for page_data in current_pages:
                url = page_data['url']
                if url in existing_pages:
                    existing_page = existing_pages[url]
                    new_hash = page_data.get('content_hash')
                    
                    if existing_page.content_hash and existing_page.content_hash != new_hash:
                        existing_page.content_hash = new_hash
                        existing_page.title = page_data.get('title', existing_page.title)
                        existing_page.description = page_data.get('description', existing_page.description)
                        existing_page.last_updated = datetime.utcnow()
                        changes_detected = True
                        
                        change_logs.append(ChangeLog(
                            website_id=website.id,
                            change_type='content_change',
                            page_url=url,
                            description=f"Content updated: {page_data.get('title', url)}"
                        ))
                        logger.info(f"Content changed: {url}")
            
            if changes_detected:
                logger.info(f"Changes detected for {website.url}, regenerating llms.txt")
                
                pages_data = []
                for page_data in current_pages:
                    db_page = existing_pages.get(page_data['url'])
                    if db_page:
                        pages_data.append({
                            'url': db_page.url,
                            'title': db_page.title or 'Untitled',
                            'description': db_page.description,
                            'raw_text': page_data.get('raw_text', ''),
                            'html_content': page_data.get('html_content', '')
                        })
                    else:
                        pages_data.append({
                            'url': page_data['url'],
                            'title': page_data.get('title', 'Untitled'),
                            'description': page_data.get('description'),
                            'raw_text': page_data.get('raw_text', ''),
                            'html_content': page_data.get('html_content', '')
                        })
                
                for url, db_page in existing_pages.items():
                    if url not in current_urls:
                        if not any(p['url'] == url for p in pages_data):
                            pages_data.append({
                                'url': db_page.url,
                                'title': db_page.title or 'Untitled',
                                'description': db_page.description,
                                'raw_text': '',
                                'html_content': ''
                            })
                
                llms_content = self.generator.generate(pages_data)
                
                latest_gen = self.db_session.query(Generation).filter(
                    Generation.website_id == website.id
                ).order_by(Generation.version.desc()).first()
                
                new_version = (latest_gen.version + 1) if latest_gen else 1
                
                new_generation = Generation(
                    website_id=website.id,
                    llms_txt_content=llms_content,
                    version=new_version,
                    change_detected=True
                )
                self.db_session.add(new_generation)
                
                for log in change_logs:
                    self.db_session.add(log)
                
                website.status = 'completed'
                logger.info(f"llms.txt regenerated for {website.url} (version {new_version})")
            else:
                website.status = 'completed'
                logger.info(f"No changes detected for {website.url}")
            
            self.db_session.commit()
            return changes_detected
            
        except Exception as e:
            logger.error(f"Error checking website {website.url}: {e}")
            website.status = 'error'
            self.db_session.commit()
            return False
    
    def check_all_monitored_websites(self):
        """Check all websites that have monitoring enabled"""
        websites = self.db_session.query(Website).filter(
            Website.monitoring_enabled == True
        ).all()
        
        logger.info(f"Checking {len(websites)} monitored websites")
        
        for website in websites:
            if website.last_checked:
                time_since_check = datetime.utcnow() - website.last_checked
                if time_since_check.total_seconds() < website.check_interval:
                    logger.debug(f"Skipping {website.url} - only {time_since_check.total_seconds()}s since last check (interval: {website.check_interval}s)")
                    continue
            
            self.check_website(website)
    
    def check_website_immediately(self, website_id: int) -> bool:
        """Check a specific website immediately, bypassing interval check"""
        website = self.db_session.query(Website).filter(Website.id == website_id).first()
        if not website:
            logger.error(f"Website {website_id} not found")
            return False
        
        if not website.monitoring_enabled:
            logger.warning(f"Website {website.url} is not enabled for monitoring")
            return False
        
        logger.info(f"Immediate check requested for {website.url}")
        return self.check_website(website)
    
    def get_change_history(self, website_id: int, limit: int = 50) -> List[ChangeLog]:
        """Get change history for a website"""
        return self.db_session.query(ChangeLog).filter(
            ChangeLog.website_id == website_id
        ).order_by(ChangeLog.detected_at.desc()).limit(limit).all()


