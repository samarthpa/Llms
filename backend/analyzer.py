from typing import List, Dict
from urllib.parse import urlparse
import re
from llm_service import LLMService

class ContentAnalyzer:
    def __init__(self, use_llm: bool = True):
        self.llm_service = LLMService() if use_llm else None
        self.category_keywords = {
            'home': ['home', 'index', 'main', 'welcome'],
            'about': ['about', 'company', 'team', 'story', 'mission', 'vision', 'history'],
            'contact': ['contact', 'reach', 'get-in-touch', 'support', 'help'],
            'services': ['service', 'services', 'offerings', 'solutions', 'what-we-do'],
            'products': ['product', 'products', 'catalog', 'shop', 'store', 'buy'],
            'blog': ['blog', 'news', 'articles', 'posts', 'updates'],
            'pricing': ['pricing', 'price', 'plans', 'cost', 'subscription'],
            'faq': ['faq', 'faqs', 'questions', 'help'],
            'careers': ['career', 'careers', 'jobs', 'hiring', 'work-with-us'],
            'documentation': ['docs', 'documentation', 'guide', 'api', 'reference']
        }
    
    def categorize_page(self, url: str, title: str = '', description: str = '', content_preview: str = '') -> str:
        """Categorize a page based on URL, title, and description"""
        if self.llm_service and self.llm_service.is_available() and content_preview:
            llm_category = self.llm_service.categorize_page_intelligently(url, title, description, content_preview)
            if llm_category:
                return llm_category
        
        url_lower = url.lower()
        title_lower = (title or '').lower()
        desc_lower = (description or '').lower()
        combined = f"{url_lower} {title_lower} {desc_lower}"
        
        path = urlparse(url).path.lower()
        
        if path in ['/', '/index', '/index.html', '/home']:
            return 'home'
        
        category_scores = {}
        for category, keywords in self.category_keywords.items():
            score = 0
            for keyword in keywords:
                if keyword in path:
                    score += 3
                if keyword in title_lower:
                    score += 2
                if keyword in desc_lower:
                    score += 1
            if score > 0:
                category_scores[category] = score
        
        if category_scores:
            return max(category_scores, key=category_scores.get)
        
        return 'other'
    
    def identify_key_pages(self, pages: List[Dict]) -> Dict[str, Dict]:
        """Identify and prioritize key pages"""
        key_pages = {}
        
        for page in pages:
            url = page['url']
            category = self.categorize_page(
                url, 
                page.get('title', ''), 
                page.get('description', ''),
                page.get('raw_text', '')
            )
            
            priority_categories = ['home', 'about', 'contact', 'services', 'products']
            
            if category in priority_categories:
                if category not in key_pages:
                    key_pages[category] = page
                elif len(page.get('description', '')) > len(key_pages[category].get('description', '')):
                    key_pages[category] = page
        
        return key_pages
    
    def group_pages_by_category(self, pages: List[Dict]) -> Dict[str, List[Dict]]:
        """Group pages by their categories"""
        categorized = {}
        
        for page in pages:
            category = self.categorize_page(
                page['url'], 
                page.get('title', ''), 
                page.get('description', ''),
                page.get('raw_text', '')
            )
            
            if category not in categorized:
                categorized[category] = []
            categorized[category].append(page)
        
        for category in categorized:
            categorized[category].sort(key=lambda p: urlparse(p['url']).path.count('/'))
        
        return categorized
    
    def extract_website_name(self, pages: List[Dict]) -> str:
        """Extract website name from homepage or domain"""
        homepage = None
        for page in pages:
            parsed = urlparse(page['url'])
            if parsed.path in ['/', '/index', '/index.html']:
                homepage = page
                break
        
        if homepage:
            title = homepage.get('title', '')
            if title:
                title = re.sub(r'\s*[-|]\s*(Home|Welcome|Main).*$', '', title, flags=re.IGNORECASE)
                return title.strip()
        
        if pages:
            domain = urlparse(pages[0]['url']).netloc
            domain = re.sub(r'^www\.', '', domain)
            domain = re.sub(r'\.[a-z]{2,4}$', '', domain)
            return domain.replace('.', ' ').title()
        
        return 'Website'
    
    def extract_summary(self, pages: List[Dict]) -> str:
        """Extract website summary from homepage"""
        if self.llm_service and self.llm_service.is_available():
            llm_summary = self.llm_service.generate_website_summary(pages)
            if llm_summary:
                return llm_summary
        
        homepage = None
        for page in pages:
            parsed = urlparse(page['url'])
            if parsed.path in ['/', '/index', '/index.html']:
                homepage = page
                break
        
        if homepage:
            description = homepage.get('description', '')
            if description:
                return description
        
        for page in pages:
            desc = page.get('description', '')
            if desc and len(desc) > 50:
                return desc
        
        return 'A website providing various services and information.'

