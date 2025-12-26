import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
from collections import deque, defaultdict
import time
import re
from typing import List, Dict, Set, Tuple
from utils import normalize_url, is_same_domain, get_content_hash, extract_text_from_html
from llm_service import LLMService

class WebCrawler:
    def __init__(self, base_url: str, max_depth: int = 3, max_pages: int = 100, delay: float = 1.0, use_llm: bool = True):
        self.base_url = normalize_url(base_url)
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.delay = delay
        self.visited_urls: Set[str] = set()
        self.pages: List[Dict] = []
        self.robots_parser = None
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; LLMsTxtGenerator/1.0; +https://llmstxt.org/)'
        })
        self.llm_service = LLMService() if use_llm else None
        self.section_counts: Dict[str, int] = defaultdict(int)
        self.defer_counts: Dict[str, int] = {}
        
    def _check_robots_txt(self):
        """Check and parse robots.txt"""
        try:
            robots_url = urljoin(self.base_url, '/robots.txt')
            rp = RobotFileParser()
            rp.set_url(robots_url)
            rp.read()
            self.robots_parser = rp
        except Exception:
            self.robots_parser = None
    
    def _can_fetch(self, url: str) -> bool:
        """Check if URL can be fetched according to robots.txt"""
        if not self.robots_parser:
            return True
        try:
            return self.robots_parser.can_fetch('*', url)
        except:
            return True
    
    def _fetch_page(self, url: str) -> requests.Response:
        """Fetch a page with error handling"""
        try:
            response = self.session.get(url, timeout=10, allow_redirects=True)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException:
            return None
    
    def _parse_sitemap(self) -> List[str]:
        """Try to parse sitemap.xml if available"""
        sitemap_urls = [
            urljoin(self.base_url, '/sitemap.xml'),
            urljoin(self.base_url, '/sitemap_index.xml'),
        ]
        
        urls = []
        for sitemap_url in sitemap_urls:
            try:
                response = self._fetch_page(sitemap_url)
                if response and response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'xml')
                    for loc in soup.find_all('loc'):
                        url = loc.get_text().strip()
                        if is_same_domain(url, self.base_url):
                            urls.append(normalize_url(url))
            except Exception:
                pass
        
        return urls
    
    def _extract_navigation_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """Extract links from navigation menus"""
        nav_links = []
        
        nav_selectors = [
            'nav a',
            'header nav a',
            '.navbar a',
            '.navigation a',
            '.menu a',
            '[role="navigation"] a',
            '.header a',
            '.main-menu a'
        ]
        
        for selector in nav_selectors:
            links = soup.select(selector)
            for link in links:
                href = link.get('href')
                if href:
                    full_url = urljoin(base_url, href)
                    if is_same_domain(full_url, self.base_url):
                        nav_links.append(normalize_url(full_url))
        
        return list(set(nav_links))
    
    def _extract_internal_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """Extract all internal links from a page"""
        links = []
        
        link_selectors = [
            ('a', 'href'),
            ('link', 'href'),
            ('area', 'href'),
        ]
        
        for tag_name, attr_name in link_selectors:
            for element in soup.find_all(tag_name, **{attr_name: True}):
                href = element.get(attr_name)
                if href:
                    full_url = urljoin(base_url, href)
                    parsed = urlparse(full_url)
                    
                    if parsed.scheme not in ['http', 'https']:
                        continue
                    
                    if is_same_domain(full_url, self.base_url):
                        normalized = normalize_url(full_url)
                        
                        skip_patterns = [
                            'mailto:', 'tel:', 'javascript:', 
                            '.pdf', '.jpg', '.jpeg', '.png', '.gif', '.svg', 
                            '.css', '.js', '.json', '.xml', '.zip', '.tar',
                            'data:', 'blob:'
                        ]
                        
                        should_skip = False
                        normalized_lower = normalized.lower()
                        for skip in skip_patterns:
                            if skip in normalized_lower:
                                should_skip = True
                                break
                        
                        if not should_skip:
                            if '#' in normalized:
                                normalized = normalized.split('#')[0]
                            
                            if normalized and normalized not in links:
                                links.append(normalized)
        
        content_selectors = [
            'main a', 'article a', '.content a', '.post a', 
            '.entry a', 'section a', '.page-content a'
        ]
        
        for selector in content_selectors:
            for link in soup.select(selector):
                href = link.get('href')
                if href:
                    full_url = urljoin(base_url, href)
                    if is_same_domain(full_url, self.base_url):
                        normalized = normalize_url(full_url)
                        if '#' in normalized:
                            normalized = normalized.split('#')[0]
                        
                        skip_extensions = ['.pdf', '.jpg', '.png', '.gif', '.svg', '.css', '.js', '.zip']
                        if not any(ext in normalized.lower() for ext in skip_extensions):
                            if normalized and normalized not in links:
                                links.append(normalized)
        
        return list(set(links))
    
    def _extract_metadata(self, url: str, html_content: str) -> Dict:
        """Extract metadata from a page"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        title = None
        if soup.title:
            title = soup.title.get_text().strip()
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            title = og_title.get('content').strip()
        
        description = None
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            description = meta_desc.get('content').strip()
        og_desc = soup.find('meta', property='og:description')
        if og_desc and og_desc.get('content'):
            description = og_desc.get('content').strip()
        
        if not description:
            first_p = soup.find('p')
            if first_p:
                description = extract_text_from_html(str(first_p), max_length=200)
        
        raw_text = extract_text_from_html(html_content, max_length=2000)
        content_hash = get_content_hash(html_content)
        
        return {
            'url': url,
            'title': title or 'Untitled',
            'description': description,
            'content_hash': content_hash,
            'html_content': html_content,
            'raw_text': raw_text
        }
    
    def _get_section_key(self, url: str) -> str:
        """Extract first path segment for section dominance tracking"""
        parsed = urlparse(url)
        path = parsed.path.strip('/')
        if not path:
            return '/'
        first_segment = path.split('/')[0]
        return f'/{first_segment}'
    
    def _check_section_dominance(self, url: str) -> bool:
        """Check if a URL's section exceeds 40% of crawled pages"""
        if len(self.visited_urls) == 0:
            return False
        section_key = self._get_section_key(url)
        section_count = self.section_counts[section_key]
        total_crawled = len(self.visited_urls)
        return (section_count / total_crawled) > 0.4
    
    def _crawl_page(self, url: str) -> Tuple[List[str], List[str]]:
        """Crawl a single page and return (nav_links, other_links)"""
        if self.delay > 0:
            time.sleep(self.delay)
        
        response = self._fetch_page(url)
        
        if not response or response.status_code != 200:
            return [], []
        
        content_type = response.headers.get('Content-Type', '').lower()
        if 'text/html' not in content_type and 'application/xhtml' not in content_type:
            return [], []
        
        try:
            metadata = self._extract_metadata(url, response.text)
            self.pages.append(metadata)
        except Exception:
            self.pages.append({
                'url': url,
                'title': 'Untitled',
                'description': None,
                'content_hash': get_content_hash(response.text),
                'html_content': response.text,
                'raw_text': extract_text_from_html(response.text, max_length=2000)
            })
        
        section_key = self._get_section_key(url)
        self.section_counts[section_key] += 1
        
        nav_links = []
        other_links = []
        
        try:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            nav_links = self._extract_navigation_links(soup, url)
            internal_links = self._extract_internal_links(soup, url)
            page_links = [l for l in internal_links if l not in nav_links and '/' in urlparse(l).path]
            other_links = page_links[:30]
        except Exception:
            pass
        
        return nav_links, other_links
    
    def crawl(self) -> List[Dict]:
        """
        Main crawling method using priority-tier BFS.
        Priority BFS: nav first, then other; dominance deferral bounded (max 3 deferrals per URL).
        Strict FIFO order within each depth level.
        """
        self._check_robots_txt()
        
        self.defer_counts.clear()
        MAX_DEFERS = 3
        
        nav_queues = [deque() for _ in range(self.max_depth + 1)]
        other_queues = [deque() for _ in range(self.max_depth + 1)]
        queued_urls: Set[str] = set()
        
        sitemap_urls = self._parse_sitemap()
        if sitemap_urls:
            for url in sitemap_urls[:self.max_pages]:
                normalized = normalize_url(url)
                if normalized not in self.visited_urls and normalized not in queued_urls and self._can_fetch(normalized):
                    nav_queues[0].append(normalized)
                    queued_urls.add(normalized)
        else:
            normalized_base = normalize_url(self.base_url)
            nav_queues[0].append(normalized_base)
            queued_urls.add(normalized_base)
        
        for depth in range(self.max_depth + 1):
            while (nav_queues[depth] or other_queues[depth]) and len(self.visited_urls) < self.max_pages:
                url = None
                priority = None
                
                # Priority BFS: nav first, then other (FIFO within each queue)
                if nav_queues[depth]:
                    url = nav_queues[depth].popleft()
                    priority = 'nav'
                elif other_queues[depth]:
                    url = other_queues[depth].popleft()
                    priority = 'other'
                
                if not url:
                    break
                
                queued_urls.discard(url)
                
                if url in self.visited_urls:
                    continue
                
                if not self._can_fetch(url):
                    continue
                
                # Bounded deferral: prevent infinite requeue loops
                # If dominant section AND other priority AND not exceeded defer limit: requeue to back
                if self._check_section_dominance(url) and priority == 'other':
                    defer_count = self.defer_counts.get(url, 0)
                    if defer_count < MAX_DEFERS:
                        self.defer_counts[url] = defer_count + 1
                        other_queues[depth].append(url)
                        queued_urls.add(url)
                        continue
                
                self.visited_urls.add(url)
                
                nav_links, other_links = self._crawl_page(url)
                
                if depth < self.max_depth and len(self.visited_urls) < self.max_pages:
                    for link in nav_links:
                        normalized = normalize_url(link)
                        if (normalized not in self.visited_urls and 
                            normalized not in queued_urls and
                            len(self.visited_urls) < self.max_pages and
                            self._can_fetch(normalized)):
                            nav_queues[depth + 1].append(normalized)
                            queued_urls.add(normalized)
                    
                    for link in other_links:
                        normalized = normalize_url(link)
                        if (normalized not in self.visited_urls and 
                            normalized not in queued_urls and
                            len(self.visited_urls) < self.max_pages and
                            self._can_fetch(normalized)):
                            other_queues[depth + 1].append(normalized)
                            queued_urls.add(normalized)
        
        if not self.pages:
            response = self._fetch_page(self.base_url)
            if response and response.status_code == 200:
                metadata = self._extract_metadata(self.base_url, response.text)
                self.pages.append(metadata)
        
        return self.pages

