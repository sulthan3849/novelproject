import json
import os
import re
import shutil
import threading
import time
from typing import Any, Dict, Optional, Union


class StateManager:
    """
    Thread-safe, crash-resilient state manager for tracking novel translation progress.
    Keys state by stable SHA-256 book content hash or normalized book title.
    Employs atomic file replacement (.tmp -> os.replace) and batch-saving dirty tracking
    to eliminate disk I/O bottlenecks across 500+ page novels.
    """

    def __init__(
        self,
        book_identifier: str,
        total_chunks: int = 0,
        state_dir: str = ".state",
        save_batch_size: int = 5,
    ):
        self._lock = threading.Lock()
        # Sanitize identifier for filesystem safety
        safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", str(book_identifier).strip())
        self.book_identifier = safe_id
        self.state_dir = os.path.abspath(state_dir)
        os.makedirs(self.state_dir, exist_ok=True)
        
        self.progress_file = os.path.join(self.state_dir, f"{self.book_identifier}_progress.json")
        
        self.save_batch_size = max(1, save_batch_size)
        self._dirty = False
        self._dirty_count = 0
        
        with self._lock:
            self.state = self.load_state()
            
            # Update total chunks if newly known and greater than stored
            if total_chunks > 0 and self.state.get("total_chunks", 0) != total_chunks:
                self.state["total_chunks"] = total_chunks
                self._dirty = True
                self._save_state_unlocked(force=True)

    def _default_state(self) -> Dict[str, Any]:
        """Returns a clean default state dictionary."""
        return {
            "book_identifier": self.book_identifier,
            "total_chunks": 0,
            "translated_items": {},  # { item_id: { chunk_index: {"translated": str, "original": str, "timestamp": float} } }
            "created_at": time.time(),
            "updated_at": time.time(),
        }

    def _backup_corrupted_file(self) -> None:
        """Backs up a corrupted state file to {progress_file}.corrupted_{timestamp}."""
        if os.path.exists(self.progress_file):
            backup_path = f"{self.progress_file}.corrupted_{int(time.time())}"
            try:
                shutil.copy2(self.progress_file, backup_path)
                os.remove(self.progress_file)
            except OSError as e:
                print(f"[StateManager] Warning: Could not back up corrupted file ({e}).")

    def load_state(self) -> Dict[str, Any]:
        """Loads state progress from the atomic JSON file if it exists, validating schema."""
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Schema Validation: Must be a dict and have translated_items as a dict
                if not isinstance(data, dict) or not isinstance(data.get("translated_items"), dict):
                    print(f"[StateManager] Warning: Invalid schema in state file {self.progress_file}. Backing up and starting fresh.")
                    self._backup_corrupted_file()
                    return self._default_state()

                return data
            except Exception as e:
                # Log corruption, back up, and fall back to fresh state
                print(f"[StateManager] Warning: Error reading state file ({e}). Backing up and starting fresh.")
                self._backup_corrupted_file()
                
        return self._default_state()

    def _save_state_unlocked(self, force: bool = False) -> None:
        """Internal atomic save executed while holding self._lock."""
        if not force and not self._dirty:
            return

        # Multi-Instance Merge: If target JSON exists on disk, read it and merge any items not present in memory
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, "r", encoding="utf-8") as f:
                    disk_data = json.load(f)
                if isinstance(disk_data, dict) and isinstance(disk_data.get("translated_items"), dict):
                    disk_items = disk_data["translated_items"]
                    for item_id, chunks in disk_items.items():
                        if isinstance(chunks, dict):
                            if item_id not in self.state["translated_items"]:
                                self.state["translated_items"][item_id] = chunks
                            else:
                                for chunk_idx, chunk_data in chunks.items():
                                    if chunk_idx not in self.state["translated_items"][item_id]:
                                        self.state["translated_items"][item_id][chunk_idx] = chunk_data
            except Exception:
                pass

        self.state["updated_at"] = time.time()
        temp_file = os.path.join(
            self.state_dir,
            f"{self.book_identifier}_{os.getpid()}_{threading.get_ident()}_{time.time_ns()}.tmp",
        )
        
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())

            # Windows File Locking Resilience: retry loop (up to 5 attempts with 20-50ms sleep)
            max_attempts = 5
            for attempt in range(max_attempts):
                try:
                    os.replace(temp_file, self.progress_file)
                    break
                except OSError:
                    if attempt < max_attempts - 1:
                        time.sleep(0.02 + 0.0075 * attempt)  # 20ms to 50ms sleep
                    else:
                        raise

            self._dirty = False
            self._dirty_count = 0
        except Exception as e:
            print(f"[StateManager] Error saving state atomically: {e}")
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except OSError:
                    pass
            raise

    def save_state(self, force: bool = False) -> None:
        """
        Atomically saves state progress using a unique temporary file and os.replace().
        Thread-safe wrapper protected by self._lock.
        """
        with self._lock:
            self._save_state_unlocked(force=force)

    def flush(self) -> None:
        """Forces an immediate atomic disk flush of all in-memory state changes."""
        with self._lock:
            self._save_state_unlocked(force=True)

    def is_chunk_translated(
        self,
        item_id: Union[str, int],
        chunk_index: Optional[Union[str, int]] = None,
    ) -> bool:
        """
        Checks whether a given chunk is already translated.
        Supports both (item_id, chunk_index) and composite chunk_id (e.g. 'item1_0').
        """
        with self._lock:
            if chunk_index is not None:
                s_item = str(item_id)
                s_idx = str(chunk_index)
                return s_idx in self.state.get("translated_items", {}).get(s_item, {})
            else:
                # Composite key check: search flat or split
                composite = str(item_id)
                if ":" in composite:
                    s_item, s_idx = composite.split(":", 1)
                    return s_idx in self.state.get("translated_items", {}).get(s_item, {})
                # Look up across any item
                for item_dict in self.state.get("translated_items", {}).values():
                    if isinstance(item_dict, dict) and composite in item_dict:
                        return True
                return False

    def get_translated_chunk(
        self,
        item_id: Union[str, int],
        chunk_index: Optional[Union[str, int]] = None,
    ) -> Optional[str]:
        """
        Retrieves translated text for a given chunk.
        Supports both (item_id, chunk_index) and composite chunk_id.
        """
        with self._lock:
            if chunk_index is not None:
                s_item = str(item_id)
                s_idx = str(chunk_index)
                record = self.state.get("translated_items", {}).get(s_item, {}).get(s_idx)
            else:
                composite = str(item_id)
                if ":" in composite:
                    s_item, s_idx = composite.split(":", 1)
                    record = self.state.get("translated_items", {}).get(s_item, {}).get(s_idx)
                else:
                    record = None
                    for item_dict in self.state.get("translated_items", {}).values():
                        if isinstance(item_dict, dict) and composite in item_dict:
                            record = item_dict[composite]
                            break

            if record is None:
                return None
            if isinstance(record, dict):
                return record.get("translated")
            return str(record)

    def get_translated_text(self, chunk_id: Union[str, int]) -> Optional[str]:
        """Contract alias for get_translated_chunk."""
        return self.get_translated_chunk(chunk_id)

    def mark_chunk_translated(
        self,
        item_id: Union[str, int],
        chunk_index: Optional[Union[str, int, str]] = None,
        translated_text: Optional[str] = None,
        original_text: Optional[str] = None,
    ) -> None:
        """
        Records a translated chunk in memory and triggers batched atomic persistence.
        Supports multiple calling conventions:
        - mark_chunk_translated(item_id, chunk_index, translated_text, original_text=None)
        - mark_chunk_translated(chunk_id, original, translated)
        """
        with self._lock:
            # Distinguish calling conventions
            if translated_text is None and original_text is not None:
                # Called as (chunk_id, original, translated) -> chunk_index is original, original_text is translated
                target_translated = original_text
                target_original = str(chunk_index)
                composite = str(item_id)
                if ":" in composite:
                    s_item, s_idx = composite.split(":", 1)
                else:
                    s_item, s_idx = "default", composite
            else:
                s_item = str(item_id)
                s_idx = str(chunk_index if chunk_index is not None else 0)
                target_translated = translated_text if translated_text is not None else ""
                target_original = original_text if original_text is not None else ""

            if "translated_items" not in self.state or not isinstance(self.state["translated_items"], dict):
                self.state["translated_items"] = {}
            if s_item not in self.state["translated_items"] or not isinstance(self.state["translated_items"][s_item], dict):
                self.state["translated_items"][s_item] = {}

            self.state["translated_items"][s_item][s_idx] = {
                "translated": target_translated,
                "original": target_original,
                "timestamp": time.time(),
            }

            self._dirty = True
            self._dirty_count += 1

            # Check if batch size threshold is reached for disk flush
            if self._dirty_count >= self.save_batch_size:
                self._save_state_unlocked(force=True)

    def get_completed_count(self) -> int:
        """Returns the total number of translated chunks across all items."""
        with self._lock:
            count = 0
            for item_dict in self.state.get("translated_items", {}).values():
                if isinstance(item_dict, dict):
                    count += len(item_dict)
            return count

    def get_progress(self) -> Dict[str, Any]:
        """
        Calculates and returns progress statistics.
        Returns {'total': int, 'completed': int, 'percent': float, 'remaining': int}
        """
        with self._lock:
            completed = 0
            for item_dict in self.state.get("translated_items", {}).values():
                if isinstance(item_dict, dict):
                    completed += len(item_dict)
            total = self.state.get("total_chunks", 0)
            
            # If total was not explicitly set, use completed count
            effective_total = max(total, completed)
            percent = (completed / effective_total * 100.0) if effective_total > 0 else 0.0
            
            return {
                "total": effective_total,
                "completed": completed,
                "percent": round(percent, 2),
                "remaining": max(0, effective_total - completed),
                "book_identifier": self.book_identifier,
            }

    def reset_state(self) -> None:
        """Clears all stored progress and removes the state file from disk."""
        with self._lock:
            self.state = {
                "book_identifier": self.book_identifier,
                "total_chunks": 0,
                "translated_items": {},
                "created_at": time.time(),
                "updated_at": time.time(),
            }
            self._dirty = False
            self._dirty_count = 0
            if os.path.exists(self.progress_file):
                try:
                    os.remove(self.progress_file)
                except OSError:
                    pass
