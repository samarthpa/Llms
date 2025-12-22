import hashlib
import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

def normalize_url(url):
    """Normalize URL by removing fragments and trailing slashes"""
    parsed = urlparse(url)
    normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    if normalized.endswith('/') and len(normalized) > 1:
        normalized = normalized[:-1]
    return normalized

def is_same_domain(url1, url2):
    """Check if two URLs belong to the same domain"""
    domain1 = urlparse(url1).netloc
    domain2 = urlparse(url2).netloc
    return domain1 == domain2

def get_content_hash(content):
    """Generate SHA256 hash of content"""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

def extract_text_from_html(html_content, max_length=500):
    """Extract meaningful text from HTML, limiting length"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    for script in soup(["script", "style", "nav", "footer", "header"]):
        script.decompose()
    
    text = soup.get_text()
    
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = ' '.join(chunk for chunk in chunks if chunk)
    
    if len(text) > max_length:
        text = text[:max_length].rsplit(' ', 1)[0] + '...'
    
    return text

