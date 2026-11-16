import os
import tempfile
import unittest

import store


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.dir.name, "loved.db")
        self.log = os.path.join(self.dir.name, "loved_songs.log")

    def tearDown(self):
        self.dir.cleanup()

    def test_imports_log_on_first_open(self):
        # Arrange
        with open(self.log, "w", encoding="utf-8") as f:
            f.write("Artist A - Song - One - id1\n\nArtist B - Two - id2\n")

        # Act
        conn = store.open_store(self.db, self.log)

        # Assert
        self.assertEqual(store.active_tracks(conn), [("Artist A", "Song - One", "id1"), ("Artist B", "Two", "id2")])

    def test_imports_log_only_once(self):
        # Arrange
        with open(self.log, "w", encoding="utf-8") as f:
            f.write("Artist A - One - id1\n")
        store.open_store(self.db, self.log).close()

        # Act
        conn = store.open_store(self.db, self.log)

        # Assert
        self.assertEqual(len(store.active_tracks(conn)), 1)

    def test_opens_without_log(self):
        # Act
        conn = store.open_store(self.db, self.log)

        # Assert
        self.assertEqual(store.active_tracks(conn), [])

    def test_unlove_keeps_history_row(self):
        # Arrange
        conn = store.open_store(self.db, self.log)
        store.record_love(conn, "Artist", "Title", "Title", "id1")

        # Act
        store.record_unlove(conn, ["id1"])

        # Assert
        self.assertEqual(store.active_tracks(conn), [])
        row = conn.execute("SELECT loved_at, unloved_at FROM tracks WHERE spotify_id = 'id1'").fetchone()
        self.assertIsNotNone(row[0])
        self.assertIsNotNone(row[1])

    def test_relove_after_unlove_adds_new_row(self):
        # Arrange
        conn = store.open_store(self.db, self.log)
        store.record_love(conn, "Artist", "Title", "Title", "id1")
        store.record_unlove(conn, ["id1"])

        # Act
        store.record_love(conn, "Artist", "Title", "Title", "id1")

        # Assert
        self.assertEqual(store.active_tracks(conn), [("Artist", "Title", "id1")])
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0], 2)

    def test_record_love_ignores_already_active_id(self):
        # Arrange
        conn = store.open_store(self.db, self.log)
        store.record_love(conn, "Artist", "Title", "Title", "id1")

        # Act
        store.record_love(conn, "Artist", "Title", "Title", "id1")

        # Assert
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
