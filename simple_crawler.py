# simpler_crawler.py
import asyncio
from crawl4ai import AsyncWebCrawler

async def main():
    print("Starting crawl of python.org...")
    
    async with AsyncWebCrawler() as crawler:
        try:
            result = await crawler.arun("https://www.python.org/")
            print(f"Successfully crawled python.org")
            print(f"Title: {result.metadata.get('title', 'No title')}")
            print(f"Description: {result.metadata.get('description', 'No description')}")
            print(f"Content length: {len(result.markdown) if hasattr(result, 'markdown') else 0} chars")
        except Exception as e:
            print(f"Error: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())