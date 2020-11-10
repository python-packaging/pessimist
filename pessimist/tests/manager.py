import unittest

from pessimist.manager import Manager


class ManagerTest(unittest.TestCase):
    def test_is_pip_line(self) -> None:
        self.assertTrue(Manager._is_pip_line("-e ../"))
        self.assertTrue(Manager._is_pip_line("-r r.txt"))
        self.assertTrue(Manager._is_pip_line("../"))
        self.assertTrue(Manager._is_pip_line("git+https://example.com/"))
        self.assertFalse(Manager._is_pip_line("pessimist"))
        self.assertFalse(Manager._is_pip_line("pessimist>=1.0"))
