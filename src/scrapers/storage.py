import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Optional, Any
from loguru import logger

class Storage:
    def __init__(self, db_path: str = "data/prompts.db"):
        self.db_path = db_path
        self._ensure_db_dir()
        self._init_db()

    def _ensure_db_dir(self):
        directory = os.path.dirname(self.db_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                prompt TEXT,
                image_url TEXT,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Add indexes for faster querying
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_source ON prompts (source)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON prompts (created_at)')
        conn.commit()
        conn.close()

    def save_prompt(self, source: str, prompt: str, image_url: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
        """
        Save a prompt to the database.

        Args:
            source: The source of the prompt (e.g., 'lexica', 'civitai', 'promptbase')
            prompt: The actual prompt text
            image_url: URL of the associated image
            metadata: Additional metadata dictionary
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            meta_json = json.dumps(metadata, ensure_ascii=False) if metadata else None

            cursor.execute('''
                INSERT INTO prompts (source, prompt, image_url, metadata)
                VALUES (?, ?, ?, ?)
            ''', (source, prompt, image_url, meta_json))

            conn.commit()
            conn.close()
            logger.debug(f"Saved prompt from {source}: {prompt[:50]}...")
        except Exception as e:
            logger.error(f"Failed to save prompt: {e}")

    def get_prompts(self, source: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Retrieve prompts from the database.

        Args:
            source: Filter by source
            limit: Max number of records to return

        Returns:
            List of dictionaries representing prompts
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            if source:
                cursor.execute('SELECT * FROM prompts WHERE source = ? ORDER BY created_at DESC LIMIT ?', (source, limit))
            else:
                cursor.execute('SELECT * FROM prompts ORDER BY created_at DESC LIMIT ?', (limit,))

            rows = cursor.fetchall()
            results = []
            for row in rows:
                item = dict(row)
                if item['metadata']:
                    try:
                        item['metadata'] = json.loads(item['metadata'])
                    except:
                        pass
                results.append(item)

            conn.close()
            return results
        except Exception as e:
            logger.error(f"Failed to retrieve prompts: {e}")
            return []

    def close(self):
        """No-op for sqlite3 as we open/close per request for thread safety in this simple implementation"""
        pass
