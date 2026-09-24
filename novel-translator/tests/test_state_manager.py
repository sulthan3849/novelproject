import json
import os
import shutil
import tempfile
import time
import unittest
from utils.state_manager import StateManager


class TestStateManager(unittest.TestCase):
    """Test suite for StateManager covering Tier 1, Tier 2, and Tier 3 requirements."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_state_")
        self.book_id = "test_book_sha256_hash_12345"
        self.manager = StateManager(
            book_identifier=self.book_id,
            total_chunks=20,
            state_dir=self.test_dir,
            save_batch_size=3,
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------
    # Tier 1: Feature Coverage
    # -------------------------------------------------------------

    def test_state_initialization_with_identifier(self):
        """Verify StateManager initializes with proper file path and default schema."""
        expected_file = os.path.join(self.test_dir, f"{self.book_id}_progress.json")
        self.assertEqual(self.manager.progress_file, expected_file)
        self.assertEqual(self.manager.book_identifier, self.book_id)
        self.assertEqual(self.manager.state["total_chunks"], 20)
        self.assertIsInstance(self.manager.state["translated_items"], dict)

    def test_mark_and_check_chunk_translated_standard_convention(self):
        """Verify marking a chunk as translated records state and returns True on check."""
        self.assertFalse(self.manager.is_chunk_translated("item_01", 0))
        self.manager.mark_chunk_translated("item_01", 0, "Terjemahan paragraf pertama.")
        self.assertTrue(self.manager.is_chunk_translated("item_01", 0))
        self.assertEqual(
            self.manager.get_translated_chunk("item_01", 0),
            "Terjemahan paragraf pertama.",
        )

    def test_mark_and_check_chunk_translated_contract_convention(self):
        """Verify PROJECT.md interface contract and composite key retrieval."""
        self.manager.mark_chunk_translated(
            item_id="item_01",
            chunk_index=5,
            translated_text="Kalimat asli diterjemahkan.",
            original_text="Original sentence",
        )
        self.assertTrue(self.manager.is_chunk_translated("item_01:5"))
        self.assertEqual(
            self.manager.get_translated_text("item_01:5"),
            "Kalimat asli diterjemahkan.",
        )

    def test_atomic_persistence_creates_valid_json(self):
        """Verify state is written atomically via temporary file replacement and leaves no stray .tmp files."""
        self.manager.mark_chunk_translated("item_01", 0, "Teks satu.")
        self.manager.flush()

        self.assertTrue(os.path.exists(self.manager.progress_file))
        # Ensure no .tmp files linger in the state directory
        tmp_files = [f for f in os.listdir(self.test_dir) if f.endswith(".tmp")]
        self.assertEqual(len(tmp_files), 0, f"Found lingering temporary files: {tmp_files}")

        # Verify persisted JSON content
        with open(self.manager.progress_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["book_identifier"], self.book_id)
        self.assertIn("item_01", data["translated_items"])
        self.assertEqual(data["translated_items"]["item_01"]["0"]["translated"], "Teks satu.")

    def test_batch_saving_debounces_disk_writes(self):
        """Verify that disk writes are debounced according to save_batch_size."""
        # Initial state file was forced on init because total_chunks > 0
        initial_mtime = os.path.getmtime(self.manager.progress_file)
        time.sleep(0.05)

        # Batch size is 3. Adding 1 chunk should NOT flush to disk immediately
        self.manager.mark_chunk_translated("item_01", 1, "Teks satu.")
        self.assertEqual(os.path.getmtime(self.manager.progress_file), initial_mtime)

        # Adding 2nd chunk should still not flush
        self.manager.mark_chunk_translated("item_01", 2, "Teks dua.")
        self.assertEqual(os.path.getmtime(self.manager.progress_file), initial_mtime)

        # Adding 3rd chunk reaches threshold (3) and must trigger flush
        self.manager.mark_chunk_translated("item_01", 3, "Teks tiga.")
        new_mtime = os.path.getmtime(self.manager.progress_file)
        self.assertGreater(new_mtime, initial_mtime)

    def test_progress_calculation(self):
        """Verify get_progress calculates total, completed, percent, and remaining accurately."""
        self.manager.mark_chunk_translated("ch1", 0, "A")
        self.manager.mark_chunk_translated("ch1", 1, "B")
        self.manager.mark_chunk_translated("ch2", 0, "C")
        self.manager.mark_chunk_translated("ch2", 1, "D")

        progress = self.manager.get_progress()
        self.assertEqual(progress["total"], 20)
        self.assertEqual(progress["completed"], 4)
        self.assertEqual(progress["percent"], 20.0)
        self.assertEqual(progress["remaining"], 16)
        self.assertEqual(progress["book_identifier"], self.book_id)

    # -------------------------------------------------------------
    # Tier 2: Boundary & Corner Cases
    # -------------------------------------------------------------

    def test_corrupted_json_recovery(self):
        """Verify StateManager recovers gracefully from corrupted or truncated state file."""
        progress_file = self.manager.progress_file
        # Deliberately corrupt the state JSON file
        with open(progress_file, "w", encoding="utf-8") as f:
            f.write("{ INVALID JSON DATA TRUNCATED !!!")

        # New manager should log warning and initialize fresh state without raising
        recovered_manager = StateManager(
            book_identifier=self.book_id,
            total_chunks=20,
            state_dir=self.test_dir,
        )
        self.assertEqual(recovered_manager.get_completed_count(), 0)
        self.assertEqual(recovered_manager.state["book_identifier"], self.book_id)

    def test_missing_state_file_initializes_empty_cleanly(self):
        """Verify initializing with non-existent state file sets up default empty structure."""
        fresh_id = "totally_fresh_book_id"
        fresh_mgr = StateManager(fresh_id, state_dir=self.test_dir)
        self.assertEqual(fresh_mgr.get_completed_count(), 0)
        self.assertFalse(fresh_mgr.is_chunk_translated("any_item", 0))
        self.assertIsNone(fresh_mgr.get_translated_chunk("any_item", 0))

    def test_filesystem_sanitization(self):
        """Verify book identifier with invalid filename characters (slashes, colons) is sanitized safely."""
        unsafe_id = 'Volume 1: "The Beginning" / Special Edition? <ver 1.0>'
        safe_mgr = StateManager(unsafe_id, state_dir=self.test_dir)
        safe_mgr.flush()
        self.assertTrue(os.path.exists(safe_mgr.progress_file))
        # Ensure no invalid Windows filename characters in basename
        base = os.path.basename(safe_mgr.progress_file)
        for char in [':', '/', '\\', '?', '*', '"', '<', '>', '|']:
            self.assertNotIn(char, base)

    def test_save_state_not_dirty_noop(self):
        """Verify calling save_state when not dirty is a no-op."""
        self.manager.save_state(force=False)
        self.assertFalse(self.manager._dirty)

    def test_flat_composite_key_lookup(self):
        """Verify flat composite key lookup across items."""
        self.manager.state["translated_items"]["generic_item"] = {"flat_01": {"translated": "Flat Text"}}
        self.assertTrue(self.manager.is_chunk_translated("flat_01"))
        self.assertEqual(self.manager.get_translated_chunk("flat_01"), "Flat Text")

    def test_reset_state_clears_file_and_memory(self):
        """Verify reset_state cleans internal memory and removes the progress file from disk."""
        self.manager.mark_chunk_translated("item_01", 0, "Teks.")
        self.manager.flush()
        self.assertTrue(os.path.exists(self.manager.progress_file))

        self.manager.reset_state()
        self.assertEqual(self.manager.get_completed_count(), 0)
        self.assertFalse(os.path.exists(self.manager.progress_file))

    # -------------------------------------------------------------
    # Tier 3: Cross-Feature Combinations
    # -------------------------------------------------------------

    def test_resume_interrupted_translation_workflow(self):
        """
        Verify that a new StateManager instance initialized with the same identifier
        reliably recovers previously saved chunks and allows uninterrupted continuation.
        """
        # Session 1: Translate chunks 0 through 4
        for i in range(5):
            self.manager.mark_chunk_translated("ch1", i, f"Terjemahan chunk {i}")
        self.manager.flush()

        # Session 2: New StateManager simulating app reload / resumption
        resumed_manager = StateManager(
            book_identifier=self.book_id,
            total_chunks=20,
            state_dir=self.test_dir,
            save_batch_size=2,
        )

        # Verify all 5 chunks are recognized as already completed
        for i in range(5):
            self.assertTrue(resumed_manager.is_chunk_translated("ch1", i))
            self.assertEqual(
                resumed_manager.get_translated_chunk("ch1", i),
                f"Terjemahan chunk {i}",
            )

        # Continue translation: Chunks 5 through 9
        for i in range(5, 10):
            resumed_manager.mark_chunk_translated("ch1", i, f"Terjemahan chunk {i}")
        resumed_manager.flush()

        # Total completed count should now be 10 out of 20 (50%)
        progress = resumed_manager.get_progress()
        self.assertEqual(progress["completed"], 10)
        self.assertEqual(progress["percent"], 50.0)
        self.assertEqual(progress["remaining"], 10)

    def test_multi_book_state_isolation(self):
        """Verify two books translated concurrently do not overwrite or pollute each other's progress."""
        mgr_a = StateManager("book_alpha", state_dir=self.test_dir)
        mgr_b = StateManager("book_beta", state_dir=self.test_dir)

        mgr_a.mark_chunk_translated("item1", 0, "Alpha Chunk")
        mgr_b.mark_chunk_translated("item1", 0, "Beta Chunk")
        mgr_a.flush()
        mgr_b.flush()

        self.assertEqual(mgr_a.get_translated_chunk("item1", 0), "Alpha Chunk")
        self.assertEqual(mgr_b.get_translated_chunk("item1", 0), "Beta Chunk")


if __name__ == "__main__":
    unittest.main()
