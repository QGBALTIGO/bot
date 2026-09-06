import unittest

from level_system import build_progress_bar, format_rank_position, get_rank_tag


class LevelSystemTests(unittest.TestCase):
    def test_rank_boundaries(self):
        self.assertEqual(get_rank_tag(1), "🌱 Iniciante")
        self.assertEqual(get_rank_tag(5), "✨ Aprendiz")
        self.assertEqual(get_rank_tag(20), "🚀 Explorador")
        self.assertEqual(get_rank_tag(40), "🌟 Especialista")
        self.assertEqual(get_rank_tag(60), "🛡️ Veterano")
        self.assertEqual(get_rank_tag(80), "🔥 Mestre")
        self.assertEqual(get_rank_tag(100), "💠 Lendário")
        self.assertEqual(get_rank_tag(120), "👑 Soberano")

    def test_progress_bar_clamps_values(self):
        self.assertEqual(build_progress_bar(-10, 100, size=10), "░" * 10)
        self.assertEqual(build_progress_bar(50, 100, size=10), "█" * 5 + "░" * 5)
        self.assertEqual(build_progress_bar(150, 100, size=10), "█" * 10)

    def test_progress_bar_handles_zero_total(self):
        self.assertEqual(build_progress_bar(0, 0, size=10), "░" * 10)

    def test_rank_position(self):
        self.assertEqual(format_rank_position(1), "#1")
        self.assertEqual(format_rank_position(42), "#42")
        self.assertEqual(format_rank_position(0), "—")
        self.assertEqual(format_rank_position(-1), "—")


if __name__ == "__main__":
    unittest.main()
