#!/usr/bin/env python3
"""
Database module for YouTube to HTML Summary application.
Handles SQLite operations for task storage and management.
"""

import sqlite3
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from contextlib import contextmanager
import os

class DatabaseManager:
    def __init__(self, db_path: str = "youtube_summary.db"):
        self.db_path = db_path
        self.init_database()
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable dict-like access
        try:
            yield conn
        finally:
            conn.close()
    
    def init_database(self):
        """Initialize the database with required tables."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Create tasks table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    video_id TEXT NOT NULL,
                    video_url TEXT NOT NULL,
                    video_title TEXT,
                    status TEXT NOT NULL,
                    progress TEXT,  -- JSON string
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    processing_time REAL,  -- in seconds
                    file_size REAL,  -- in MB
                    segments_count INTEGER DEFAULT 0,
                    transcription_length INTEGER DEFAULT 0  -- in characters
                )
            """)
            
            # Create task_events table for detailed logging
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES tasks (task_id)
                )
            """)
            
            # Create indexes for better performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_events_task_id ON task_events(task_id)")
            
            conn.commit()
    
    def create_task(self, task_id: str, video_id: str, video_url: str, video_title: str = None) -> bool:
        """Create a new task in the database."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                
                cursor.execute("""
                    INSERT INTO tasks (
                        task_id, video_id, video_url, video_title, status, 
                        progress, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    task_id, video_id, video_url, video_title, "queued",
                    json.dumps({}), now, now
                ))
                
                # Add initial event
                cursor.execute("""
                    INSERT INTO task_events (task_id, event_type, message, timestamp)
                    VALUES (?, ?, ?, ?)
                """, (task_id, "created", "Task created", now))
                
                conn.commit()
                return True
        except Exception as e:
            print(f"Error creating task: {e}")
            return False
    
    def update_task_status(self, task_id: str, status: str, progress: Dict = None, 
                          error_message: str = None, video_title: str = None) -> bool:
        """Update task status and progress."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                
                # Update task
                update_fields = ["status = ?", "updated_at = ?"]
                params = [status, now]
                
                if progress is not None:
                    update_fields.append("progress = ?")
                    params.append(json.dumps(progress))
                
                if error_message is not None:
                    update_fields.append("error_message = ?")
                    params.append(error_message)
                
                if video_title is not None:
                    update_fields.append("video_title = ?")
                    params.append(video_title)
                
                if status == "completed":
                    update_fields.append("completed_at = ?")
                    params.append(now)
                
                params.append(task_id)
                
                cursor.execute(f"""
                    UPDATE tasks SET {', '.join(update_fields)}
                    WHERE task_id = ?
                """, params)
                
                # Add event
                event_message = f"Status changed to {status}"
                if error_message:
                    event_message += f": {error_message}"
                
                cursor.execute("""
                    INSERT INTO task_events (task_id, event_type, message, timestamp)
                    VALUES (?, ?, ?, ?)
                """, (task_id, "status_change", event_message, now))
                
                conn.commit()
                return True
        except Exception as e:
            print(f"Error updating task status: {e}")
            return False
    
    def get_task(self, task_id: str) -> Optional[Dict]:
        """Get a single task by ID."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
                row = cursor.fetchone()
                
                if row:
                    task = dict(row)
                    task['progress'] = json.loads(task['progress']) if task['progress'] else {}
                    return task
                return None
        except Exception as e:
            print(f"Error getting task: {e}")
            return None
    
    def get_tasks(self, status: str = None, limit: int = 50, offset: int = 0) -> List[Dict]:
        """Get tasks with optional filtering."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                query = "SELECT * FROM tasks"
                params = []
                
                if status:
                    query += " WHERE status = ?"
                    params.append(status)
                
                query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
                params.extend([limit, offset])
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                tasks = []
                for row in rows:
                    task = dict(row)
                    task['progress'] = json.loads(task['progress']) if task['progress'] else {}
                    tasks.append(task)
                
                return tasks
        except Exception as e:
            print(f"Error getting tasks: {e}")
            return []
    
    def get_task_stats(self) -> Dict[str, Any]:
        """Get statistics about tasks."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Count by status
                cursor.execute("""
                    SELECT status, COUNT(*) as count 
                    FROM tasks 
                    GROUP BY status
                """)
                status_counts = dict(cursor.fetchall())
                
                # Total tasks
                cursor.execute("SELECT COUNT(*) FROM tasks")
                total_tasks = cursor.fetchone()[0]
                
                # Average processing time for completed tasks
                cursor.execute("""
                    SELECT AVG(processing_time) 
                    FROM tasks 
                    WHERE status = 'completed' AND processing_time IS NOT NULL
                """)
                avg_processing_time = cursor.fetchone()[0] or 0
                
                # Recent activity (last 24 hours)
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM tasks 
                    WHERE created_at >= datetime('now', '-1 day')
                """)
                recent_tasks = cursor.fetchone()[0]
                
                return {
                    "total_tasks": total_tasks,
                    "status_counts": status_counts,
                    "avg_processing_time": round(avg_processing_time, 2),
                    "recent_tasks": recent_tasks
                }
        except Exception as e:
            print(f"Error getting task stats: {e}")
            return {}
    
    def delete_task(self, task_id: str) -> bool:
        """Delete a task and its events."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Delete events first (foreign key constraint)
                cursor.execute("DELETE FROM task_events WHERE task_id = ?", (task_id,))
                
                # Delete task
                cursor.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
                
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            print(f"Error deleting task: {e}")
            return False
    
    def get_task_events(self, task_id: str, limit: int = 20) -> List[Dict]:
        """Get events for a specific task."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM task_events 
                    WHERE task_id = ? 
                    ORDER BY timestamp DESC 
                    LIMIT ?
                """, (task_id, limit))
                
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            print(f"Error getting task events: {e}")
            return []
    
    def update_task_metadata(self, task_id: str, **kwargs) -> bool:
        """Update task metadata like file size, processing time, etc."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Build dynamic update query
                valid_fields = {
                    'processing_time', 'file_size', 'segments_count', 
                    'transcription_length', 'video_title'
                }
                
                update_fields = []
                params = []
                
                for key, value in kwargs.items():
                    if key in valid_fields:
                        update_fields.append(f"{key} = ?")
                        params.append(value)
                
                if not update_fields:
                    return False
                
                params.append(task_id)
                
                cursor.execute(f"""
                    UPDATE tasks SET {', '.join(update_fields)}
                    WHERE task_id = ?
                """, params)
                
                conn.commit()
                return True
        except Exception as e:
            print(f"Error updating task metadata: {e}")
            return False
    
    def cleanup_old_tasks(self, days: int = 30) -> int:
        """Clean up old completed/failed tasks."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Delete old events first
                cursor.execute("""
                    DELETE FROM task_events 
                    WHERE task_id IN (
                        SELECT task_id FROM tasks 
                        WHERE created_at < datetime('now', '-{} days')
                        AND status IN ('completed', 'failed')
                    )
                """.format(days))
                
                # Delete old tasks
                cursor.execute("""
                    DELETE FROM tasks 
                    WHERE created_at < datetime('now', '-{} days')
                    AND status IN ('completed', 'failed')
                """.format(days))
                
                deleted_count = cursor.rowcount
                conn.commit()
                return deleted_count
        except Exception as e:
            print(f"Error cleaning up old tasks: {e}")
            return 0

# Global database instance
db = DatabaseManager() 