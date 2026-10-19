"""Small local SQLite history. Only completed replies are sent as context."""
from runtime_paths import app_dir
from action_presentation import visible_text
import os
from pathlib import Path
import sqlite3
from PySide6.QtCore import QStandardPaths


class ConversationStore:
    def __init__(self, path=None):
        if path is None:
            path = app_dir('data') / 'conversations.sqlite3'
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(self.path)
        os.chmod(self.path, 0o600)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY, title TEXT NOT NULL DEFAULT 'New conversation',
            created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
          CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY, conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK(role IN ('user','assistant')), content TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('complete','pending','cancelled','error','interrupted')),
            model TEXT NOT NULL DEFAULT '', created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        ''')
        with self.db:
            self.db.execute("UPDATE messages SET status='interrupted' WHERE status='pending'")

    def conversations(self):
        return list(self.db.execute('SELECT * FROM conversations ORDER BY id DESC'))

    def new(self):
        with self.db:
            return self.db.execute('INSERT INTO conversations DEFAULT VALUES').lastrowid

    def messages(self, conversation):
        return list(self.db.execute('SELECT * FROM messages WHERE conversation_id=? ORDER BY id', (conversation,)))

    def begin(self, conversation, text, model):
        text = text.strip()
        if not text or len(text) > 16000:
            raise ValueError('Enter a message of 1–16000 characters.')
        with self.db:
            first = self.db.execute('SELECT 1 FROM messages WHERE conversation_id=? LIMIT 1', (conversation,)).fetchone() is None
            self.db.execute("INSERT INTO messages(conversation_id,role,content,status) VALUES (?,'user',?,'complete')", (conversation, text))
            if first:
                self.db.execute('UPDATE conversations SET title=? WHERE id=?', (' '.join(text.split())[:60], conversation))
            return self.db.execute("INSERT INTO messages(conversation_id,role,content,status,model) VALUES (?,'assistant','','pending',?)", (conversation, model)).lastrowid

    def finish(self, message, text, status):
        if status not in ('complete', 'cancelled', 'error'):
            raise ValueError('Invalid reply status')
        with self.db:
            self.db.execute("UPDATE messages SET content=?,status=? WHERE id=? AND status='pending'", (text, status, message))

    def context(self, conversation, budget=12000):
        result = []
        # Keep recent complete turns within a conservative character budget.
        for row in reversed(self.messages(conversation)):
            if row['status'] != 'complete':
                continue
            content = visible_text(row['content']) if row['role']=='assistant' else row['content']
            if len(content) > budget:
                if not result:
                    result.append({'role': row['role'], 'content': content[-budget:]})
                break
            result.append({'role': row['role'], 'content': content})
            budget -= len(content)
            if budget <= 0:
                break
        result.reverse()
        while result and result[0]['role'] != 'user':
            result.pop(0)
        return result

    def clear(self, conversation):
        with self.db:
            self.db.execute('DELETE FROM messages WHERE conversation_id=?', (conversation,))
            self.db.execute("UPDATE conversations SET title='New conversation' WHERE id=?", (conversation,))

    def delete(self, conversation):
        with self.db:
            self.db.execute('DELETE FROM conversations WHERE id=?', (conversation,))

    def close(self):
        self.db.close()
