import ast
import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace
from utils.card_image_review_rules import matches_danbooru_identity


def load_function(name, **env):
    tree = ast.parse(Path('utils/card_image_review.py').read_text())
    node = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<review>', 'exec'), env)
    return env[name]


class IdentityTests(unittest.TestCase):
    def test_beam_requires_actual_character_and_work(self):
        good = {'tag_string_character': 'beam_(chainsaw_man)', 'tag_string_copyright': 'chainsaw_man'}
        self.assertTrue(matches_danbooru_identity(good, 'Beam', 'Chainsaw Man'))
        for post in [
            {**good, 'tag_string_character': 'sakura_haruno'},
            {**good, 'tag_string_copyright': 'naruto'},
            {**good, 'tag_string_character': ''},
            {**good, 'tag_string_character': 'beam_(chainsaw_man) makima_(chainsaw_man)'},
            {**good, 'tag_string_copyright': ''},
            {**good, 'tag_string_copyright': 'chainsaw_man naruto'},
        ]:
            self.assertFalse(matches_danbooru_identity(post, 'Beam', 'Chainsaw Man'))

    def test_family_name_order(self):
        self.assertTrue(matches_danbooru_identity(
            {'tag_string_character': 'hatake_kakashi', 'tag_string_copyright': 'naruto'},
            'Kakashi Hatake', 'Naruto'))


class QueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_queued_old_task_reads_new_selection_under_lock(self):
        lock = asyncio.Lock()
        state = {'anime': 1}
        sent = []
        async def dispatch(app, selected):
            sent.append(selected)
            return True
        fn = load_function('dispatch_next_character', asyncio=asyncio,
                           _dispatch_lock=lambda app: lock,
                           _selected_anime=lambda: state['anime'],
                           _dispatch_next_character=dispatch)
        await lock.acquire()
        pending = asyncio.create_task(fn(SimpleNamespace(bot_data={}), 1))
        await asyncio.sleep(0)
        state['anime'] = 2
        lock.release()
        await pending
        self.assertEqual(sent, [2])

    async def test_no_selection_sends_nothing(self):
        async def dispatch(*args):
            self.fail('Must not dispatch without a selection')
        fn = load_function('dispatch_next_character', asyncio=asyncio,
                           _dispatch_lock=lambda app: asyncio.Lock(),
                           _selected_anime=lambda: None, _dispatch_next_character=dispatch)
        self.assertFalse(await fn(SimpleNamespace(bot_data={}), 1))

    async def test_sql_is_scoped_to_selected_anime(self):
        class Cursor:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def execute(self, sql, params):
                self.sql, self.params = sql, params
            def fetchone(self): return None
        cursor = Cursor()
        class Connection:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def cursor(self, **kwargs): return cursor
        fn = load_function('_next_queue_row', Any=object, dict_row=None, MAX_ROUNDS=3,
                           pool=SimpleNamespace(connection=Connection))
        self.assertIsNone(fn(20))
        self.assertIn('AND q.anime_id=%s', cursor.sql)
        self.assertEqual(cursor.params, (3, 20))


if __name__ == '__main__':
    unittest.main()
