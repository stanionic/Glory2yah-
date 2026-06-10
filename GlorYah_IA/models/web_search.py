"""
Web Search Integration for MANDEMMAPBAW
Allows the AI to search the internet for current information
"""

import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

class WebSearcher:
    """Web search functionality using DuckDuckGo API (no key needed)"""
    
    def __init__(self):
        self.search_enabled = True
        self.base_url = "https://api.duckduckgo.com/"
        self.timeout = 10
        
    def search(self, query, max_results=5):
        """
        Search the web for information
        
        Args:
            query: Search query string
            max_results: Maximum number of results to return
            
        Returns:
            List of search results with title, snippet, and URL
        """
        if not self.search_enabled:
            return []
        
        try:
            logger.info(f"Web search: {query}")
            
            # Use DuckDuckGo Instant Answer API
            params = {
                'q': query,
                'format': 'json',
                'no_html': 1,
                'skip_disambig': 1
            }
            
            response = requests.get(
                self.base_url,
                params=params,
                timeout=self.timeout,
                headers={'User-Agent': 'MANDEMMAPBAW/2.0'}
            )
            
            if response.status_code == 200:
                data = response.json()
                results = self._parse_results(data, max_results)
                logger.info(f"Found {len(results)} results")
                return results
            else:
                logger.error(f"Search failed: {response.status_code}")
                return []
                
        except requests.Timeout:
            logger.error("Search timeout")
            return []
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []
    
    def _parse_results(self, data, max_results):
        """Parse DuckDuckGo API response"""
        results = []
        
        # Abstract (main answer)
        if data.get('Abstract'):
            results.append({
                'title': data.get('Heading', 'Answer'),
                'snippet': data.get('Abstract'),
                'url': data.get('AbstractURL', ''),
                'source': data.get('AbstractSource', 'DuckDuckGo')
            })
        
        # Related topics
        for topic in data.get('RelatedTopics', [])[:max_results-1]:
            if isinstance(topic, dict) and 'Text' in topic:
                results.append({
                    'title': topic.get('Text', '')[:100],
                    'snippet': topic.get('Text', ''),
                    'url': topic.get('FirstURL', ''),
                    'source': 'Related'
                })
        
        return results[:max_results]
    
    def search_and_summarize(self, query):
        """
        Search and create a summary response
        
        Returns:
            Formatted response with search results
        """
        results = self.search(query)
        
        if not results:
            return None
        
        # Create formatted response
        response = f"Men sa mwen jwenn sou '{query}':\n\n"
        
        for i, result in enumerate(results, 1):
            title = result.get('title', '')
            snippet = result.get('snippet', '')[:200]
            url = result.get('url', '')
            
            if title and snippet:
                response += f"{i}. **{title}**\n"
                response += f"   {snippet}\n"
                if url:
                    response += f"   🔗 {url}\n"
                response += "\n"
        
        response += f"_Rechèch fèt: {datetime.now().strftime('%H:%M')}_ 🔍"
        
        return response
    
    def should_search(self, prompt):
        """
        Determine if a prompt requires web search
        
        Args:
            prompt: User's message
            
        Returns:
            Boolean indicating if search is needed
        """
        prompt_lower = prompt.lower()
        
        # Keywords that indicate need for current information
        search_keywords = [
            'latest', 'recent', 'current', 'today', 'now', 'news',
            'dènye', 'kounye a', 'jodi a', 'nouvèl', 'aktyèl',
            'what is', 'who is', 'kisa', 'ki moun',
            'search', 'find', 'chèche', 'jwenn',
            'weather', 'tan', 'meteo',
            'price', 'pri', 'cost',
            'when', 'kilè', 'quand'
        ]
        
        # Questions that likely need search
        question_words = ['ki', 'kisa', 'kijan', 'kilè', 'poukisa', 'what', 'who', 'when', 'where', 'why', 'how']
        starts_with_question = any(prompt_lower.startswith(word) for word in question_words)
        
        # Check for search keywords
        has_search_keyword = any(keyword in prompt_lower for keyword in search_keywords)
        
        # Specific topics that often need current info
        current_topics = [
            'president', 'prezidan', 'government', 'gouvènman',
            'covid', 'coronavirus', 'pandemic',
            'election', 'eleksyon',
            'stock', 'market', 'mache',
            'technology', 'teknoloji'
        ]
        has_current_topic = any(topic in prompt_lower for topic in current_topics)
        
        return has_search_keyword or (starts_with_question and has_current_topic)

# Singleton instance
_web_searcher = None

def get_web_searcher():
    """Get singleton instance of web searcher"""
    global _web_searcher
    if _web_searcher is None:
        _web_searcher = WebSearcher()
    return _web_searcher
