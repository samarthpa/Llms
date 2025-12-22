from typing import List, Dict, Optional
from analyzer import ContentAnalyzer
from urllib.parse import urlparse
from llm_service import LLMService
from metadata_extractor import MetadataExtractor

class LLMsTxtGenerator:
    def __init__(self, use_llm: bool = True):
        self.analyzer = ContentAnalyzer(use_llm=use_llm)
        self.llm_service = LLMService() if use_llm else None
        self.metadata_extractor = MetadataExtractor()
    
    def generate(self, pages: List[Dict]) -> str:
        """Generate llms.txt content following the exact llms.txt specification"""
        if not pages:
            return "# Website\n\n> No content found.\n"
        
        website_name = self.analyzer.extract_website_name(pages)
        summary = self.analyzer.extract_summary(pages)
        homepage_url = self._get_homepage_url(pages)
        
        homepage = None
        for page in pages:
            parsed = urlparse(page['url'])
            if parsed.path in ['/', '/index', '/index.html']:
                homepage = page
                break
        if not homepage and pages:
            homepage = pages[0]
        
        author_info = None
        contact_links = []
        licensing = None
        languages = []
        main_nav = []
        
        if homepage:
            try:
                author_info = self.metadata_extractor.extract_author_info([homepage])
                contact_links = self.metadata_extractor.extract_contact_links([homepage])
                licensing = self.metadata_extractor.extract_licensing([homepage])
                languages = self.metadata_extractor.extract_languages([homepage])
                main_nav = self.metadata_extractor.extract_main_navigation([homepage])
            except Exception:
                pass
        
        categorized = self.analyzer.group_pages_by_category(pages)
        
        lines = []
        
        lines.append(f"# {website_name}\n")
        
        blockquote_text = self._get_blockquote_text(pages, author_info, summary, homepage_url)
        lines.append(f"> {blockquote_text}\n")
        
        detail_sections = []
        
        if self.llm_service and self.llm_service.is_available():
            try:
                detailed_info = self.llm_service.generate_website_summary(pages)
                if detailed_info and len(detailed_info) > 100:
                    detail_sections.append(detailed_info)
            except:
                pass
        
        if not detail_sections:
            homepage = None
            for page in pages:
                parsed = urlparse(page['url'])
                if parsed.path in ['/', '/index', '/index.html']:
                    homepage = page
                    break
            
            if homepage:
                desc = homepage.get('description', '')
                if desc and len(desc) > 100:
                    detail_sections.append(desc)
                elif homepage.get('raw_text'):
                    text = homepage.get('raw_text', '')[:1000]
                    sentences = [s.strip() for s in text.split('.') if s.strip() and len(s.strip()) > 30]
                    if sentences:
                        detail_sections.append('. '.join(sentences[:3]) + '.')
        
        if author_info and author_info.get('bio'):
            detail_sections.append(author_info['bio'])
        
        if licensing:
            if licensing.startswith('http'):
                detail_sections.append(f"All pages under this site ({homepage_url or 'this site'}) are licensed under [{licensing.split('/')[-1]}]({licensing}).")
            else:
                detail_sections.append(licensing)
        
        if languages and len(languages) > 1:
            detail_sections.append(f"Languages supported: {', '.join(languages)}.")
        
        if detail_sections:
            lines.append("")
            for section in detail_sections:
                lines.append(f"{section}\n")
        
        core_pages = []
        homepage = None
        for page in pages:
            parsed = urlparse(page['url'])
            if parsed.path in ['/', '/index', '/index.html']:
                homepage = page
                core_pages.append(page)
                break
        
        if main_nav:
            for nav_item in main_nav[:10]:
                nav_url = nav_item.get('url', '')
                for page in pages:
                    if page['url'] == nav_url and page not in core_pages:
                        core_pages.append(page)
                        break
        
        important_keywords = ['faq', 'pricing', 'about', 'demo', 'features', 'contact']
        for page in pages:
            if page in core_pages:
                continue
            parsed = urlparse(page['url'])
            path_lower = parsed.path.lower()
            if any(keyword in path_lower for keyword in important_keywords):
                if len(core_pages) < 10:
                    core_pages.append(page)
        
        if core_pages:
            lines.append("\n## Core Pages\n")
            sorted_core = self._sort_pages_by_importance(core_pages)
            for page in sorted_core:
                self._add_page_link(lines, page)
            lines.append("")
        
        if 'services' in categorized and categorized['services']:
            lines.append("\n## Key Features\n")
            sorted_pages = self._sort_pages_by_importance(categorized['services'])
            for page in sorted_pages[:10]:
                self._add_page_link(lines, page)
            lines.append("")
        elif 'products' in categorized and categorized['products']:
            lines.append("\n## Key Features\n")
            sorted_pages = self._sort_pages_by_importance(categorized['products'])
            for page in sorted_pages[:10]:
                self._add_page_link(lines, page)
            lines.append("")
        
        integration_pages = [p for p in pages if 'integration' in p.get('url', '').lower() or 'integration' in p.get('title', '').lower()]
        if integration_pages:
            lines.append("\n## Integrations\n")
            for page in integration_pages[:10]:
                self._add_page_link(lines, page)
            lines.append("")
        
        if 'blog' in categorized and categorized['blog']:
            blog_pages = categorized['blog']
            lines.append("\n## Blog\n")
            
            main_blog = None
            for page in blog_pages:
                parsed = urlparse(page['url'])
                path = parsed.path.rstrip('/')
                if path in ['/blog', '/blog/']:
                    main_blog = page
                    break
            
            if not main_blog and blog_pages:
                main_blog = blog_pages[0]
            
            if main_blog:
                desc = main_blog.get('description', 'Technical articles and posts')
                lines.append(f"- [Blog]({main_blog['url']}): {desc}")
            
            other_blog_pages = [p for p in blog_pages if p != main_blog] if main_blog else blog_pages
            for page in other_blog_pages[:5]:
                self._add_page_link(lines, page)
            lines.append("")
        
        if 'documentation' in categorized and categorized['documentation']:
            lines.append("\n## Documentation\n")
            sorted_pages = self._sort_pages_by_importance(categorized['documentation'])
            for page in sorted_pages[:15]:
                self._add_page_link(lines, page)
            lines.append("")
        
        if 'about' in categorized and categorized['about']:
            lines.append("\n## About\n")
            sorted_pages = self._sort_pages_by_importance(categorized['about'])
            for page in sorted_pages[:5]:
                self._add_page_link(lines, page)
            lines.append("")
        
        if contact_links:
            lines.append("\n## Contact\n")
            for link in contact_links[:10]:
                platform = link.get('platform', '').title()
                url = link.get('url', '')
                text = link.get('text', platform)
                
                if platform.lower() == 'twitter':
                    platform = 'Twitter/X'
                elif platform.lower() == 'ko-fi':
                    platform = 'Ko-fi'
                
                lines.append(f"- [{platform}]({url}): {text}")
            lines.append("")
        elif 'contact' in categorized and categorized['contact']:
            lines.append("\n## Contact\n")
            sorted_pages = self._sort_pages_by_importance(categorized['contact'])
            for page in sorted_pages[:5]:
                self._add_page_link(lines, page)
            lines.append("")
        
        optional_pages = self._get_optional_pages(categorized)
        if optional_pages:
            lines.append("\n## Optional\n")
            for page in optional_pages[:15]:
                self._add_page_link(lines, page)
            lines.append("")
        
        llms_content = '\n'.join(lines)
        
        if self.llm_service and self.llm_service.is_available():
            try:
                improved = self.llm_service.improve_llms_txt_structure(llms_content, pages)
                if improved and len(improved) > 100:
                    return improved
            except Exception:
                pass
        
        return llms_content
    
    def _get_homepage_url(self, pages: List[Dict]) -> str:
        """Get the homepage URL"""
        for page in pages:
            parsed = urlparse(page['url'])
            if parsed.path in ['/', '/index', '/index.html']:
                return page['url']
        return pages[0]['url'] if pages else ''
    
    def _sort_pages_by_importance(self, pages: List[Dict]) -> List[Dict]:
        """Sort pages by importance (homepage first, then by URL depth)"""
        return sorted(
            pages,
            key=lambda p: (
                0 if urlparse(p['url']).path in ['/', '/index'] else 1,
                urlparse(p['url']).path.count('/')
            )
        )
    
    def _add_page_link(self, lines: List[str], page: Dict):
        """Add a page link following llms.txt format: [name](url): description"""
        title = page.get('title', 'Untitled')
        url = page['url']
        description = page.get('description', '')
        
        if description:
            desc = description.strip()
            if len(desc) > 150:
                desc = desc[:147] + '...'
            lines.append(f"- [{title}]({url}): {desc}")
        else:
            lines.append(f"- [{title}]({url})")
    
    def _get_optional_pages(self, categorized: Dict) -> List[Dict]:
        """Get optional/secondary pages"""
        optional = []
        
        if 'other' in categorized:
            optional.extend(categorized['other'][:5])
        
        return optional
    
    def _get_blockquote_text(self, pages: List[Dict], author_info: Optional[Dict], summary: str, homepage_url: str) -> str:
        """Get concise blockquote text"""
        if author_info and author_info.get('title'):
            title = author_info['title']
            if len(title) < 200:
                return title
        
        homepage = None
        for page in pages:
            parsed = urlparse(page['url'])
            if parsed.path in ['/', '/index', '/index.html']:
                homepage = page
                break
        
        if homepage:
            description = homepage.get('description', '')
            if description and 50 < len(description) < 200:
                return description
            
            raw_text = homepage.get('raw_text', '')
            if raw_text:
                sentences = [s.strip() for s in raw_text.split('.') if s.strip() and len(s.strip()) > 30]
                if sentences:
                    text = sentences[0]
                    if len(text) < 200:
                        return text + '.' if not text.endswith('.') else text
        
        if summary and 50 < len(summary) < 200:
            return summary
        
        return homepage_url if homepage_url else (summary[:150] if summary else "A website providing various services and information.")
    
    def _get_rss_feeds(self, pages: List[Dict]) -> List[str]:
        """Get RSS/Atom feed URLs"""
        feeds = []
        
        # Check if we found feeds during crawling
        for page in pages:
            html_content = page.get('html_content', '')
            if not html_content:
                continue
            
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html_content, 'html.parser')
            except ImportError:
                continue
            
            # Look for feed links
            for link in soup.find_all('link', type=lambda x: x and ('rss' in x.lower() or 'atom' in x.lower())):
                href = link.get('href')
                if href:
                    from urllib.parse import urljoin
                    feed_url = urljoin(page['url'], href)
                    if feed_url not in feeds:
                        feeds.append(feed_url)
        
        # Also try common feed paths
        if not feeds and pages:
            base_url = pages[0]['url']
            parsed = urlparse(base_url)
            base = f"{parsed.scheme}://{parsed.netloc}"
            
            common_feeds = [
                '/feed',
                '/rss',
                '/atom',
                '/feed.xml',
                '/rss.xml',
                '/atom.xml',
                '/blog/feed',
                '/blog/rss',
                '/blog/index.xml',
                '/feeds/all.rss'
            ]
            
            for path in common_feeds:
                feeds.append(f"{base}{path}")
        
        return feeds[:3]  # Return up to 3 feeds
    
    def _get_sitemap_urls(self, pages: List[Dict]) -> List[str]:
        """Get sitemap URLs if available"""
        if not pages:
            return []
        
        base_url = pages[0]['url']
        parsed = urlparse(base_url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        
        sitemap_urls = []
        sitemap_paths = ['/sitemap.xml', '/sitemap_index.xml']
        
        for path in sitemap_paths:
            sitemap_urls.append(f"{base}{path}")
        
        return sitemap_urls
    
    def _format_category_name(self, category: str) -> str:
        """Format category name for section heading"""
        category_names = {
            'home': 'Home',
            'about': 'About',
            'contact': 'Contact',
            'services': 'Services',
            'products': 'Products',
            'blog': 'Blog',
            'pricing': 'Pricing',
            'faq': 'FAQ',
            'careers': 'Careers',
            'documentation': 'Documentation',
            'other': 'Pages'
        }
        return category_names.get(category, category.title())

