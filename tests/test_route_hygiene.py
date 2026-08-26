import unittest

from utils.route_hygiene import dedupe_http_routes_keep_last


class _Endpoint:
    def __init__(self, name):
        self.__name__ = name


class _Route:
    def __init__(self, path, methods, name):
        self.path = path
        self.methods = set(methods) if methods is not None else None
        self.name = name
        self.endpoint = _Endpoint(name) if methods is not None else None


class _Router:
    def __init__(self, routes):
        self.routes = routes


class _App:
    def __init__(self, routes):
        self.router = _Router(routes)


class RouteHygieneTests(unittest.TestCase):
    def test_keeps_last_duplicate(self):
        old = _Route("/api/cards/reload", {"GET"}, "old_reload")
        middle = _Route("/health", {"GET"}, "health")
        new = _Route("/api/cards/reload", {"GET"}, "new_reload")
        app = _App([old, middle, new])

        removed = dedupe_http_routes_keep_last(app)

        self.assertEqual(len(removed), 1)
        self.assertIs(app.router.routes[0], middle)
        self.assertIs(app.router.routes[1], new)
        self.assertEqual(removed[0].removed_name, "old_reload")
        self.assertEqual(removed[0].kept_name, "new_reload")

    def test_same_path_different_methods_are_not_duplicates(self):
        get_route = _Route("/item", {"GET"}, "get_item")
        post_route = _Route("/item", {"POST"}, "post_item")
        app = _App([get_route, post_route])

        removed = dedupe_http_routes_keep_last(app)

        self.assertEqual(removed, [])
        self.assertEqual(app.router.routes, [get_route, post_route])

    def test_non_http_routes_are_preserved(self):
        mount = _Route("/static", None, "static")
        app = _App([mount])

        dedupe_http_routes_keep_last(app)
        self.assertEqual(app.router.routes, [mount])


if __name__ == "__main__":
    unittest.main()
