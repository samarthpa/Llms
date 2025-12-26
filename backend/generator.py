from typing import List, Dict, Optional
from analyzer import ContentAnalyzer
from urllib.parse import urlparse
from llm_service import LLMService
from metadata_extractor import MetadataExtractor
from bs4 import BeautifulSoup
import logging
import requests
import re

logger = logging.getLogger(__name__)

class LLMsTxtGenerator:
    def __init__(self, use_llm: bool = True, include_blog: bool = False, 
                 include_sitemaps: bool = False, max_core_pages: int = 6, 
                 max_key_features: int = 8):
        self.analyzer = ContentAnalyzer(use_llm=use_llm)
        self.llm_service = LLMService(require_api_key=True)
        self.metadata_extractor = MetadataExtractor()
        self.session = requests.Session()
        
        self.include_blog = include_blog
        self.include_sitemaps = include_sitemaps
        self.max_core_pages = max_core_pages
        self.max_key_features = max_key_features
        self.allowed_urls = set()

    def _normalize_url(self, url: str, base_url: str = "") -> str:
        if not url:
            return ""
        if url.startswith('/') and base_url:
            from urllib.parse import urljoin
            url = urljoin(base_url, url)
        parsed = urlparse(url)
        path = (parsed.path or "").rstrip('/')
        return f"{parsed.netloc.lower()}{path}"

    def _segments_no_locale(self, url: str) -> List[str]:
        segs = self._path_segments(url)
        if segs and self._is_locale_segment(segs[0]):
            return segs[1:]
        return segs

    def _normalize_text_for_compare(self, text: str) -> str:
        """Normalize text for equality checks (lowercase, collapse whitespace, strip trailing punctuation)."""
        if not text:
            return ""
        t = text.strip().lower()
        t = re.sub(r'\s+', ' ', t)
        t = t.strip().rstrip('.!?:;,"\'')
        return t

    def is_legal_page(self, url: str) -> bool:
        """Heuristic: legal/policy pages (locale-stripped, segment-based)."""
        segs = self._segments_no_locale(url)
        legal_tokens = {"terms", "privacy", "cookie", "cookies", "legal", "security", "policy"}
        return any(any(tok in seg for tok in legal_tokens) for seg in segs)

    def is_content_page(self, url: str) -> bool:
        """Heuristic: blog/resources/guide/content hubs (locale-stripped, segment-based)."""
        segs = self._segments_no_locale(url)
        content_tokens = {"blog", "post", "article", "topic", "topics", "resource", "resources", "guide", "free-guide", "ideas", "tips"}
        return any(any(tok in seg for tok in content_tokens) for seg in segs)

    def _verify_sitemap(self, url: str) -> bool:
        """Verify sitemap is XML and reachable."""
        try:
            resp = self.session.get(url, timeout=5, stream=True)
            if resp.status_code == 200:
                content_type = resp.headers.get('Content-Type', '').lower()
                if 'xml' in content_type:
                    return True
                chunk = next(resp.iter_content(chunk_size=512), b"").decode('utf-8', 'ignore')
                if '<?xml' in chunk or '<urlset' in chunk or '<sitemapindex' in chunk:
                    return True
        except Exception:
            pass
        return False

    def _path_segments(self, url: str) -> List[str]:
        path = urlparse(url).path.strip('/')
        return [s for s in path.split('/') if s]

    def _path_depth(self, url: str) -> int:
        return len(self._path_segments(url))

    def _looks_like_article(self, url: str) -> bool:
        """Heuristics to detect articles/long-tail content."""
        segments = self._path_segments(url)
        if not segments:
            return False
            
        slug = segments[-1]
        if len(slug) > 40:
            return True
            
        if any(re.match(r'^\d{4}$|^\d{2}$', s) for s in segments):
            return True
            
        if len(segments) > 3:
            return True
            
        return False

    def _score_core_page(self, page: Dict) -> int:
        """Score page importance for Core Pages selection."""
        url = page['url']
        path = urlparse(url).path.lower().rstrip('/')
        
        if path == '' or path == '/':
            return 100
            
        score = 0
        keywords = {
            '/pricing': 90,
            '/about': 85,
            '/contact': 80,
            '/help': 75,
            '/support': 75,
            '/docs': 70,
            '/documentation': 70,
            '/terms': 60,
            '/privacy': 60,
        }
        
        for kw, val in keywords.items():
            if kw in path:
                score += val
                break
                
        depth = self._path_depth(url)
        score += (10 - depth) * 2
        
        return score

    def generate(self, pages: List[Dict]) -> str:
        if not pages:
            return "# Website\n\n> No content found.\n"

        pages = [p for p in pages if not p.get("is_soft_404")]
        
        homepage_url = self._get_homepage_url(pages)
        self.allowed_urls = {self._normalize_url(p['url']) for p in pages}
        allowed_urls_full = sorted({p.get('url') for p in pages if p.get('url')})
        
        sitemaps = []
        if self.include_sitemaps:
            candidates = [f"{homepage_url.rstrip('/')}/sitemap.xml", f"{homepage_url.rstrip('/')}/sitemap_index.xml"]
            for sm in candidates:
                if self._verify_sitemap(sm):
                    sitemaps.append(sm)
                    self.allowed_urls.add(self._normalize_url(sm))
                    allowed_urls_full.append(sm)

        pages = self._dedupe_pages_by_canonical_url(pages)
        website_name = self.analyzer.extract_website_name(pages)
        summary = self.analyzer.extract_summary(pages)
        
        homepage = next((p for p in pages if urlparse(p['url']).path in ['/', '/index', '/index.html']), pages[0])
        
        author_info = None
        contact_links = []
        licensing = None
        languages = []
        main_nav = []
        
        try:
            author_info = self.metadata_extractor.extract_author_info([homepage])
            contact_links = self.metadata_extractor.extract_contact_links([homepage])
            licensing = self.metadata_extractor.extract_licensing([homepage])
            languages = self.metadata_extractor.extract_languages(pages) # Use all pages for lang
            main_nav = self.metadata_extractor.extract_main_navigation([homepage])
        except Exception:
            pass
        
        lines = []
        lines.append(f"# {website_name}\n")
        
        blockquote_text = self._get_blockquote_text(pages, author_info, summary, homepage_url)
        lines.append(f"> {blockquote_text}\n")
        
        detail_sections = []
        blockquote_norm = self._normalize_text_for_compare(blockquote_text)

        def _add_detail(text: str):
            if not text:
                return
            candidate = text.strip()
            if not candidate:
                return
            if self._normalize_text_for_compare(candidate) == blockquote_norm:
                return
            if any(self._normalize_text_for_compare(s) == self._normalize_text_for_compare(candidate) for s in detail_sections):
                return
            detail_sections.append(candidate)

        if self.include_blog and self.llm_service and self.llm_service.is_available():
            try:
                detailed_info = self.llm_service.generate_website_summary(pages)
                if detailed_info and len(detailed_info) > 100:
                    _add_detail(detailed_info)
            except:
                pass

        if homepage:
            desc = homepage.get('description', '')
            if desc and len(desc) > 100:
                _add_detail(desc)
            elif homepage.get('raw_text'):
                raw = (homepage.get('raw_text') or '').strip()
                if raw:
                    _add_detail(raw[:400])
        
        if licensing:
            _add_detail(f"Licensed under: {licensing}")
            
        if languages and len(languages) <= 5:
            _add_detail(f"Languages supported: {', '.join(languages)}.")
        
        if detail_sections:
            lines.append("")
            for section in detail_sections:
                lines.append(f"{section}\n")
        
        intent_first_segments = {'pricing', 'about', 'contact', 'help', 'support', 'docs', 'documentation'}

        core_candidates: List[Dict] = []
        for p in pages:
            url = p['url']
            path = urlparse(url).path.lower()
            is_home = path in ['', '/']
            segs = self._segments_no_locale(url)

            if not is_home and len(segs) > 2:
                continue
            if self.is_content_page(url) or self.is_legal_page(url):
                continue

            if is_home:
                core_candidates.append(p)
                continue

            if segs and segs[0] in intent_first_segments:
                core_candidates.append(p)
        
        core_candidates.sort(key=lambda x: self._score_core_page(x), reverse=True)
        selected_core = core_candidates[:self.max_core_pages]
        
        if selected_core:
            lines.append("\n## Core Pages\n")
            for page in selected_core:
                self._add_page_link(lines, page)
            lines.append("")

        def _pick_section(pages_in: List[Dict], keywords: List[str], max_items: int = 5) -> List[Dict]:
            out: List[Dict] = []
            seen = set()
            for p in pages_in:
                u = p.get("url", "")
                if not u:
                    continue
                if self._normalize_url(u) in seen:
                    continue
                t = (p.get("title") or "").lower()
                segs = self._segments_no_locale(u)
                if any(k in t for k in keywords) or any(k in segs for k in keywords) or any(k in u.lower() for k in keywords):
                    out.append(p)
                    seen.add(self._normalize_url(u))
                if len(out) >= max_items:
                    break
            return out

        about_pages = _pick_section(pages, ["about", "team", "company"], 5)
        services_pages = _pick_section(pages, ["services", "service", "solutions", "offerings"], 5)
        approach_pages = _pick_section(pages, ["approach", "process", "method", "methodology"], 5)
        contact_pages = _pick_section(pages, ["contact", "support", "help"], 5)

        if about_pages:
            lines.append("\n## About\n")
            for p in about_pages:
                self._add_page_link(lines, p)
            lines.append("")

        if services_pages:
            lines.append("\n## Services\n")
            for p in services_pages:
                self._add_page_link(lines, p)
            lines.append("")

        if approach_pages:
            lines.append("\n## Approach\n")
            for p in approach_pages:
                self._add_page_link(lines, p)
            lines.append("")

        if contact_pages:
            lines.append("\n## Contact\n")
            for p in contact_pages:
                self._add_page_link(lines, p)
            lines.append("")

        categorized = self.analyzer.group_pages_by_category(pages)
        features = categorized.get('services', []) + categorized.get('products', [])
        
        filtered_features: List[Dict] = []
        seen_feature_urls: set = set()
        feature_exclude_keywords = ['generator', 'ideas', 'design-', 'room-', 'home-']
        bad_slug_tokens = {"free", "guide", "ideas", "generator", "tool", "tips", "2024", "2025"}
        
        for f in features:
            url = f['url']
            segs = self._segments_no_locale(url)
            slug = segs[-1] if segs else ""
            
            if self._normalize_url(url, homepage_url) in seen_feature_urls:
                continue
            if f in selected_core:
                continue

            if self.is_legal_page(url) or self.is_content_page(url):
                continue

            if len(slug) > 25:
                continue
            if any(tok in slug.lower() for tok in bad_slug_tokens):
                continue
            if any(char.isdigit() for char in slug):
                continue
            if len(segs) >= 3:
                continue
            if any(kw in url.lower() for kw in feature_exclude_keywords):
                continue

            desc = (f.get('description') or '').strip()
            raw = (f.get('raw_text') or '').strip()
            if len(desc) < 40 and len(raw) < 300:
                continue

            filtered_features.append(f)
            seen_feature_urls.add(self._normalize_url(url, homepage_url))
        
        if filtered_features:
            lines.append("\n## Key Features\n")
            cap = min(self.max_key_features, 5)
            for page in filtered_features[:cap]:
                self._add_page_link(lines, page)
            lines.append("")
            
        if self.include_blog and categorized.get('blog'):
            lines.append("\n## Blog\n")
            for page in categorized['blog'][:5]:
                self._add_page_link(lines, page)
            lines.append("")
            
        if sitemaps:
            lines.append("\n## Sitemaps\n")
            for sm in sitemaps:
                lines.append(f"- [Sitemap]({sm})")
            lines.append("")
            
        outline = '\n'.join(lines)

        evidence_parts: List[str] = []
        for p in pages[:40]:
            evidence_parts.append(
                f"URL: {p.get('url')}\n"
                f"Title: {p.get('title')}\n"
                f"Description: {(p.get('best_description') or p.get('description') or '')}\n"
                f"Text: {(p.get('raw_text') or '')[:600]}\n"
            )
        evidence_pack = "\n---\n".join(evidence_parts)

        llms_content = self.llm_service.render_llms_txt(
            outline_markdown=outline,
            evidence_pack=evidence_pack,
            allowed_urls=allowed_urls_full,
            include_blog=self.include_blog,
        )

        blockquote_norm = self._normalize_text_for_compare(blockquote_text)
        sanitized_lines: List[str] = []
        for line in llms_content.split('\n'):
            stripped = line.strip()
            if stripped and not stripped.startswith(('>','-','#')):
                if self._normalize_text_for_compare(stripped) == blockquote_norm:
                    continue
                if not self.include_blog and re.search(r'\b(blog|resources?|guides?|topics?)\b', stripped, re.I):
                    continue
            if stripped.lower().startswith("languages supported:"):
                codes = [c.strip() for c in stripped.split(':', 1)[-1].split(',') if c.strip()]
                if len(codes) > 5:
                    continue
            sanitized_lines.append(line)
        llms_content = "\n".join(sanitized_lines)

        def _strip_section(lines_in: List[str], heading: str) -> List[str]:
            out = []
            skipping = False
            for ln in lines_in:
                if ln.strip().lower() == heading.lower():
                    skipping = True
                    continue
                if skipping and ln.startswith("## "):
                    skipping = False
                if not skipping:
                    out.append(ln)
            return out

        lines_after = llms_content.split("\n")
        if not self.include_blog:
            lines_after = _strip_section(lines_after, "## Blog")

        strict_lines: List[str] = []
        link_line_re = re.compile(r'^-\s+\[[^\]]+\]\([^)]+\)(:\s+.*)?$')
        paragraphs_allowed = 2
        paragraphs_used = 0
        seen_heading = False
        for ln in lines_after:
            s = ln.rstrip()
            st = s.strip()
            if st == "":
                strict_lines.append("")
                continue
            if st.startswith("# "):
                strict_lines.append(s)
                continue
            if st.startswith(">"):
                strict_lines.append(s)
                continue
            if st.startswith("## "):
                seen_heading = True
                strict_lines.append(s)
                continue
            if st.startswith("- "):
                if link_line_re.match(st):
                    strict_lines.append(s)
                continue
            if not seen_heading and not st.startswith("[") and not st.startswith("(") and "http" not in st and paragraphs_used < paragraphs_allowed:
                strict_lines.append(s)
                paragraphs_used += 1
                continue
            continue

        llms_content = "\n".join(strict_lines)

        validated_lines = []
        home_netloc = urlparse(homepage_url).netloc
        for line in llms_content.split('\n'):
            matches = re.findall(r'\[.*?\]\((.*?)\)', line)
            if matches:
                all_allowed = True
                for link_url in matches:
                    if link_url.startswith('#'): continue
                    parsed_link = urlparse(link_url)
                    if parsed_link.netloc == home_netloc or (not parsed_link.netloc and parsed_link.path):
                        norm = self._normalize_url(link_url, homepage_url)
                        if norm not in self.allowed_urls:
                            all_allowed = False
                            break
                if all_allowed: validated_lines.append(line)
            else:
                validated_lines.append(line)
        return '\n'.join(validated_lines)

    def _get_homepage_url(self, pages: List[Dict]) -> str:
        for page in pages:
            parsed = urlparse(page['url'])
            if parsed.path in ['/', '/index', '/index.html']:
                return page['url']
        return pages[0]['url'] if pages else ''

    def _add_page_link(self, lines: List[str], page: Dict):
        title = page.get('title', 'Untitled')
        url = page['url']
        if self._normalize_url(url) not in self.allowed_urls:
            return
        description = page.get('best_description') or page.get('description', '')
        if description:
            desc = description.strip()
            if len(desc) > 150: desc = desc[:147] + '...'
            lines.append(f"- [{title}]({url}): {desc}")
        else:
            lines.append(f"- [{title}]({url})")

    def _get_blockquote_text(self, pages: List[Dict], author_info: Optional[Dict], summary: str, homepage_url: str) -> str:
        homepage = next((p for p in pages if urlparse(p['url']).path in ['/', '/index']), pages[0] if pages else None)
        if homepage:
            desc = (homepage.get('description') or '').strip()
            if 50 < len(desc) < 220: return desc
        if self.llm_service and self.llm_service.is_available() and homepage:
            one_liner = self.llm_service.generate_one_liner(
                self.analyzer.extract_website_name(pages), 
                homepage.get('title', ''), 
                homepage.get('description', ''), 
                homepage.get('raw_text', '')
            )
            if one_liner: return one_liner
        return f"Official site for {homepage_url.split('//')[-1].split('/')[0] if homepage_url else 'this website'}."

    def _is_locale_segment(self, seg: str) -> bool:
        if not seg: return False
        return bool(re.match(r'^[a-z]{2}$', seg) or re.match(r'^[a-z]{2}-[A-Z]{2}$', seg) or re.match(r'^[a-z]{2}-[a-z]{2}$', seg) or re.match(r'^[a-z]{3}$', seg))

    def _strip_locale(self, url: str) -> str:
        parsed = urlparse(url)
        segments = parsed.path.strip('/').split('/')
        if segments and self._is_locale_segment(segments[0]):
            return f"{parsed.netloc}/{'/'.join(segments[1:])}".rstrip('/')
        return f"{parsed.netloc}/{parsed.path.strip('/')}".rstrip('/')

    def _dedupe_pages_by_canonical_url(self, pages: List[Dict]) -> List[Dict]:
        groups = {}
        for p in pages:
            key = self._strip_locale(p['url'])
            groups.setdefault(key, []).append(p)
        deduped = []
        for members in groups.values():
            if len(members) == 1:
                deduped.append(members[0])
            else:
                english = [m for m in members if any(seg.startswith('en') and self._is_locale_segment(seg) for seg in self._path_segments(m['url']))]
                deduped.append(min(english if english else members, key=lambda x: (x['url'].count('/'), len(x['url']))))
        return deduped
