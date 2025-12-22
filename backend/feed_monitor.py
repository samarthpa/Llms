import requests
import feedparser
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import List, Dict, Optional
from datetime import datetime
import hashlib
import logging

logger = logging.getLogger(__name__)

class FeedMonitor:
    """Monitor RSS/Atom feeds and sitemaps for changes"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; LLMsTxtGenerator/1.0; +https://llmstxt.org/)'
        })
    
    def find_feeds(self) -> List[str]:
        """Find RSS/Atom feeds on the website"""
        feeds = []
        
        try:
            common_feeds = [
                '/feed',
                '/rss',
                '/atom',
                '/feed.xml',
                '/rss.xml',
                '/atom.xml',
                '/blog/feed',
                '/blog/rss',
                '/feeds/all.rss',
            ]
            
            for feed_path in common_feeds:
                feed_url = urljoin(self.base_url, feed_path)
                try:
                    response = self.session.get(feed_url, timeout=5)
                    if response.status_code == 200:
                        content_type = response.headers.get('Content-Type', '').lower()
                        if 'xml' in content_type or 'rss' in content_type or 'atom' in content_type:
                            feed = feedparser.parse(response.content)
                            if feed.entries:
                                feeds.append(feed_url)
                                logger.info(f"Found feed: {feed_url}")
                except:
                    continue
            
            try:
                response = self.session.get(self.base_url, timeout=10)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    feed_links = soup.find_all('link', type=lambda x: x and ('rss' in x.lower() or 'atom' in x.lower()))
                    for link in feed_links:
                        href = link.get('href')
                        if href:
                            feed_url = urljoin(self.base_url, href)
                            if feed_url not in feeds:
                                try:
                                    feed = feedparser.parse(self.session.get(feed_url, timeout=5).content)
                                    if feed.entries:
                                        feeds.append(feed_url)
                                        logger.info(f"Found feed in HTML: {feed_url}")
                                except:
                                    pass
            except:
                pass
                
        except Exception as e:
            logger.error(f"Error finding feeds: {e}")
        
        return feeds
    
    def check_feed_changes(self, feed_url: str, last_hash: Optional[str] = None):
        """Check if feed has new entries"""
        try:
            response = self.session.get(feed_url, timeout=10)
            if response.status_code != 200:
                return False, None, []
            
            feed = feedparser.parse(response.content)
            
            if not feed.entries:
                return False, None, []
            
            feed_content = '\n'.join([
                entry.get('title', '') + entry.get('link', '') 
                for entry in feed.entries[:5]
            ])
            current_hash = hashlib.sha256(feed_content.encode()).hexdigest()
            
            if last_hash and current_hash == last_hash:
                return False, current_hash, []
            
            new_entries = []
            for entry in feed.entries[:10]:
                new_entries.append({
                    'title': entry.get('title', 'Untitled'),
                    'url': entry.get('link', ''),
                    'published': entry.get('published', ''),
                    'description': entry.get('summary', '')[:200]
                })
            
            return True, current_hash, new_entries
            
        except Exception as e:
            logger.error(f"Error checking feed {feed_url}: {e}")
            return False, None, []
    
    def check_sitemap_changes(self, last_urls: Optional[List[str]] = None):
        """Check sitemap.xml for new URLs"""
        try:
            sitemap_url = urljoin(self.base_url, '/sitemap.xml')
            response = self.session.get(sitemap_url, timeout=10)
            
            if response.status_code != 200:
                return False, []
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.content, 'xml')
            
            current_urls = []
            for loc in soup.find_all('loc'):
                url = loc.get_text().strip()
                current_urls.append(url)
            
            if not last_urls:
                return True, current_urls
            
            new_urls = [url for url in current_urls if url not in last_urls]
            
            return len(new_urls) > 0, new_urls
            
        except Exception as e:
            logger.error(f"Error checking sitemap: {e}")
            return False, []

