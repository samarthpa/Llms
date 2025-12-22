from bs4 import BeautifulSoup
from urllib.parse import urlparse
from typing import Dict, List, Optional
import re

class MetadataExtractor:
    """Extract additional metadata like author info, contact links, licensing, etc."""
    
    def __init__(self):
        pass
    
    def extract_author_info(self, pages: List[Dict]) -> Optional[Dict]:
        """Extract author information from about pages"""
        # Find about page
        about_page = None
        for page in pages:
            parsed = urlparse(page['url'])
            path = parsed.path.lower()
            if 'about' in path or page.get('title', '').lower().find('about') >= 0:
                about_page = page
                break
        
        if not about_page:
            return None
        
        html_content = about_page.get('html_content', '')
        if not html_content:
            return None
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        author_info = {
            'name': None,
            'bio': None,
            'title': None,
            'location': None
        }
        
        for heading in soup.find_all(['h1', 'h2', 'h3']):
            text = heading.get_text().strip()
            if 'engineer' in text.lower() or 'developer' in text.lower() or 'author' in text.lower():
                author_info['name'] = text.split('-')[0].strip() if '-' in text else text
                author_info['title'] = text
                break
        
        main_content = soup.find('main') or soup.find('article') or soup.find('.content')
        if not main_content:
            main_content = soup.find('div', class_=re.compile('content|post|entry|article'))
        
        if main_content:
            paragraphs = main_content.find_all('p')
            bio_parts = []
            for p in paragraphs[:3]:
                text = p.get_text().strip()
                if len(text) > 50:
                    bio_parts.append(text)
            if bio_parts:
                author_info['bio'] = ' '.join(bio_parts)
        
        if author_info['name'] or author_info['bio']:
            return author_info
        
        return None
    
    def extract_contact_links(self, pages: List[Dict]) -> List[Dict]:
        """Extract contact and social media links"""
        contact_links = []
        
        social_patterns = {
            'twitter': ['twitter.com', 'x.com', 'twitter'],
            'github': ['github.com', 'github'],
            'linkedin': ['linkedin.com', 'linkedin'],
            'email': ['mailto:', 'email'],
            'bluesky': ['bsky.app', 'bluesky'],
            'ko-fi': ['ko-fi.com', 'kofi'],
            'mastodon': ['mastodon', 'mastodon.social'],
            'instagram': ['instagram.com', 'instagram'],
            'youtube': ['youtube.com', 'youtube']
        }
        
        for page in pages:
            html_content = page.get('html_content', '')
            if not html_content:
                continue
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            for link in soup.find_all('a', href=True):
                href = link.get('href', '').lower()
                text = link.get_text().strip()
                
                for platform, patterns in social_patterns.items():
                    if any(pattern in href for pattern in patterns):
                        if not any(c['url'] == link.get('href') for c in contact_links):
                            contact_links.append({
                                'platform': platform,
                                'url': link.get('href'),
                                'text': text or platform.title()
                            })
        
        return contact_links
    
    def extract_licensing(self, pages: List[Dict]) -> Optional[str]:
        """Extract licensing information"""
        license_keywords = ['license', 'licensing', 'copyright', 'cc-by', 'creative commons']
        
        for page in pages:
            html_content = page.get('html_content', '')
            if not html_content:
                continue
            
            soup = BeautifulSoup(html_content, 'html.parser')
            text = soup.get_text().lower()
            
            for keyword in license_keywords:
                if keyword in text:
                    for link in soup.find_all('a', href=True):
                        href = link.get('href', '').lower()
                        if 'creativecommons.org' in href or 'license' in href:
                            return link.get('href')
                    
                    for elem in soup.find_all(['p', 'div', 'span']):
                        elem_text = elem.get_text().lower()
                        if keyword in elem_text and 'license' in elem_text:
                            return elem.get_text().strip()
        
        return None
    
    def extract_languages(self, pages: List[Dict]) -> List[str]:
        """Extract supported languages"""
        languages = []
        
        # Look for language indicators in HTML
        for page in pages:
            html_content = page.get('html_content', '')
            if not html_content:
                continue
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            html_tag = soup.find('html')
            if html_tag and html_tag.get('lang'):
                lang = html_tag.get('lang')
                if lang not in languages:
                    languages.append(lang)
            
            for link in soup.find_all('a', href=True):
                href = link.get('href', '').lower()
                text = link.get_text().strip()
                if 'lang=' in href or '/en/' in href or '/es/' in href:
                    if '/en/' in href:
                        if 'English' not in languages:
                            languages.append('English')
                    elif '/es/' in href:
                        if 'Spanish' not in languages:
                            languages.append('Spanish')
        
        if not languages:
            languages = ['English']
        
        return languages
    
    def extract_main_navigation(self, pages: List[Dict]) -> List[Dict]:
        """Extract main navigation links"""
        main_pages = []
        
        homepage = None
        for page in pages:
            parsed = urlparse(page['url'])
            if parsed.path in ['/', '/index', '/index.html']:
                homepage = page
                break
        
        if not homepage:
            homepage = pages[0] if pages else None
        
        if not homepage:
            return main_pages
        
        html_content = homepage.get('html_content', '')
        if not html_content:
            return main_pages
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        nav_links = []
        nav_selectors = ['nav a', 'header nav a', '.navbar a', '.navigation a', '[role="navigation"] a']
        
        for selector in nav_selectors:
            for link in soup.select(selector):
                href = link.get('href')
                if href:
                    from urllib.parse import urljoin
                    full_url = urljoin(homepage['url'], href)
                    text = link.get_text().strip()
                    if text and full_url not in [p['url'] for p in nav_links]:
                        nav_links.append({
                            'url': full_url,
                            'text': text
                        })
        
        main_page_patterns = ['/', '/about', '/blog', '/contact', '/home']
        for page in pages:
            parsed = urlparse(page['url'])
            path = parsed.path.rstrip('/')
            if path in main_page_patterns or path == '':
                if page not in [p for p in main_pages if p['url'] == page['url']]:
                    main_pages.append({
                        'url': page['url'],
                        'text': page.get('title', 'Untitled')
                    })
        
        all_main = {}
        for item in nav_links + main_pages:
            url = item['url']
            if url not in all_main:
                all_main[url] = item
        
        return list(all_main.values())

