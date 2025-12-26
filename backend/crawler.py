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
        self.homepage_signature: Dict = {}
        
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

        def _safe_json_load(text: str):
            if not text:
                return None
            t = text.strip()
            if not t:
                return None
            import json
            try:
                return json.loads(t)
            except Exception:
                return None

        def _extract_js_assigned_object(script_text: str, needle: str) -> str:
            if not script_text or needle not in script_text:
                return ""
            idx = script_text.find(needle)
            brace_start = script_text.find("{", idx)
            list_start = script_text.find("[", idx)
            if brace_start == -1 or (list_start != -1 and list_start < brace_start):
                brace_start = list_start
            if brace_start == -1:
                return ""
            open_ch = script_text[brace_start]
            close_ch = "}" if open_ch == "{" else "]"
            depth = 0
            in_str = False
            esc = False
            for i in range(brace_start, min(len(script_text), brace_start + 200000)):
                ch = script_text[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                    continue
                if ch == open_ch:
                    depth += 1
                elif ch == close_ch:
                    depth -= 1
                    if depth == 0:
                        return script_text[brace_start:i+1]
            return ""

        def _looks_like_url(s: str) -> bool:
            if not s:
                return False
            sl = s.strip().lower()
            return sl.startswith('http://') or sl.startswith('https://') or sl.startswith('data:') or sl.startswith('blob:')

        def _looks_like_internal_path(s: str) -> bool:
            if not s:
                return False
            t = s.strip()
            if not t.startswith("/") or t.startswith("//"):
                return False
            tl = t.lower()
            if any(tl.endswith(ext) for ext in ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.json', '.xml', '.woff', '.woff2', '.map', '.pdf', '.zip')):
                return False
            return True

        def _should_keep_string(s: str) -> bool:
            if not s:
                return False
            t = s.strip()
            if len(t) < 25:
                return False
            if _looks_like_url(t):
                return False
            tl = t.lower()
            if any(ext in tl for ext in ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.json', '.xml', '.woff', '.woff2')):
                return False
            if len(t) > 500 and re.fullmatch(r'[A-Za-z0-9+/=\s]+', t):
                return False
            non_text = sum(1 for c in t if not (c.isalnum() or c.isspace() or c in ".,;:!?'-()[]/"))
            if non_text > max(10, int(len(t) * 0.2)):
                return False
            return True

        def _collect_json(obj, strings_out: List[str], urls_out: List[str]):
            if obj is None:
                return
            if isinstance(obj, str):
                s = obj.strip()
                if _looks_like_internal_path(s):
                    urls_out.append(s)
                    return
                if _looks_like_url(s):
                    try:
                        if is_same_domain(s, self.base_url):
                            urls_out.append(s)
                    except Exception:
                        pass
                    return
                if _should_keep_string(s):
                    strings_out.append(s)
                return
            if isinstance(obj, (int, float, bool)):
                return
            if isinstance(obj, list):
                for item in obj:
                    _collect_json(item, strings_out, urls_out)
                return
            if isinstance(obj, dict):
                for _, v in obj.items():
                    _collect_json(v, strings_out, urls_out)

        def _extract_structured_from_scripts(soup_obj: BeautifulSoup) -> Tuple[str, List[str], List[Dict]]:
            strings: List[str] = []
            urls: List[str] = []
            jsonld_objs: List[Dict] = []

            next_data = soup_obj.find('script', id='__NEXT_DATA__')
            if next_data and (next_data.get('type') in (None, '', 'application/json')):
                parsed = _safe_json_load(next_data.get_text())
                if parsed is not None:
                    _collect_json(parsed, strings, urls)

            for s in soup_obj.find_all('script', type='application/ld+json'):
                parsed = _safe_json_load(s.get_text())
                if parsed is not None:
                    if isinstance(parsed, dict):
                        jsonld_objs.append(parsed)
                    elif isinstance(parsed, list):
                        for item in parsed:
                            if isinstance(item, dict):
                                jsonld_objs.append(item)
                    _collect_json(parsed, strings, urls)

            nuxt = soup_obj.find('script', id='__NUXT__')
            if nuxt:
                parsed = _safe_json_load(nuxt.get_text())
                if parsed is not None:
                    _collect_json(parsed, strings, urls)

            for s in soup_obj.find_all('script', type='application/json'):
                parsed = _safe_json_load(s.get_text())
                if parsed is not None:
                    _collect_json(parsed, strings, urls)

            for s in soup_obj.find_all('script'):
                txt = (s.get_text() or "").strip()
                if not txt or len(txt) > 200000:
                    continue
                if txt.startswith("{") or txt.startswith("["):
                    parsed = _safe_json_load(txt)
                    if parsed is not None:
                        _collect_json(parsed, strings, urls)
                        continue
                if "window.__NUXT__" in txt or "__NUXT__" in txt:
                    snippet = _extract_js_assigned_object(txt, "window.__NUXT__")
                    if not snippet:
                        snippet = _extract_js_assigned_object(txt, "__NUXT__")
                    if snippet:
                        parsed = _safe_json_load(snippet)
                        if parsed is not None:
                            _collect_json(parsed, strings, urls)

            strings_sorted = sorted(strings, key=lambda x: len(x), reverse=True)
            uniq: List[str] = []
            seen = set()
            for part in strings_sorted:
                p = part.strip()
                if not p:
                    continue
                norm = re.sub(r'\s+', ' ', p.lower())
                if norm in seen:
                    continue
                seen.add(norm)
                uniq.append(p)
                if len(uniq) >= 200:
                    break

            structured_text = "\n".join(uniq)[:8000]

            urls_uniq: List[str] = []
            seen_u = set()
            for u in urls:
                if not u:
                    continue
                if u.startswith("/"):
                    full = normalize_url(urljoin(self.base_url, u))
                else:
                    full = normalize_url(u)
                if full in seen_u:
                    continue
                seen_u.add(full)
                urls_uniq.append(full)
                if len(urls_uniq) >= 20:
                    break

            return structured_text, urls_uniq, jsonld_objs

        def _extract_best_description(og_desc: str, meta_desc: str, jsonld_objs: List[Dict], structured_text: str) -> str:
            if og_desc:
                return og_desc
            if meta_desc:
                return meta_desc
            best = ""
            for obj in jsonld_objs:
                v = obj.get("description")
                if isinstance(v, str):
                    vv = v.strip()
                    if 40 <= len(vv) <= 240 and len(vv) > len(best):
                        best = vv
            if best:
                return best
            if structured_text:
                first = structured_text.split("\n", 1)[0].strip()
                if 40 <= len(first) <= 240:
                    return first
            main = soup.find("main") or soup.find("header")
            if main:
                h1 = main.find("h1")
                p = main.find("p")
                parts = []
                if h1:
                    parts.append(h1.get_text(" ", strip=True))
                if p:
                    parts.append(p.get_text(" ", strip=True))
                cand = re.sub(r"\s+", " ", " ".join([x for x in parts if x])).strip()
                if 40 <= len(cand) <= 240:
                    return cand
            return ""

        def _extract_main_text(soup_obj: BeautifulSoup) -> str:
            working = BeautifulSoup(str(soup_obj), "html.parser")
            for t in working(["script", "style", "noscript", "nav", "header", "footer", "aside"]):
                t.decompose()
            main = working.find("main") or working.find("article")
            if main:
                text = main.get_text("\n", strip=True)
                text = re.sub(r"\n{2,}", "\n", text)
                return text.strip()
            candidates = working.find_all(["section", "div"])
            best_text = ""
            best_len = 0
            for c in candidates:
                txt = c.get_text(" ", strip=True)
                txt = re.sub(r"\s+", " ", txt).strip()
                if len(txt) > best_len:
                    best_len = len(txt)
                    best_text = txt
            return best_text.strip()

        def _first_good_paragraph(main_text: str) -> str:
            if not main_text:
                return ""
            parts = [p.strip() for p in re.split(r"\n+", main_text) if p.strip()]
            for p in parts:
                p2 = re.sub(r"\s+", " ", p).strip()
                if 80 <= len(p2) <= 300 and re.search(r"[.!?]", p2):
                    return p2
            for p in parts:
                p2 = re.sub(r"\s+", " ", p).strip()
                if 80 <= len(p2) <= 300:
                    return p2
            return ""

        def _norm_desc(s: str) -> str:
            if not s:
                return ""
            t = re.sub(r"\s+", " ", s.strip().lower())
            return t.rstrip(".!?:;,'\"")

        def _compute_visible_signature(soup_obj: BeautifulSoup) -> Tuple[str, int, str]:
            cleaned = BeautifulSoup(str(soup_obj), "html.parser")
            for t in cleaned(["script", "style", "noscript"]):
                t.decompose()
            text = cleaned.get_text(" ", strip=True)
            text = re.sub(r"\s+", " ", text).strip()
            return get_content_hash(text), len(text), text[:2000]

        def _is_soft_404(meta: Dict, home_sig: Dict) -> bool:
            if not home_sig:
                return False
            if normalize_url(meta.get("url", "")) == normalize_url(home_sig.get("url", "")):
                return False
            t = (meta.get("visible_text") or "").lower()
            if any(p in t for p in ("not found", "page not found", "404", "doesn't exist", "does not exist", "could not be found")):
                return True
            canon = meta.get("canonical") or ""
            ogu = meta.get("og_url") or ""
            if canon and normalize_url(canon) == normalize_url(home_sig.get("url", "")):
                return True
            if ogu and normalize_url(ogu) == normalize_url(home_sig.get("url", "")):
                return True
            if (meta.get("title") or "").strip() and (meta.get("best_description") or "").strip():
                if (meta.get("title") or "").strip() == (home_sig.get("title") or "").strip() and (meta.get("best_description") or "").strip() == (home_sig.get("best_description") or "").strip():
                    if meta.get("visible_text_len", 0) < 200:
                        return True
            if meta.get("visible_hash") and meta.get("visible_hash") == home_sig.get("visible_hash") and meta.get("visible_text_len", 0) < 400:
                return True
            return False

        title = None
        if soup.title:
            title = soup.title.get_text().strip()
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            title = og_title.get('content').strip()

        og_desc = None
        og_desc_tag = soup.find('meta', property='og:description')
        if og_desc_tag and og_desc_tag.get('content'):
            og_desc = og_desc_tag.get('content').strip()

        meta_desc = None
        meta_desc_tag = soup.find('meta', attrs={'name': 'description'})
        if meta_desc_tag and meta_desc_tag.get('content'):
            meta_desc = meta_desc_tag.get('content').strip()

        description = meta_desc or og_desc
        if not description:
            first_p = soup.find('p')
            if first_p:
                description = extract_text_from_html(str(first_p), max_length=200)

        canonical = None
        canon_tag = soup.find('link', rel='canonical')
        if canon_tag and canon_tag.get('href'):
            canonical = canon_tag.get('href').strip()

        og_url = None
        og_url_tag = soup.find('meta', property='og:url')
        if og_url_tag and og_url_tag.get('content'):
            og_url = og_url_tag.get('content').strip()

        raw_text = extract_text_from_html(html_content, max_length=2000)
        structured_text, structured_urls, jsonld_objs = _extract_structured_from_scripts(soup)
        if structured_text:
            raw_text = (raw_text or "").strip()
            merged = (raw_text + "\n\n" + structured_text).strip() if raw_text else structured_text
            raw_text = merged[:4000]

        main_text = _extract_main_text(soup)
        main_para = _first_good_paragraph(main_text)

        best_description = main_para or ""
        if not best_description:
            if structured_text:
                first = structured_text.split("\n", 1)[0].strip()
                if 80 <= len(first) <= 300 and re.search(r"[.!?]", first):
                    best_description = first
        if not best_description:
            best_description = _extract_best_description(og_desc, meta_desc, jsonld_objs, structured_text) or (description or "")

        visible_hash, visible_len, visible_text = _compute_visible_signature(soup)

        meta_out = {
            'url': url,
            'title': title or 'Untitled',
            'description': description,
            'best_description': best_description,
            'canonical': canonical,
            'og_url': og_url,
            'structured_text': structured_text,
            'structured_urls': structured_urls,
            'main_text': main_text[:8000],
            'visible_hash': visible_hash,
            'visible_text_len': visible_len,
            'visible_text': visible_text,
        }

        if self.homepage_signature and normalize_url(url) != normalize_url(self.homepage_signature.get("url", "")):
            home_desc_norm = _norm_desc(self.homepage_signature.get("best_description") or "")
            cand_norm = _norm_desc(meta_out.get("best_description") or "")
            if home_desc_norm and cand_norm and cand_norm == home_desc_norm:
                alt = _first_good_paragraph(main_text)
                if alt and _norm_desc(alt) != home_desc_norm:
                    meta_out["best_description"] = alt
                elif structured_text:
                    alt2 = structured_text.split("\n", 1)[0].strip()
                    if alt2 and _norm_desc(alt2) != home_desc_norm:
                        meta_out["best_description"] = alt2
                    else:
                        meta_out["best_description"] = ""
                else:
                    meta_out["best_description"] = ""

        meta_out["is_soft_404"] = _is_soft_404(meta_out, self.homepage_signature)

        content_hash = get_content_hash(html_content)
        meta_out.update({
            'content_hash': content_hash,
            'html_content': html_content,
            'raw_text': raw_text
        })

        return meta_out
    
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
            metadata = self.pages[-1]

        if normalize_url(url) == normalize_url(self.base_url) and not self.homepage_signature:
            self.homepage_signature = {
                "url": metadata.get("url"),
                "title": metadata.get("title"),
                "best_description": metadata.get("best_description") or metadata.get("description") or "",
                "canonical": metadata.get("canonical") or "",
                "og_url": metadata.get("og_url") or "",
                "visible_hash": metadata.get("visible_hash") or "",
                "visible_text_len": metadata.get("visible_text_len") or 0,
            }

        if metadata.get("is_soft_404"):
            return [], []
        
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

            structured_urls = metadata.get("structured_urls") or []
            if structured_urls:
                extras = []
                for u in structured_urls:
                    nu = normalize_url(u)
                    if nu not in nav_links and nu not in other_links and is_same_domain(nu, self.base_url):
                        extras.append(nu)
                    if len(extras) >= 20:
                        break
                other_links = (extras + other_links)[:30]
        except Exception:
            pass
        
        return nav_links, other_links
    
    def _is_locale_segment(self, seg: str) -> bool:
        """Generic locale detection for path segments."""
        if not seg:
            return False
        if re.match(r'^[a-z]{2}$', seg):
            return True
        if re.match(r'^[a-z]{2}-[A-Z]{2}$', seg) or re.match(r'^[a-z]{2}-[a-z]{2}$', seg):
            return True
        if re.match(r'^[a-z]{3}$', seg):
            return True
        return False

    def _strip_locale(self, url: str) -> str:
        """Strip locale segment from start of path for canonical grouping."""
        parsed = urlparse(url)
        path = parsed.path.strip('/')
        segments = path.split('/')
        if segments and self._is_locale_segment(segments[0]):
            new_path = '/' + '/'.join(segments[1:])
            return f"{parsed.netloc}{new_path.rstrip('/')}"
        return f"{parsed.netloc}/{path.rstrip('/')}"

    def _dedupe_urls_by_locale(self, urls: List[str]) -> List[str]:
        """Group URLs by canonical path (no locale) and pick the best representative."""
        if not urls:
            return []
        groups = {}
        for url in urls:
            key = self._strip_locale(url)
            if key not in groups:
                groups[key] = []
            groups[key].append(url)
        deduped = []
        for key, members in groups.items():
            if len(members) == 1:
                deduped.append(members[0])
                continue
            english = [u for u in members if any(seg.startswith('en') and self._is_locale_segment(seg) 
                                                 for seg in urlparse(u).path.strip('/').split('/'))]
            if english:
                deduped.append(min(english, key=lambda x: (x.count('/'), len(x))))
                continue
            best = min(members, key=lambda x: (x.count('/'), len(x)))
            deduped.append(best)
        return deduped

    def crawl(self) -> List[Dict]:
        """
        Main crawling method using priority-tier BFS.
        Priority BFS: nav first, then other; dominance deferral bounded (max 3 deferrals per URL).
        Strict FIFO order within each depth level.
        """
        self._check_robots_txt()

        try:
            if not self.homepage_signature and self._can_fetch(self.base_url):
                resp = self._fetch_page(self.base_url)
                if resp and resp.status_code == 200:
                    ct = (resp.headers.get("Content-Type") or "").lower()
                    if "text/html" in ct or "application/xhtml" in ct:
                        meta = self._extract_metadata(self.base_url, resp.text)
                        self.homepage_signature = {
                            "url": meta.get("url"),
                            "title": meta.get("title"),
                            "best_description": meta.get("best_description") or meta.get("description") or "",
                            "canonical": meta.get("canonical") or "",
                            "og_url": meta.get("og_url") or "",
                            "visible_hash": meta.get("visible_hash") or "",
                            "visible_text_len": meta.get("visible_text_len") or 0,
                        }
        except Exception:
            pass
        
        self.defer_counts.clear()
        MAX_DEFERS = 3
        
        nav_queues = [deque() for _ in range(self.max_depth + 1)]
        other_queues = [deque() for _ in range(self.max_depth + 1)]
        queued_urls: Set[str] = set()
        
        sitemap_urls = self._parse_sitemap()
        if sitemap_urls:
            deduped_sitemaps = self._dedupe_urls_by_locale(sitemap_urls)
            for url in deduped_sitemaps[:self.max_pages]:
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

