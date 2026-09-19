from __future__ import annotations

import io
import unittest
from pathlib import Path
from unittest.mock import patch

import requests
from PIL import Image
from pptx import Presentation

from assemble.ppt_filter import filter_adjacent_images
from assemble.server import create_app


def image_bytes(color: tuple[int, int, int]) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (320, 180), color).save(output, format="PNG")
    return output.getvalue()


class FilterAdjacentImagesTests(unittest.TestCase):
    def test_removes_only_near_identical_adjacent_images(self) -> None:
        black = image_bytes((0, 0, 0))
        white = image_bytes((255, 255, 255))

        kept, removed = filter_adjacent_images([
            (0, black),
            (1, black),
            (2, white),
            (3, white),
        ])

        self.assertEqual([index for index, _ in kept], [0, 2])
        self.assertEqual(removed, [1, 3])

    def test_does_not_compare_across_a_missing_page(self) -> None:
        black = image_bytes((0, 0, 0))

        kept, removed = filter_adjacent_images([(0, black), (2, black)])

        self.assertEqual([index for index, _ in kept], [0, 2])
        self.assertEqual(removed, [])

    def test_rejects_invalid_thresholds(self) -> None:
        with self.assertRaises(ValueError):
            filter_adjacent_images([], max_changed_ratio=1.1)


class PptDownloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.black = image_bytes((0, 0, 0))
        self.white = image_bytes((255, 255, 255))

    def _get(self, filter_similar: bool):
        images = {
            "https://resource.msa.buaa.edu.cn/0.png": self.black,
            "https://resource.msa.buaa.edu.cn/1.png": self.black,
            "https://resource.msa.buaa.edu.cn/2.png": self.white,
        }

        class FakeResponse:
            status_code = 200

            def __init__(self, content: bytes) -> None:
                self.content = content
                self.headers = {"content-type": "image/png"}
                self.text = ""

        class DownloadSession:
            def __init__(self) -> None:
                self.cookies = requests.cookies.RequestsCookieJar()
                self.headers: dict[str, str] = {}

            def get(self, url: str, **_kwargs):
                return FakeResponse(images[url])

        class ClassroomClient:
            def __init__(self) -> None:
                self.session = requests.Session()
                self.proxies = None

            def get_ppt_timeline(self, _course_id: str, _sub_id: str, _guid: str):
                return [{"img_url": url} for url in images]

        fake_client = ClassroomClient()
        with (
            patch("assemble.server.load_cookies", return_value=requests.Session()),
            patch("assemble.server.is_logged_in", return_value=True),
            patch("assemble.server.ClassroomClient.from_cookies", return_value=fake_client),
            patch("requests.Session", DownloadSession),
        ):
            app = create_app(Path("unused-cookies.json"))
            app.testing = True
            return app.test_client().get(
                "/api/courses/ppt/download",
                query_string={
                    "course_id": "course",
                    "sub_id": "sub",
                    "resource_guid": "guid",
                    "filter_similar": "1" if filter_similar else "0",
                },
            )

    def test_download_filters_similar_pages_and_reports_counts(self) -> None:
        response = self._get(filter_similar=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-PPT-Original-Slides"], "3")
        self.assertEqual(response.headers["X-PPT-Slides"], "2")
        self.assertEqual(response.headers["X-PPT-Removed-Slides"], "1")
        self.assertIn("ppt_course_sub_filtered.pptx", response.headers["Content-Disposition"])
        self.assertEqual(len(Presentation(io.BytesIO(response.data)).slides), 2)

    def test_download_can_keep_all_pages(self) -> None:
        response = self._get(filter_similar=False)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-PPT-Slides"], "3")
        self.assertEqual(response.headers["X-PPT-Removed-Slides"], "0")
        self.assertIn("ppt_course_sub.pptx", response.headers["Content-Disposition"])
        self.assertEqual(len(Presentation(io.BytesIO(response.data)).slides), 3)


if __name__ == "__main__":
    unittest.main()
