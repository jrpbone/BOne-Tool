import unittest

from tests.temp_directory import temporary_directory


class TemporaryDirectoryTest(unittest.TestCase):
    def test_fixture_is_writable_and_removed_after_error(self):
        with self.assertRaisesRegex(RuntimeError, "test failure"):
            with temporary_directory() as directory:
                path = directory / "fixture.txt"
                path.write_text("test fixture", encoding="utf-8")
                self.assertEqual(path.read_text(encoding="utf-8"), "test fixture")
                raise RuntimeError("test failure")
        self.assertFalse(directory.exists())

    def test_concurrent_directories_are_isolated(self):
        with temporary_directory() as first, temporary_directory() as second:
            self.assertNotEqual(first, second)
            (first / "fixture.txt").write_text("first", encoding="utf-8")
            self.assertFalse((second / "fixture.txt").exists())
        self.assertFalse(first.exists())
        self.assertFalse(second.exists())
