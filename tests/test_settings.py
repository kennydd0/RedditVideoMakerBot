import unittest
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Assuming _safe_str_to_bool is accessible for testing.
# If it's meant to be private, this import might be an issue,
# but for unit testing helpers, it's often practical.
from utils.settings import _safe_str_to_bool

class TestSafeStrToBool(unittest.TestCase):

    def test_true_strings(self):
        self.assertTrue(_safe_str_to_bool("true"))
        self.assertTrue(_safe_str_to_bool("True"))
        self.assertTrue(_safe_str_to_bool("TRUE"))
        self.assertTrue(_safe_str_to_bool("yes"))
        self.assertTrue(_safe_str_to_bool("Yes"))
        self.assertTrue(_safe_str_to_bool("1"))
        self.assertTrue(_safe_str_to_bool("on"))
        self.assertTrue(_safe_str_to_bool("On"))

    def test_false_strings(self):
        self.assertFalse(_safe_str_to_bool("false"))
        self.assertFalse(_safe_str_to_bool("False"))
        self.assertFalse(_safe_str_to_bool("FALSE"))
        self.assertFalse(_safe_str_to_bool("no"))
        self.assertFalse(_safe_str_to_bool("No"))
        self.assertFalse(_safe_str_to_bool("0"))
        self.assertFalse(_safe_str_to_bool("off"))
        self.assertFalse(_safe_str_to_bool("Off"))

    def test_boolean_input(self):
        self.assertTrue(_safe_str_to_bool(True))
        self.assertFalse(_safe_str_to_bool(False))

    def test_integer_input(self):
        # Note: The function converts input to str, so int 1 becomes "1" -> True
        self.assertTrue(_safe_str_to_bool(1))
        self.assertFalse(_safe_str_to_bool(0))
        # Other integers will raise ValueError as they don't match "true"/"false" strings
        with self.assertRaises(ValueError):
            _safe_str_to_bool(2)
        with self.assertRaises(ValueError):
            _safe_str_to_bool(-1)

    def test_invalid_strings(self):
        with self.assertRaises(ValueError):
            _safe_str_to_bool("T")
        with self.assertRaises(ValueError):
            _safe_str_to_bool("F")
        with self.assertRaises(ValueError):
            _safe_str_to_bool("Y")
        with self.assertRaises(ValueError):
            _safe_str_to_bool("N")
        with self.assertRaises(ValueError):
            _safe_str_to_bool("maybe")
        with self.assertRaises(ValueError):
            _safe_str_to_bool("") # Empty string
        with self.assertRaises(ValueError):
            _safe_str_to_bool("  true  ") # Contains spaces, current impl fails

    def test_string_with_spaces_strict(self):
        # Current implementation is strict about surrounding spaces.
        # If "  true  ".strip() was used, this would pass.
        # Testing current behavior.
        with self.assertRaises(ValueError):
            _safe_str_to_bool(" true ")
        with self.assertRaises(ValueError):
            _safe_str_to_bool("false ")


if __name__ == '__main__':
    unittest.main()
