import httpx
import re
from typing import List, Optional
from datetime import datetime
from bs4 import BeautifulSoup

from .models import TrendingItem
from .config import Config


class TrendingFetcher:
    """热点获取器 - 支持多个数据源"""

    def __init__(self):
        config = Config()
        self.news_api_key = config.NEWS_API_KEY
        self.proxy = config.HTTP_PROXY or None

    async def fetch(self, category: str = "general") -> List[TrendingItem]:
        """
        获取热点新闻

        优先级：
        1. 如果配置了 NEWS_API_KEY，使用 NewsAPI
        2. 否则使用微博热搜（国内）
        3. 或百度热搜
        """
        if self.news_api_key:
            return await self._fetch_newsapi(category)
        else:
            # 默认使用微博热搜
            return await self._fetch_weibo()

    async def _fetch_newsapi(self, category: str) -> List[TrendingItem]:
        """使用 NewsAPI 获取热点"""
        category_map = {
            "general": "general",
            "tech": "technology",
            "entertainment": "entertainment",
            "sports": "sports",
            "business": "business",
            "science": "science",
            "health": "health"
        }

        cat = category_map.get(category, "general")

        url = "https://newsapi.org/v2/top-headlines"
        params = {
            "category": cat,
            "language": "zh",
            "pageSize": 10,
            "apiKey": self.news_api_key
        }

        async with httpx.AsyncClient(proxies=self.proxy, timeout=30) as client:
            response = await client.get(url, params=params)
            data = response.json()

        if data.get("status") != "ok":
            print(f"NewsAPI 错误: {data.get('message')}")
            return []

        items = []
        for i, article in enumerate(data.get("articles", [])):
            items.append(TrendingItem(
                id=f"news_{i}_{datetime.now().strftime('%Y%m%d')}",
                title=article.get("title", ""),
                description=article.get("description", ""),
                url=article.get("url"),
                category=category,
                hot_score=None
            ))

        return items

    async def _fetch_weibo(self) -> List[TrendingItem]:
        """获取微博热搜"""
        url = "https://weibo.com/ajax/side/hotSearch"

        async with httpx.AsyncClient(proxies=self.proxy, timeout=30) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0"
            }
            response = await client.get(url, headers=headers)
            data = response.json()

        items = []
        realtime = data.get("data", {}).get("realtime", [])

        for i, item in enumerate(realtime[:15]):  # 取前15条
            items.append(TrendingItem(
                id=f"weibo_{item.get('word_scheme', f'{i}')}",
                title=item.get("word", ""),
                description=item.get("note", ""),
                category="general",
                hot_score=item.get("raw_hot")
            ))

        return items

    async def _fetch_baidu(self) -> List[TrendingItem]:
        """获取百度热搜"""
        url = "https://top.baidu.com/board?tab=realtime"

        async with httpx.AsyncClient(proxies=self.proxy, timeout=30) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0"
            }
            response = await client.get(url, headers=headers)
            html = response.text

        soup = BeautifulSoup(html, 'html.parser')
        items = []

        # 解析百度热搜卡片
        cards = soup.find_all('div', class_='category-wrap_iQLoo')

        for i, card in enumerate(cards[:15]):
            title_elem = card.find('div', class_='c-single-text-ellipsis')
            desc_elem = card.find('div', class_='content_1YWBm')
            hot_elem = card.find('div', class_='hot-index_1Bl1a')

            if title_elem:
                title = title_elem.get_text(strip=True)
                desc = desc_elem.get_text(strip=True) if desc_elem else ""
                hot_score = None

                if hot_elem:
                    hot_text = hot_elem.get_text(strip=True)
                    match = re.search(r'[\d,]+', hot_text)
                    if match:
                        hot_score = float(match.group().replace(',', ''))

                items.append(TrendingItem(
                    id=f"baidu_{i}_{datetime.now().strftime('%Y%m%d')}",
                    title=title,
                    description=desc,
                    category="general",
                    hot_score=hot_score
                ))

        return items

    async def _fetch_zhihu(self) -> List[TrendingItem]:
        """获取知乎热榜"""
        url = "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total"

        async with httpx.AsyncClient(proxies=self.proxy, timeout=30) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0",
                "Referer": "https://www.zhihu.com/"
            }
            response = await client.get(url, headers=headers)
            data = response.json()

        items = []
        for i, item in enumerate(data.get("data", [])[:15]):
            target = item.get("target", {})
            items.append(TrendingItem(
                id=f"zhihu_{target.get('id', i)}",
                title=target.get("title", ""),
                description=target.get("excerpt", ""),
                url=target.get("url"),
                category="general",
                hot_score=item.get("detail_text", "").replace(" 万热度", "")
            ))

        return items
