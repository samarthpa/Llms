import os
from openai import OpenAI
from typing import List, Dict
from urllib.parse import urlparse
import logging

logger = logging.getLogger(__name__)

class LLMService:
    def __init__(self, require_api_key: bool = False):
        """
        Initialize LLM Service
        
        Args:
            require_api_key: If True, raise error if OPENAI_API_KEY is missing.
                           If False, gracefully disable LLM features (default).
        """
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            if require_api_key:
                raise ValueError(
                    "OPENAI_API_KEY environment variable is required but not set. "
                    "Please set it in your .env file or environment. "
                    "Get your API key from https://platform.openai.com/api-keys"
                )
            logger.warning("OPENAI_API_KEY not found. LLM features will be disabled.")
            self.client = None
        else:
            if not api_key.startswith('sk-'):
                logger.warning("OPENAI_API_KEY format appears invalid (should start with 'sk-')")
            try:
                self.client = OpenAI(api_key=api_key)
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
                if require_api_key:
                    raise
                self.client = None
    
    def is_available(self):
        return self.client is not None
    
    def generate_page_description(self, url: str, title: str, raw_content: str, existing_description: str = None) -> str:
        """Use LLM to generate a better page description from messy content"""
        if not self.is_available():
            return existing_description
        
        try:
            content_preview = raw_content[:2000] if len(raw_content) > 2000 else raw_content
            
            prompt = f"""Analyze this webpage and generate a concise, informative description (2-3 sentences max).

URL: {url}
Title: {title}
Content preview: {content_preview}

Generate a clear description that explains what this page is about and its purpose. Focus on the main value or information provided."""

            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that creates clear, concise descriptions of web pages."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=150,
                temperature=0.7
            )
            
            description = response.choices[0].message.content.strip()
            return description
        except Exception as e:
            logger.error(f"Error generating description with LLM: {e}")
            return existing_description
    
    def generate_website_summary(self, pages: List[Dict]) -> str:
        """Use LLM to generate a comprehensive website summary"""
        if not self.is_available():
            return None
        
        try:
            homepage = next((p for p in pages if urlparse(p['url']).path in ['/', '/index']), pages[0] if pages else None)
            
            if not homepage:
                return None
            
            page_summaries = []
            for page in pages[:10]:
                page_summaries.append(f"- {page.get('title', 'Untitled')}: {page.get('description', 'No description')[:100]}")
            
            prompt = f"""Based on this website's homepage and key pages, generate a comprehensive 2-3 paragraph summary that explains:
1. What the website/company does
2. Its main purpose and value proposition
3. Who it serves (target audience)

Homepage:
Title: {homepage.get('title', 'Unknown')}
Description: {homepage.get('description', 'No description available')}

Key Pages:
{chr(10).join(page_summaries)}

Generate a professional, informative summary."""

            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that creates professional website summaries."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300,
                temperature=0.7
            )
            
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Error generating summary with LLM: {e}")
            return None
    
    def categorize_page_intelligently(self, url: str, title: str, description: str, content_preview: str) -> str:
        """Use LLM to intelligently categorize pages"""
        if not self.is_available():
            return None
        
        try:
            categories = ['home', 'about', 'contact', 'services', 'products', 'blog', 'pricing', 'faq', 'careers', 'documentation', 'other']
            
            prompt = f"""Categorize this webpage into one of these categories: {', '.join(categories)}

URL: {url}
Title: {title}
Description: {description}
Content preview: {content_preview[:500]}

Return only the category name, nothing else."""

            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that categorizes web pages. Return only the category name."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=20,
                temperature=0.3
            )
            
            category = response.choices[0].message.content.strip().lower()
            if category in categories:
                return category
            return 'other'
        except Exception as e:
            logger.error(f"Error categorizing page with LLM: {e}")
            return None
    
    def improve_llms_txt_structure(self, llms_content: str, pages: List[Dict]) -> str:
        """Use LLM to improve the overall structure and organization of llms.txt"""
        if not self.is_available():
            return llms_content
        
        try:
            prompt = f"""Review and improve this llms.txt file. Ensure it:
1. Has clear, logical section organization
2. Descriptions are concise and informative
3. Important pages are prioritized
4. Follows the llms.txt specification format

Current llms.txt:
{llms_content[:3000]}

IMPORTANT: Return ONLY the improved llms.txt content. Do not include any explanatory text, comments, or summaries. The response must start with "#" (the H1 heading) and contain only the llms.txt file content."""

            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that improves llms.txt files according to the specification. Always return only the llms.txt content, no explanations."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000,
                temperature=0.5
            )
            
            improved = response.choices[0].message.content.strip()
            
            # Remove any explanatory text that might have been added
            # Look for common patterns of explanatory text at the end
            lines = improved.split('\n')
            cleaned_lines = []
            
            # Common phrases that indicate explanatory text
            explanatory_phrases = [
                "this improved version",
                "maintains the original format",
                "enhancing clarity",
                "better organization",
                "improved version",
                "note:",
                "summary:",
                "explanation:"
            ]
            
            for line in lines:
                line_lower = line.lower().strip()
                # If we hit an explanatory line, stop adding lines
                if any(phrase in line_lower for phrase in explanatory_phrases):
                    # But only if it's not part of the actual content (not in a code block or list)
                    if not line_lower.startswith('#') and not line_lower.startswith('-') and not line_lower.startswith('>'):
                        break
                cleaned_lines.append(line)
            
            cleaned = '\n'.join(cleaned_lines).strip()
            
            # Ensure it starts with H1 (valid llms.txt)
            if cleaned.startswith('#'):
                return cleaned
            else:
                # If LLM didn't return valid format, return original
                logger.warning("LLM response doesn't start with H1, using original content")
                return llms_content
            
        except Exception as e:
            logger.error(f"Error improving llms.txt with LLM: {e}")
            return llms_content

