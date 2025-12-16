"""
Clash API client for node management and switching.
Used to rotate proxy nodes for YouTube downloads.
"""
import asyncio
import httpx
import logging
import random
from typing import Optional, List, Dict, Any

from app.config import settings

logger = logging.getLogger(__name__)


class ClashAPIClient:
    """
    Client for Clash RESTful API.
    Supports node listing, switching, and health checking.
    """
    
    def __init__(
        self, 
        api_url: Optional[str] = None,
        secret: Optional[str] = None
    ):
        """
        Initialize Clash API client.
        
        Args:
            api_url: Clash external-controller URL (default: http://127.0.0.1:9090)
            secret: Clash API secret (optional)
        """
        self.api_url = (api_url or settings.clash_api_url).rstrip('/')
        self.secret = secret or settings.clash_api_secret
        self.headers = {}
        
        if self.secret:
            self.headers['Authorization'] = f'Bearer {self.secret}'
    
    async def _request(
        self, 
        method: str, 
        path: str, 
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """Make HTTP request to Clash API."""
        url = f"{self.api_url}{path}"
        
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.request(
                    method, 
                    url, 
                    headers=self.headers,
                    **kwargs
                )
                
                if response.status_code == 200:
                    return response.json() if response.content else {}
                elif response.status_code == 204:
                    return {}
                else:
                    logger.warning(f"Clash API error: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Clash API request failed: {e}")
            return None
    
    async def get_proxies(self) -> Optional[Dict[str, Any]]:
        """Get all proxies information."""
        return await self._request('GET', '/proxies')
    
    async def get_proxy_names(self, filter_keywords: Optional[List[str]] = None) -> List[str]:
        """
        Get list of proxy node names.
        
        Args:
            filter_keywords: Only return nodes containing these keywords
            
        Returns:
            List of proxy names
        """
        data = await self.get_proxies()
        if not data:
            return []
        
        proxies = data.get('proxies', {})
        names = []
        
        for name, info in proxies.items():
            # Skip special groups
            if info.get('type') in ['Selector', 'URLTest', 'Fallback', 'LoadBalance', 'Direct', 'Reject']:
                continue
            
            # Filter by keywords
            if filter_keywords:
                if any(kw in name for kw in filter_keywords):
                    names.append(name)
            else:
                names.append(name)
        
        return names
    
    async def get_youtube_preferred_nodes(self) -> List[str]:
        """Get nodes preferred for YouTube download."""
        keywords = settings.youtube_preferred_nodes.split(',')
        keywords = [k.strip() for k in keywords if k.strip()]
        
        if not keywords:
            keywords = ['美国', '日本原生', '新加坡']
        
        return await self.get_proxy_names(filter_keywords=keywords)
    
    async def switch_node(self, selector: str, node_name: str) -> bool:
        """
        Switch to a specific node.
        
        Args:
            selector: Selector group name (e.g., 'SELECT', '手动选择')
            node_name: Target node name
            
        Returns:
            True if successful
        """
        result = await self._request(
            'PUT', 
            f'/proxies/{selector}',
            json={'name': node_name}
        )
        
        if result is not None:
            logger.info(f"Switched to node: {node_name}")
            return True
        return False
    
    async def switch_to_random_preferred_node(self, selector: str = 'SELECT') -> Optional[str]:
        """
        Switch to a random preferred node for YouTube.
        
        Args:
            selector: Selector group name
            
        Returns:
            Node name if successful, None otherwise
        """
        nodes = await self.get_youtube_preferred_nodes()
        
        if not nodes:
            logger.warning("No preferred nodes found for YouTube")
            return None
        
        # Randomly select a node
        node = random.choice(nodes)
        
        if await self.switch_node(selector, node):
            return node
        return None
    
    async def get_current_node(self, selector: str = 'SELECT') -> Optional[str]:
        """Get currently selected node."""
        data = await self.get_proxies()
        if not data:
            return None
        
        proxies = data.get('proxies', {})
        selector_info = proxies.get(selector, {})
        
        return selector_info.get('now')
    
    async def test_node_delay(self, node_name: str, url: str = 'http://www.gstatic.com/generate_204') -> Optional[int]:
        """
        Test delay of a specific node.
        
        Args:
            node_name: Node name to test
            url: Test URL
            
        Returns:
            Delay in ms, or None if failed
        """
        result = await self._request(
            'GET',
            f'/proxies/{node_name}/delay',
            params={'url': url, 'timeout': 5000}
        )
        
        if result:
            return result.get('delay')
        return None
    
    async def get_best_youtube_node(self) -> Optional[str]:
        """
        Find the best node for YouTube based on delay.
        
        Returns:
            Best node name or None
        """
        nodes = await self.get_youtube_preferred_nodes()
        
        if not nodes:
            return None
        
        # Test a sample of nodes (max 5 to avoid too many requests)
        sample_nodes = random.sample(nodes, min(5, len(nodes)))
        
        best_node = None
        best_delay = float('inf')
        
        for node in sample_nodes:
            delay = await self.test_node_delay(node)
            if delay and delay < best_delay:
                best_delay = delay
                best_node = node
        
        if best_node:
            logger.info(f"Best YouTube node: {best_node} ({best_delay}ms)")
        
        return best_node
    
    async def is_available(self) -> bool:
        """Check if Clash API is available."""
        try:
            result = await self._request('GET', '/version')
            return result is not None
        except Exception:
            return False


# Global client instance
_clash_client: Optional[ClashAPIClient] = None


def get_clash_client() -> ClashAPIClient:
    """Get or create global Clash API client."""
    global _clash_client
    if _clash_client is None:
        _clash_client = ClashAPIClient()
    return _clash_client


async def switch_youtube_node() -> Optional[str]:
    """
    Convenience function to switch to a good YouTube node.
    
    Returns:
        New node name or None
    """
    client = get_clash_client()
    
    if not await client.is_available():
        logger.warning("Clash API not available")
        return None
    
    return await client.switch_to_random_preferred_node()


async def get_youtube_nodes() -> List[str]:
    """Get list of nodes suitable for YouTube."""
    client = get_clash_client()
    
    if not await client.is_available():
        return []
    
    return await client.get_youtube_preferred_nodes()
