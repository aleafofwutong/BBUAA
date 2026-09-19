from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import requests

from assemble.server import (
    _course_in_term,
    _current_term_id,
    _same_favorite_course,
    create_app,
)


class CurrentTermTests(unittest.TestCase):
    def test_prefers_api_current_flag(self) -> None:
        terms = [
            {"id": 1, "term_name": "2026-2027学年第一学期"},
            {"id": 2, "term_name": "other", "is_current": True},
        ]
        self.assertEqual(_current_term_id(terms, date(2026, 9, 19)), "2")

    def test_infers_autumn_and_spring_terms_from_name(self) -> None:
        terms = [
            {"id": "spring", "term_name": "2026-2027学年第二学期"},
            {"id": "autumn", "term_name": "2026-2027学年第一学期"},
        ]
        self.assertEqual(_current_term_id(terms, date(2026, 9, 19)), "autumn")
        self.assertEqual(_current_term_id(terms, date(2027, 3, 1)), "spring")

    def test_falls_back_to_first_term(self) -> None:
        self.assertEqual(_current_term_id([{"id": 7, "term_name": "unknown"}]), "7")


class FavoriteMatchTests(unittest.TestCase):
    def test_matches_by_id_code_or_exact_title_and_lecturer(self) -> None:
        favorite = {
            "course_id": "10",
            "course_code": "PHYS-1",
            "title": "基础物理学",
            "lecturer_name": "乐老师",
        }
        self.assertTrue(_same_favorite_course({"course_id": 10}, favorite))
        self.assertTrue(_same_favorite_course({"course_code": "phys-1"}, favorite))
        self.assertTrue(_same_favorite_course(
            {"title": "基础物理学", "lecturer_name": "乐老师"}, favorite
        ))
        self.assertFalse(_same_favorite_course(
            {"title": "基础物理学", "lecturer_name": "其他老师"}, favorite
        ))

    def test_filters_sessions_by_term_dates(self) -> None:
        term = {"begin_date": "2026-09-07", "end_date": "2027-01-17"}
        self.assertTrue(_course_in_term({"course_time": "2026-09-19 08:00"}, term))
        self.assertFalse(_course_in_term({"course_time": "2026-01-19 08:00"}, term))


class FavoriteSearchApiTests(unittest.TestCase):
    def setUp(self) -> None:
        class FakeClient:
            user_name = "tester"
            tenant_id = 21
            proxies = None

            def __init__(self) -> None:
                self.session = requests.Session()
                self.filters = []

            def list_terms(self):
                return [{
                    "id": "term-current",
                    "term_name": "current",
                    "is_current": 1,
                    "begin_date": "2026-09-07",
                    "end_date": "2027-01-17",
                }]

            def list_course_sessions(self, course_id):
                self.filters.append(course_id)
                return [
                    {
                        "course_id": "course-1",
                        "sub_id": "replay-1",
                        "course_code": "CODE-1",
                        "title": "线性代数",
                        "lecturer_name": "张老师",
                        "status_label": "回放",
                        "course_time": "2026-09-18 08:00",
                    },
                    {
                        "course_id": "course-1",
                        "sub_id": "live-1",
                        "course_code": "CODE-1",
                        "title": "线性代数",
                        "lecturer_name": "张老师",
                        "status_label": "直播中",
                        "course_time": "2026-09-19 08:00",
                    },
                    {
                        "course_id": "other",
                        "sub_id": "replay-2",
                        "course_code": "OTHER",
                        "title": "其他课程",
                        "lecturer_name": "李老师",
                        "status_label": "回放",
                        "course_time": "2026-09-17 08:00",
                    },
                    {
                        "course_id": "course-1",
                        "sub_id": "old-1",
                        "course_code": "CODE-1",
                        "title": "线性代数",
                        "lecturer_name": "张老师",
                        "status_label": "回放",
                        "course_time": "2026-01-19 08:00",
                    },
                ]

        self.client = FakeClient()

    def _post(self, payload):
        with (
            patch("assemble.server.load_cookies", return_value=requests.Session()),
            patch("assemble.server.is_logged_in", return_value=True),
            patch("assemble.server.ClassroomClient.from_cookies", return_value=self.client),
        ):
            app = create_app(Path("unused-cookies.json"))
            app.testing = True
            return app.test_client().post(
                "/api/courses/favorites/search", json=payload
            )

    def test_returns_current_term_matches_in_all_statuses(self) -> None:
        response = self._post(
            {
                "favorites": [
                    {
                        "course_id": "course-1",
                        "course_code": "CODE-1",
                        "title": "线性代数",
                        "lecturer_name": "张老师",
                    },
                    {
                        "course_id": "duplicate",
                        "course_code": "CODE-1",
                        "title": "同一课程的重复收藏",
                    },
                ]
            }
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["term"], "term-current")
        self.assertEqual(data["total"], 2)
        self.assertEqual(
            [item["sub_id"] for item in data["list"]],
            ["live-1", "replay-1"],
        )
        self.assertEqual(self.client.filters[0], "course-1")
        self.assertEqual(len(self.client.filters), 1)

    def test_rejects_empty_favorites(self) -> None:
        response = self._post({"favorites": []})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
