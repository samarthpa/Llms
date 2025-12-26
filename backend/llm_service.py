import os
import re
from openai import OpenAI
from typing import List, Dict
from urllib.parse import urlparse
import logging

logger = logging.getLogger(__name__)

class LLMService:
    def __init__(self, require_api_key: bool = False):
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            if require_api_key:
                raise ValueError("OPENAI_API_KEY environment variable is required.")
            logger.warning("OPENAI_API_KEY not found. LLM features will be disabled.")
            self.client = None
        else:
            try:
                self.client = OpenAI(api_key=api_key)
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
                self.client = None
    
    def is_available(self):
        return self.client is not None

    def _validate_llm_output(self, output: str, context: str) -> bool:
        if not output or not context:
            return True
        context_lower = context.lower()
        words = re.findall(r'\b[A-Z][a-z]{2,}\b', output)
        for word in words:
            if word.lower() not in context_lower:
                logger.warning(f"Hallucination check failed: found '{word}' in output but not in context.")
                return False
        return True

    def generate_one_liner(self, site_name: str, title: str, description: str, raw_text: str) -> str:
        if not self.is_available():
            return None
        try:
            prompt = f"""Generate one concise descriptive sentence for the website "{site_name}".
RULES:
1. Use ONLY words or facts present in the provided context.
2. Do NOT guess the business type or add new facts.
3. If uncertain, return a generic but factual description based ONLY on the title.
4. Max 180 characters.
CONTEXT:
Title: {title}
Description: {description}
Content Sample: {raw_text[:1000]}
Response:"""
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a factual summarizer. Do NOT hallucinate. Low temperature set."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=60,
                temperature=0.2
            )
            result = response.choices[0].message.content.strip().strip('"')
            if self._validate_llm_output(result, f"{site_name} {title} {description} {raw_text[:1000]}"):
                return result
            return None
        except Exception:
            return None

    def improve_llms_txt_structure(self, llms_content: str, pages: List[Dict]) -> str:
        if not self.is_available():
            return llms_content
        try:
            evidence_parts = []
            for p in pages[:15]:
                evidence_parts.append(f"URL: {p['url']}\nTitle: {p.get('title')}\nDesc: {p.get('description', '')[:150]}")
            evidence = "\n\n".join(evidence_parts)
            prompt = f"""Review and improve this llms.txt file. 
HARD RULES:
1. Do NOT introduce any new product claims, pricing, or features not present in the evidence or original content.
2. You may only reorder, shorten, and rephrase existing content.
3. If uncertain about a fact, OMIT it.
4. Ensure all link lists follow the [name](url): description format.
5. Return ONLY the improved markdown starting with #.
EVIDENCE PACK:
{evidence}
ORIGINAL CONTENT:
{llms_content}
Improved llms.txt:"""
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a strictly factual editor. Do NOT add new information. Keep temperature low."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000,
                temperature=0.2
            )
            improved = response.choices[0].message.content.strip()
            if not improved.startswith('#'):
                return llms_content
            if self._validate_llm_output(improved, f"{llms_content} {evidence}"):
                return improved
            return llms_content
        except Exception as e:
            logger.error(f"Error improving structure: {e}")
            return llms_content

    def generate_website_summary(self, pages: List[Dict]) -> str:
        if not self.is_available():
            return None
        try:
            homepage = next((p for p in pages if urlparse(p['url']).path in ['/', '/index']), pages[0] if pages else None)
            if not homepage: return None
            prompt = f"""Generate a 2-paragraph summary based ONLY on the following info.
SITE TITLE: {homepage.get('title')}
HOME DESCRIPTION: {homepage.get('description')}
DISCOVERED PAGES: {", ".join([p.get('title', 'Untitled') for p in pages[:8]])}
"""
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a factual summarizer. Do NOT use external knowledge. Temperature 0.2."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300,
                temperature=0.2
            )
            return response.choices[0].message.content.strip()
        except Exception:
            return None

    def categorize_page_intelligently(self, url: str, title: str, description: str, content_preview: str) -> str:
        if not self.is_available():
            return None
        try:
            categories = ['home', 'about', 'contact', 'services', 'products', 'blog', 'pricing', 'faq', 'careers', 'documentation', 'other']
            prompt = f"""Categorize this webpage:
URL: {url}
Title: {title}
Description: {description}
Categories: {', '.join(categories)}
Return ONLY the category name."""
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a categorization assistant. Return ONLY the category name."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=20,
                temperature=0.2
            )
            cat = response.choices[0].message.content.strip().lower()
            return cat if cat in categories else 'other'
        except Exception:
            return None
