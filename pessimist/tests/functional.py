import unittest

from click.testing import CliRunner

from ..cli import main


class FunctionalTest(unittest.TestCase):
    def test_project1(self) -> None:
        # TODO unmingle stderr
        runner = CliRunner()
        result = runner.invoke(main, ["test_data/project1", "-p", "2"],)
        print(result.exit_code)
        print(result.output)
        self.assertEqual(0, result.exit_code)
        self.assertIn("Variable ['volatile (<2)', 'attrs']", result.output)
        self.assertIn("Fixed ['attrs==20.1.0', 'moreorless']", result.output)
        self.assertIn("FAIL attrs:17.4.0", result.output)
        self.assertIn("Suggest narrowing: attrs>=18.1.0", result.output)
        self.assertIn("OK   max", result.output)
        self.assertIn("OK   min", result.output)

    def test_project1_fast(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--fast", "test_data/project1"],)
        print(result.exit_code)
        print(result.output)
        self.assertEqual(1, result.exit_code)
        self.assertIn("FAIL min", result.output)
