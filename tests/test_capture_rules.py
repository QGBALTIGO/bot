import unittest

from capture_rules import name_matches, normalize_name, valid_activity_text


class CaptureNameTests(unittest.TestCase):
    def test_normalizes_accents_and_punctuation(self):
        self.assertEqual("satoru gojo", normalize_name(" Satoru Gójo!! "))

    def test_matches_full_and_first_name(self):
        self.assertTrue(name_matches("Victor Nikiforov", "Victor Nikiforov"))
        self.assertTrue(name_matches("Victor Nikiforov", "Victor"))
        self.assertTrue(name_matches("Victor Nikiforov", "Nikif"))

    def test_rejects_too_short_or_unrelated_guess(self):
        self.assertFalse(name_matches("Satoru Gojo", "s"))
        self.assertFalse(name_matches("Satoru Gojo", "Naruto"))


class CaptureActivityTests(unittest.TestCase):
    def test_commands_do_not_count(self):
        self.assertFalse(valid_activity_text("/capturar Gojo"))

    def test_empty_and_noise_do_not_count(self):
        self.assertFalse(valid_activity_text(""))
        self.assertFalse(valid_activity_text("!!!"))

    def test_real_text_counts(self):
        self.assertTrue(valid_activity_text("esse episódio foi muito bom"))


if __name__ == "__main__":
    unittest.main()
