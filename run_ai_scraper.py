import asyncio
import sys
import os

# Add root to python path to make imports work seamlessly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.ai_scraper.main import main

if __name__ == "__main__":
    asyncio.run(main())
