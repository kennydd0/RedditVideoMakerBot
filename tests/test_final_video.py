import unittest
import sys
from pathlib import Path

# Add project root to sys.path to allow importing project modules
# Assuming 'tests' directory is at the root of the project, or one level down.
# If tests/ is in root, then Path(__file__).parent.parent should be project root.
# If tests/ is utils/tests/, then Path(__file__).parent.parent.parent
# For now, let's assume tests/ is at the project root.
# If this script is run from the project root (e.g., python -m unittest discover),
# then imports might work without sys.path modification if modules are packaged or top-level.
# However, to be safe for direct execution of this test file or discovery from tests/ dir:
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from video_creation.final_video import name_normalize

class TestNameNormalize(unittest.TestCase):

    def test_empty_string(self):
        self.assertEqual(name_normalize(""), "")

    def test_no_special_chars(self):
        self.assertEqual(name_normalize("Simple Name 123"), "Simple Name 123")

    def test_forbidden_chars(self):
        self.assertEqual(name_normalize('Test? \\ " * : | < > Name'), "Test   Name")

    def test_slash_variants_word_or(self):
        self.assertEqual(name_normalize("cat/dog"), "cat or dog")
        self.assertEqual(name_normalize("cat / dog"), "cat or dog")
        self.assertEqual(name_normalize("cat /dog"), "cat or dog")
        self.assertEqual(name_normalize("cat/ dog"), "cat or dog")

    def test_slash_variants_numbers_of(self):
        self.assertEqual(name_normalize("1/2"), "1 of 2")
        self.assertEqual(name_normalize("1 / 2"), "1 of 2")
        self.assertEqual(name_normalize("10 / 20"), "10 of 20")

    def test_slash_variants_with_without(self):
        self.assertEqual(name_normalize("test w/ feature"), "test with feature")
        self.assertEqual(name_normalize("test W / feature"), "test with feature")
        self.assertEqual(name_normalize("test w/o feature"), "test without feature")
        self.assertEqual(name_normalize("test W / O feature"), "test without feature")
        self.assertEqual(name_normalize("test W / 0 feature"), "test without feature") # '0' for 'o'

    def test_remove_remaining_slashes(self):
        self.assertEqual(name_normalize("a/b/c"), "a or b or c") # First pass
        self.assertEqual(name_normalize("leading/trailing/"), "leading or trailing") # after or, / is removed
        # The function applies rules sequentially. "a/b/c" -> "a or b/c" -> "a or b or c"
        # "test / only / remove" -> "test or only or remove"
        # A single remaining slash after other rules: "path/to/file" -> "path or to or file"
        # If a literal single slash needs removing without 'or', 'of', 'with', 'without' interpretation:
        # e.g. "text/ single" -> "text single" (this is what it currently does due to the final re.sub(r"\/", r"", name))
        self.assertEqual(name_normalize("text/ single"), "text single")


    def test_combined_rules(self):
        self.assertEqual(name_normalize('File <1>/<2> w/ option?'), "File 1 of 2 with option")

    def test_translation_skip(self):
        # This test assumes 'post_lang' is not set in settings for name_normalize to skip translation.
        # To properly test translation, we'd need to mock settings.config or have a way to set it.
        # For now, testing the non-translation path.
        # If settings.config["reddit"]["thread"]["post_lang"] is None or empty, it should not translate.
        # This requires settings to be loaded; for a unit test, it's better if name_normalize
        # can take lang as a parameter or if settings is easily mockable.
        # For now, we assume the default state or test its behavior when lang is None.
        # To test this properly, name_normalize might need a slight refactor
        # to accept 'lang' as an argument, or we mock 'settings.config'.
        # Given current structure, we just test a name that would be unchanged if no translation.
        self.assertEqual(name_normalize("A simple name"), "A simple name")

if __name__ == '__main__':
    unittest.main()
