"""北航 classroom 课程列表与搜索 API 封装。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import unquote

import requests

from assemble.sso_login import (
    COOKIE_FILE,
    _proxy_from_env,
    create_session,
    load_cookies,
)

CLASSROOM_BASE = "https://classroom.msa.buaa.edu.cn"
YJAPI_BASE = "https://yjapi.msa.buaa.edu.cn"
LIVE_COURSE_URL = (
    f"{CLASSROOM_BASE}/courseapi/v2/course-live/search-live-course-list"
)
# hover 触发的详情接口：yjapi 域名 + all=1/show_all=1 + Bearer token
LIVE_COURSE_DETAIL_URL = (
    f"{YJAPI_BASE}/courseapi/v2/course-live/search-live-course-list"
)
SEARCH_LIST_URL = f"{CLASSROOM_BASE}/pptnote/v1/searchlist"
PPT_TIMELINE_URL = f"{CLASSROOM_BASE}/pptnote/v1/schedule/search-ppt"
LIVINGROOM_URL = f"{CLASSROOM_BASE}/livingroom"

# sub_status → 真实状态标签（API 返回的 status_label 经常不准）
# 经验证：API 的"预告"=正在直播，"直播中"=回放生成中，"回放"=可观看
_STATUS_MAP: dict[int, str] = {
    1: "直播中",       # API标"预告"，实际正在直播
    2: "未开始",
    3: "回放生成中",    # API标"直播中"，实际回放未就绪
    4: "已结束",
    5: "回放生成中",
    6: "回放",         # 可观看回放
    7: "回放",
}

_JWT_RE = re.compile(r's:\d+:"(eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)"')


def _extract_jwt(session: requests.Session) -> str:
    """从 session 的 _token cookie 中提取 JWT（用于 Authorization: Bearer 头）。"""
    raw = session.cookies.get("_token", "")
    if not raw:
        for cookie in session.cookies:
            if cookie.name == "_token":
                raw = cookie.value
                break
    if not raw:
        return ""
    decoded = unquote(raw)
    m = _JWT_RE.search(decoded)
    return m.group(1) if m else ""

_RE_STREAM_URL = re.compile(
    r'(https?://[^"\'\s]+\.m3u8[^"\'\s]*)'
)
_RE_MP4_URL = re.compile(
    r'(https?://resource\.msa\.buaa\.edu\.cn[^"\'\s]+\.mp4[^"\'\s]*)'
)
_RE_JSON_CONFIG = re.compile(
    r'(?:sub_content|video_list|playback|stream_url)[^}]*'
)


@dataclass
class SearchFilters:
    title: str = ""
    realname: str = ""
    course_code: str = ""
    kkxycode: str = ""
    term: str = ""
    create_at: str = ""
    search_time: str = ""
    campus_id: str = ""
    building_id: str = ""
    room_id: str = ""
    page: int = 1
    per_page: int = 20


@dataclass
class ClassroomClient:
    session: requests.Session
    tenant_id: int = 21
    user_id: int = 0
    user_name: str = ""
    proxies: dict[str, str] | None = field(default_factory=_proxy_from_env)

    @classmethod
    def from_cookies(cls, cookie_path: str | None = None) -> ClassroomClient:
        session = load_cookies(cookie_path or COOKIE_FILE)
        user = _jwt_user(session)
        return cls(
            session=session,
            tenant_id=int(user.get("tenant_id", 21)),
            user_id=int(user.get("id", 0)),
            user_name=str(user.get("account", "")),
        )

    def _json_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json, text/plain, */*",
            "Referer": f"{CLASSROOM_BASE}/",
            "Origin": CLASSROOM_BASE,
        }

    def _get(self, url: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = self.session.get(
            url,
            params=params,
            headers=self._json_headers(),
            proxies=self.proxies,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def _post(self, url: str) -> dict[str, Any]:
        resp = self.session.post(
            url,
            headers=self._json_headers(),
            proxies=self.proxies,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def list_terms(self) -> list[dict[str, Any]]:
        data = self._get(
            f"{CLASSROOM_BASE}/courseapi/index.php/v2/schedule/search-term",
            params={"tenant": self.tenant_id},
        )
        return data.get("list", []) if data.get("code") == 0 else []

    def list_colleges(self) -> list[dict[str, Any]]:
        data = self._get(
            f"{CLASSROOM_BASE}/courseapi/index.php/v2/schedule/search-xy-list",
            params={"tenant": self.tenant_id},
        )
        return data.get("list", []) if data.get("code") == 0 else []

    def list_campuses(self) -> list[dict[str, Any]]:
        data = self._post(
            f"{CLASSROOM_BASE}/courseapi/v2/schedule/search-campus?tenant_code={self.tenant_id}"
        )
        return data.get("list", []) if data.get("code") == 0 else []

    def list_buildings(self, campus_id: str) -> list[dict[str, Any]]:
        data = self._post(
            f"{CLASSROOM_BASE}/courseapi/v2/schedule/search-building"
            f"?tenant_code={self.tenant_id}&campus_id={campus_id}"
        )
        return data.get("list", []) if data.get("code") == 0 else []

    def list_rooms(self, building_id: str) -> list[dict[str, Any]]:
        data = self._post(
            f"{CLASSROOM_BASE}/courseapi/v2/schedule/search-room"
            f"?tenant_code={self.tenant_id}&building_id={building_id}"
        )
        return data.get("list", []) if data.get("code") == 0 else []

    def search(self, filters: SearchFilters) -> dict[str, Any]:
        filters = _normalize_date_filter(filters)
        if filters.create_at or filters.search_time:
            # 合并三个 API 的结果：live + yjapi + searchlist
            live_result = self._search_via_live(filters)
            yjapi_result = self._search_via_yjapi(filters)
            searchlist_result = self._search_via_searchlist(filters)

            seen: set[str] = set()
            merged: list[dict[str, Any]] = []
            for item in live_result.get("list", []):
                key = f"{item.get('course_id','')}|{item.get('sub_id','')}"
                if key not in seen:
                    seen.add(key)
                    merged.append(item)
            for item in yjapi_result.get("list", []):
                key = f"{item.get('course_id','')}|{item.get('sub_id','')}"
                if key not in seen:
                    seen.add(key)
                    merged.append(item)
            for item in searchlist_result.get("list", []):
                key = f"{item.get('course_id','')}|{item.get('sub_id','')}"
                if key not in seen:
                    seen.add(key)
                    merged.append(item)

            return {
                "total": len(merged),
                "list": merged,
                "source": "merged",
                "msg": f"live={live_result.get('total',0)}, yjapi={yjapi_result.get('total',0)}, searchlist={searchlist_result.get('total',0)}",
            }

        if _should_use_searchlist(filters):
            return self._search_via_searchlist(filters)
        return self._search_via_live(filters)

    def _search_via_yjapi(self, filters: SearchFilters) -> dict[str, Any]:
        """通过 yjapi 域名搜索（包含 show_all/show_delete，覆盖面更广）。"""
        import sys as _sys
        time_value = filters.search_time or filters.create_at
        day = _format_live_day(time_value) if time_value else ""
        if not day:
            return {"total": 0, "list": [], "source": "yjapi"}

        jwt = _extract_jwt(self.session)
        headers = self._json_headers()
        if jwt:
            headers["Authorization"] = f"Bearer {jwt}"
        else:
            print("[YJAPI] WARNING: no JWT extracted!", file=_sys.stderr)

        courses: list[dict[str, Any]] = []
        for page in range(1, 8):
            params: dict[str, Any] = {
                "all": "1",
                "show_all": "1",
                "show_delete": "2",
                "with_sub_data": "1",
                "with_room_data": "1",
                "search_time": day,
                "per_page": 100,
                "page": page,
            }
            if filters.title:
                params["like_title"] = "1"
            try:
                resp = self.session.get(
                    LIVE_COURSE_DETAIL_URL,
                    params=params,
                    headers=headers,
                    proxies=self.proxies,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                print(f"[YJAPI] page {page} request error: {exc}", file=_sys.stderr)
                break
            if data.get("code") != 0:
                print(f"[YJAPI] page {page} code={data.get('code')} msg={data.get('msg','')}", file=_sys.stderr)
                break
            batch = _flatten_live_courses(data)
            print(f"[YJAPI] page {page}: got {len(batch)} courses", file=_sys.stderr)
            if not batch:
                break
            courses.extend(batch)

        print(f"[YJAPI] total before local filter: {len(courses)}", file=_sys.stderr)
        # yjapi 已经用 search_time 过滤日期，只做标题等文本筛选，不再重复按日期过滤
        courses = _apply_local_filters_no_date(courses, filters)
        print(f"[YJAPI] total after local filter: {len(courses)}", file=_sys.stderr)
        total = len(courses)
        start = (filters.page - 1) * filters.per_page
        courses = courses[start : start + filters.per_page]
        return {"total": total, "list": courses, "source": "yjapi"}

    def _search_via_searchlist(self, filters: SearchFilters) -> dict[str, Any]:
        filters = _normalize_date_filter(filters)
        params: dict[str, Any] = {
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "page": filters.page,
            "per_page": filters.per_page,
        }
        for key in (
            "title",
            "realname",
            "course_code",
            "kkxycode",
            "term",
            "campus_id",
            "building_id",
            "room_id",
        ):
            value = getattr(filters, key, "")
            if value:
                params[key] = value

        if filters.create_at and str(filters.create_at).isdigit():
            params["create_at"] = filters.create_at

        if params.get("kkxycode") == "":
            params.pop("kkxycode", None)

        data = self._get(SEARCH_LIST_URL, params=params)
        if data.get("code") != 0:
            return {"total": 0, "list": [], "source": "searchlist", "msg": data.get("msg", "")}

        total_block = data.get("total")
        if isinstance(total_block, dict):
            items = total_block.get("list") or []
            total = int(total_block.get("total") or 0)
        elif isinstance(total_block, (int, float, str)):
            items = data.get("list") or []
            total = int(total_block)
        else:
            items = data.get("list") or []
            total = len(items)
        return {
            "total": total,
            "list": [_normalize_search_item(item) for item in items],
            "source": "searchlist",
            "msg": data.get("msg", ""),
        }

    def _search_via_live(self, filters: SearchFilters) -> dict[str, Any]:
        time_value = filters.search_time or filters.create_at
        needs_local = _needs_local_filter(filters) or bool(time_value)
        # 带上 JWT Bearer token（官网搜索也带这个头）
        jwt = _extract_jwt(self.session)
        live_headers = self._json_headers()
        if jwt:
            live_headers["Authorization"] = f"Bearer {jwt}"
        base_params: dict[str, Any] = {
            "tenant": self.tenant_id,
            "need_time_quantum": 1,
            "unique_course": 1,
            "with_sub_duration": 1,
            "with_sub_data": 1,
            "sub_live_status": "",
            "sub_public": "",
            "course_student_type": "",
            "like_title": filters.title or "",  # 传实际标题文本，由 API 端过滤
            "has_frame": 1,
            "kkxy_code": filters.kkxycode or "",
        }
        if time_value:
            base_params["search_time"] = _format_live_day(time_value)
        for key in ("campus_id", "building_id", "room_id"):
            value = getattr(filters, key, "")
            if value:
                base_params[key] = value

        if filters.realname and not needs_local:
            base_params["lecturer_name"] = filters.realname

        if needs_local:
            courses: list[dict[str, Any]] = []
            api_total = 0
            msg = ""
            # 单日时直接按页拉取；多日/复杂条件时可以本地兜底过滤
            for page in range(1, 16):
                params = {
                    **base_params,
                    "page": page,
                    "per_page": 100,
                }
                resp = self.session.get(LIVE_COURSE_URL, params=params, headers=live_headers, proxies=self.proxies, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                msg = data.get("msg", "")
                if data.get("code") != 0:
                    break
                api_total = int(data.get("total") or api_total)
                batch = _flatten_live_courses(data)
                if not batch:
                    break
                courses.extend(batch)
                if api_total and len(courses) >= api_total:
                    break

            courses = _apply_local_filters(courses, filters)
            total = len(courses)
            start = (filters.page - 1) * filters.per_page
            courses = courses[start : start + filters.per_page]
            return {
                "total": total,
                "list": courses,
                "source": "live",
                "msg": msg,
            }

        params = {
            **base_params,
            "page": filters.page,
            "per_page": min(filters.per_page, 100),
        }
        data = self._get(LIVE_COURSE_URL, params=params)
        if data.get("code") != 0:
            return {"total": 0, "list": [], "source": "live", "msg": data.get("msg", "")}

        courses = _flatten_live_courses(data)
        total = int(data.get("total") or len(courses))
        return {
            "total": total,
            "list": courses,
            "source": "live",
            "msg": data.get("msg", ""),
        }

    # ---- 课程详情 & PPT -------------------------------------------------

    def get_course_detail(
        self, course_id: str, sub_id: str, *, search_time: str = ""
    ) -> dict[str, Any] | None:
        """获取单门课程的完整详情（含视频地址、PPT资源标识等）。

        使用鼠标悬停触发的 API（yjapi 域名 + all=1/show_all=1 + Bearer token），
        直接按 course_id + sub_id 过滤，返回最完整的数据。
        """
        # 提取 JWT 用于 Authorization 头
        jwt = _extract_jwt(self.session)

        headers = self._json_headers()
        if jwt:
            headers["Authorization"] = f"Bearer {jwt}"

        params: dict[str, Any] = {
            "all": "1",
            "course_id": str(course_id),
            "sub_id": str(sub_id),
            "with_sub_data": "1",
            "with_room_data": "1",
            "show_all": "1",
            "show_delete": "2",
        }

        try:
            resp = self.session.get(
                LIVE_COURSE_DETAIL_URL,
                params=params,
                headers=headers,
                proxies=self.proxies,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            # 降级：用原来的 classroom 域名 + 日期搜索方式
            return self._get_course_detail_fallback(course_id, sub_id, search_time)

        if data.get("code") != 0:
            return self._get_course_detail_fallback(course_id, sub_id, search_time)

        # all=1 的返回可能是两种结构之一：
        # A) 分组: {"list": [{"name": "第X节", "list": [course1,...]}, ...]}
        # B) 扁平: {"list": [course1, course2, ...]}  或 {"list": {"name": ..., "list": [...]}}
        raw_list = data.get("list") or []

        def _match(item: dict) -> bool:
            return (
                str(item.get("course_id") or item.get("id", "")) == str(course_id)
                and str(item.get("sub_id", "")) == str(sub_id)
            )

        # 分组结构
        for slot in raw_list if isinstance(raw_list, list) else [raw_list]:
            if not isinstance(slot, dict):
                continue
            # slot 可能本身就是课程条目
            if "course_id" in slot and _match(slot):
                return _parse_course_detail(slot)
            # 或者 slot 包含课程列表
            for item in slot.get("list") or []:
                if _match(item):
                    return _parse_course_detail(item)

        return self._get_course_detail_fallback(course_id, sub_id, search_time)

    def _get_course_detail_fallback(
        self, course_id: str, sub_id: str, search_time: str = ""
    ) -> dict[str, Any] | None:
        """降级方案：按日期搜索 classroom 域名，遍历找到匹配课程。"""
        if not search_time:
            import time as _time
            search_time = str(int(_time.time()))

        day = _format_live_day(search_time)
        params: dict[str, Any] = {
            "tenant": self.tenant_id,
            "need_time_quantum": 1,
            "unique_course": 0,
            "with_sub_data": 1,
            "with_sub_duration": 1,
            "has_frame": 1,
            "search_time": day,
            "per_page": 100,
        }

        for page in range(1, 16):
            params["page"] = page
            try:
                resp = self.session.get(LIVE_COURSE_URL, params=params, headers=live_headers, proxies=self.proxies, timeout=30)
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                break
            if data.get("code") != 0:
                break
            for slot in data.get("list") or []:
                for item in slot.get("list") or []:
                    cid = str(item.get("course_id") or item.get("id"))
                    sid = str(item.get("sub_id"))
                    if cid == str(course_id) and sid == str(sub_id):
                        return _parse_course_detail(item)
            if not any(s.get("list") for s in data.get("list") or []):
                break

        return None

    def get_ppt_timeline(
        self,
        course_id: str,
        sub_id: str,
        resource_guid: str,
    ) -> list[dict[str, Any]]:
        """获取课程 PPT 时间轴（每页图片 URL + 时间戳）。"""
        jwt = _extract_jwt(self.session)
        ppt_headers = self._json_headers()
        if jwt:
            ppt_headers["Authorization"] = f"Bearer {jwt}"
        all_items: list[dict[str, Any]] = []
        for page in range(1, 10):
            params = {
                "course_id": course_id,
                "sub_id": sub_id,
                "page": str(page),
                "per_page": "100",
                "resource_guid": resource_guid,
            }
            resp = self.session.get(PPT_TIMELINE_URL, params=params, headers=ppt_headers, proxies=self.proxies, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                break
            batch = data.get("list") or []
            if not batch:
                break
            for item in batch:
                time_sec = _to_int(item.get("created_sec", 0))
                img_url = ""
                try:
                    content_obj = json.loads(item.get("content", "{}"))
                    img_url = content_obj.get("pptimgurl", "")
                except (json.JSONDecodeError, TypeError):
                    pass
                if img_url:
                    all_items.append(
                        {
                            "time_sec": time_sec,
                            "img_url": img_url,
                            "created_sec": time_sec,
                        }
                    )
            if len(batch) < 100:
                break
        all_items.sort(key=lambda x: x["time_sec"])
        return all_items

    def get_livingroom_video_urls(
        self, course_id: str, sub_id: str
    ) -> dict[str, Any]:
        """从 livingroom 页面提取视频地址与 PPT 资源标识。

        北航 classroom 网页在鼠标悬停视频区域时加载播放器。
        通过抓取 livingroom 页面的 HTML 和内嵌 JS 数据，
        提取所有可用的视频 URL 和 resource_guid。
        """
        page_url = f"{LIVINGROOM_URL}?course_id={course_id}&sub_id={sub_id}"
        try:
            resp = self.session.get(
                page_url,
                headers={
                    **self._json_headers(),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
                proxies=self.proxies,
                timeout=30,
            )
            resp.raise_for_status()
            html = resp.text
        except Exception as exc:
            return {"stream_url": "", "playback_url": "", "ppt_video_url": "", "resource_guids": [], "source": "error", "error": str(exc)}

        result: dict[str, Any] = {
            "stream_url": "",
            "playback_url": "",
            "ppt_video_url": "",
            "resource_guids": [],
            "all_video_urls": [],
            "source": "livingroom",
        }

        # ---- 1. 提取所有绝对 URL（视频相关） ----
        # 匹配所有 https?:// 开头的 URL
        all_urls = re.findall(r'https?://[^\s"\'<>(){}|\\^`\[\]]+', html)
        seen_urls = set()

        for u in all_urls:
            # 清理 URL 末尾的标点
            u = re.sub(r'[.,;:!?)\]}>]+$', '', u)
            if u in seen_urls:
                continue
            seen_urls.add(u)

            # m3u8 直播/回放流
            if '.m3u8' in u and not result["stream_url"]:
                result["stream_url"] = u
                result["all_video_urls"].append({"type": "m3u8", "url": u})

            # mp4 视频
            elif '.mp4' in u and 'buaa.edu.cn' in u:
                result["all_video_urls"].append({"type": "mp4", "url": u})
                if 'ppt' in u.lower() and not result["ppt_video_url"]:
                    result["ppt_video_url"] = u
                elif not result["playback_url"]:
                    result["playback_url"] = u

            # resource_guid（32 位 hex）
            guid_match = re.search(r'resource_guid[=:]\s*"?([a-f0-9]{32})', u)
            if guid_match:
                g = guid_match.group(1)
                if g not in result["resource_guids"]:
                    result["resource_guids"].append(g)

        # ---- 2. 提取 <video> / <source> 标签 ----
        for tag_pat in [
            r'<video[^>]+src="([^"]+)"',
            r"<video[^>]+src='([^']+)'",
            r'<source[^>]+src="([^"]+)"',
            r"<source[^>]+src='([^']+)'",
        ]:
            for m in re.findall(tag_pat, html):
                if m not in seen_urls and 'buaa' in m:
                    seen_urls.add(m)
                    result["all_video_urls"].append({"type": "video_tag", "url": m})
                    if '.m3u8' in m and not result["stream_url"]:
                        result["stream_url"] = m
                    elif '.mp4' in m and not result["playback_url"]:
                        result["playback_url"] = m

        # ---- 3. 提取 JS 变量中的视频配置 ----
        # 常见模式：var xxx = "https://...mp4" 或 player({url: "..."})
        js_video_patterns = [
            r'(?:video_url|videoUrl|play_url|playUrl|stream_url|streamUrl|src|source|url)\s*[:=]\s*"([^"]*(?:m3u8|mp4)[^"]*)"',
            r"(?:video_url|videoUrl|play_url|playUrl|stream_url|streamUrl|src|source|url)\s*[:=]\s*'([^']*(?:m3u8|mp4)[^']*)'",
        ]
        for pat in js_video_patterns:
            for m in re.findall(pat, html, re.IGNORECASE):
                if 'buaa' in m and m not in seen_urls:
                    seen_urls.add(m)
                    result["all_video_urls"].append({"type": "js_var", "url": m})
                    if '.m3u8' in m and not result["stream_url"]:
                        result["stream_url"] = m
                    elif '.mp4' in m and not result["playback_url"]:
                        result["playback_url"] = m

        # ---- 4. 提取 resource_guid（页面中所有 32 位 hex） ----
        for m in re.findall(r'[^a-f0-9]([a-f0-9]{32})[^a-f0-9]', html):
            if m not in result["resource_guids"]:
                result["resource_guids"].append(m)

        # ---- 5. 尝试解析 <script> 中的 JSON 数据 ----
        script_json_patterns = [
            r'<script[^>]*type="application/json"[^>]*>(.*?)</script>',
            r'<script[^>]*>\s*(?:var|let|const)\s+\w+\s*=\s*({[^;]+});',
            r'window\.__\w+__\s*=\s*({[^;]+});',
        ]
        for pat in script_json_patterns:
            for raw_json in re.findall(pat, html, re.DOTALL):
                try:
                    obj = json.loads(raw_json)
                    _extract_from_json(obj, result)
                except (json.JSONDecodeError, TypeError):
                    # 尝试提取 JSON 片段
                    for sub_match in re.findall(r'\{[^}]+\}', raw_json):
                        try:
                            obj = json.loads(sub_match)
                            _extract_from_json(obj, result)
                        except (json.JSONDecodeError, TypeError):
                            pass

        # ---- 6. 从查询字符串中提取 resource_guid ----
        for m in re.findall(r'resource_guid=([a-f0-9]{32})', html):
            if m not in result["resource_guids"]:
                result["resource_guids"].append(m)

        return result


def _extract_from_json(obj: Any, result: dict[str, Any]) -> None:
    """递归从 JSON 对象中提取视频 URL 和 resource_guid。"""
    if isinstance(obj, dict):
        for key in ("stream_url", "m3u8_url", "playback_url", "video_url",
                     "play_url", "preview_url", "contents", "src", "url"):
            val = obj.get(key, "")
            if isinstance(val, str) and ("m3u8" in val or "mp4" in val) and "buaa" in val:
                url = val
                if url not in [u["url"] for u in result.get("all_video_urls", [])]:
                    result.setdefault("all_video_urls", []).append({"type": f"json.{key}", "url": url})
                if ".m3u8" in url and not result.get("stream_url"):
                    result["stream_url"] = url
                elif ".mp4" in url and not result.get("playback_url"):
                    result["playback_url"] = url
        for key in ("resource_guid", "guid", "sub_resource_guid"):
            val = obj.get(key, "")
            if isinstance(val, str) and len(val) == 32 and val.isalnum():
                if val not in result.setdefault("resource_guids", []):
                    result["resource_guids"].append(val)
        for v in obj.values():
            _extract_from_json(v, result)
    elif isinstance(obj, list):
        for item in obj:
            _extract_from_json(item, result)


def _parse_course_detail(item: dict[str, Any]) -> dict[str, Any]:
    """解析原始课程条目，提取视频地址、PPT资源等关键字段。"""
    # 解析 sub_content（可能是 JSON 字符串，也可能是已解析的 dict）
    sub_content_raw = item.get("sub_content", {})
    sub_content: dict[str, Any] = {}
    if isinstance(sub_content_raw, dict):
        sub_content = sub_content_raw
    elif isinstance(sub_content_raw, str) and sub_content_raw.strip():
        try:
            sub_content = json.loads(sub_content_raw)
        except (json.JSONDecodeError, TypeError):
            pass

    save_playback = sub_content.get("save_playback", {})
    playback_url = save_playback.get("contents", "")
    is_m3u8 = save_playback.get("is_m3u8", "no") == "yes"

    # 视频列表
    video_list = item.get("video_list") or []
    ppt_video = None
    teacher_video = None
    ppt_resource_guid = item.get("sub_resource_guid", "")
    for v in video_list:
        vtype = str(v.get("type", ""))
        vid = {
            "resource_guid": v.get("resource_guid", ""),
            "preview_url": v.get("preview_url", ""),
            "duration": _to_int(v.get("duration", 0)),
            "is_m3u8": v.get("is_m3u8", "no") == "yes",
            "status": str(v.get("status", "")),
        }
        if vtype == "2":  # PPT 录屏视频
            ppt_video = vid
            # PPT 视频的 resource_guid 用于 pptnote API
            if vid["resource_guid"]:
                ppt_resource_guid = vid["resource_guid"]
        elif vtype == "3":  # 教师摄像头视频
            teacher_video = vid

    # segment_video_list 中的 PPT/教师分段
    segment_list = item.get("segment_video_list") or []
    ppt_segment = None
    teacher_segment = None
    if segment_list:
        seg = segment_list[0]
        ppt_raw = seg.get("ppt_list") or {}
        teacher_raw = seg.get("teacher_list") or {}
        ppt_segment = {
            "resource_guid": ppt_raw.get("resource_guid", ""),
            "preview_url": ppt_raw.get("preview_url", ""),
            "duration": _to_int(ppt_raw.get("duration", 0)),
            "time_offset": _to_int(ppt_raw.get("time_offset", 0)),
            "thumb": ppt_raw.get("thumb", ""),
        }
        teacher_segment = {
            "resource_guid": teacher_raw.get("resource_guid", ""),
            "preview_url": teacher_raw.get("preview_url", ""),
            "duration": _to_int(teacher_raw.get("duration", 0)),
            "time_offset": _to_int(teacher_raw.get("time_offset", 0)),
            "thumb": teacher_raw.get("thumb", ""),
        }
        # 如果还没有 ppt_resource_guid，从 segment 中取
        if not ppt_resource_guid and ppt_segment["resource_guid"]:
            ppt_resource_guid = ppt_segment["resource_guid"]

    # 直播流地址：trans_socket_url 通常为空，实际在 output.m3u8 / output_student.m3u8
    trans_socket_url = sub_content.get("trans_socket_url", "")
    if not trans_socket_url:
        for section in ("output", "output_student", "tts"):
            url = (sub_content.get(section) or {}).get("m3u8", "")
            if url and "buaa" in url:
                trans_socket_url = url
                break

    # ---- 真实状态判断 ----
    sub_status_val = _to_int(item.get("sub_status", 0))
    real_status = _STATUS_MAP.get(sub_status_val, item.get("status_label", "未知"))
    live_status_val = _to_int(item.get("live_status", 0))
    is_live = str(item.get("is_live", "0")) == "1"

    # 综合判断：是否有可用视频
    has_playback = bool(playback_url or (teacher_video and teacher_video["preview_url"]))
    has_live_stream = bool(trans_socket_url)
    has_ppt_video = bool(ppt_video and ppt_video["preview_url"])
    has_any_video = has_playback or has_live_stream or has_ppt_video

    # 确定首选视频 URL
    primary_video_url = ""
    primary_is_m3u8 = False
    if has_live_stream:
        primary_video_url = trans_socket_url
        primary_is_m3u8 = True
    elif playback_url:
        primary_video_url = playback_url
        primary_is_m3u8 = is_m3u8
    elif teacher_video and teacher_video["preview_url"]:
        primary_video_url = teacher_video["preview_url"]
        primary_is_m3u8 = teacher_video["is_m3u8"]
    elif ppt_video and ppt_video["preview_url"]:
        primary_video_url = ppt_video["preview_url"]
        primary_is_m3u8 = ppt_video["is_m3u8"]

    # 兜底：递归搜索整个 item，找到实际的视频 URL（https:// 开头）
    if not primary_video_url:
        def _find_video_url(obj: Any, depth: int = 0) -> str:
            if depth > 6:
                return ""
            if isinstance(obj, str):
                # 只匹配以 https:// 开头的真实 URL，避免匹配到整个 JSON 字符串
                if obj.startswith("https://") and ".m3u8" in obj and "buaa" in obj:
                    return obj
                if obj.startswith("https://") and ".mp4" in obj and "buaa" in obj:
                    return obj
            elif isinstance(obj, dict):
                for v in obj.values():
                    found = _find_video_url(v, depth + 1)
                    if found:
                        return found
            elif isinstance(obj, list):
                for v in obj:
                    found = _find_video_url(v, depth + 1)
                    if found:
                        return found
            return ""

        primary_video_url = _find_video_url(item)
        if primary_video_url:
            primary_is_m3u8 = ".m3u8" in primary_video_url
            has_any_video = True

    # 分别判断直播和回放是否有可用视频
    live_url = trans_socket_url
    # 回放地址：优先 save_playback.contents，其次 teacher_video，最后 ppt_video
    replay_url = playback_url
    replay_is_m3u8 = is_m3u8
    if not replay_url and teacher_video:
        replay_url = teacher_video["preview_url"]
        replay_is_m3u8 = teacher_video["is_m3u8"]
    if not replay_url and ppt_video:
        replay_url = ppt_video["preview_url"]
        replay_is_m3u8 = ppt_video["is_m3u8"]

    has_live = bool(live_url)
    has_replay = bool(replay_url)

    return {
        "course_id": str(item.get("course_id") or item.get("id", "")),
        "sub_id": str(item.get("sub_id", "")),
        "title": item.get("title", ""),
        "course_code": item.get("course_code", ""),
        "lecturer_name": item.get("lecturer_name") or item.get("realname", ""),
        "room_name": item.get("room_name", ""),
        "sub_title": item.get("sub_title", ""),
        # 状态
        "status_label": real_status,
        "sub_status": sub_status_val,
        "live_status": live_status_val,
        "is_live": is_live,
        "has_video": has_any_video,
        # 时间
        "course_begin": _to_int(item.get("course_begin", 0)),
        "course_over": _to_int(item.get("course_over", 0)),
        # 资源标识
        "sub_resource_guid": item.get("sub_resource_guid", ""),
        "ppt_resource_guid": ppt_resource_guid,
        # 视频（兼容旧字段）
        "primary_video_url": primary_video_url,
        "is_m3u8": primary_is_m3u8,
        "playback_url": playback_url,
        "trans_socket_url": trans_socket_url,
        "ppt_video": ppt_video,
        "teacher_video": teacher_video,
        "ppt_segment": ppt_segment,
        "teacher_segment": teacher_segment,
        # ---- 新增：直播/回放 分开的数据源 ----
        "sources": {
            "live": {
                "available": has_live,
                "url": live_url,
                "is_m3u8": True,  # 直播都是 m3u8
                "label": "🔴 直播",
            },
            "replay": {
                "available": has_replay,
                "url": replay_url,
                "is_m3u8": replay_is_m3u8,
                "label": "📼 回放",
            },
        },
    }


def _jwt_user(session: requests.Session) -> dict[str, Any]:
    raw = session.cookies.get("JWTUser") or ""
    if not raw:
        for cookie in session.cookies:
            if cookie.name == "JWTUser":
                raw = cookie.value
                break
    if not raw:
        return {}
    try:
        return json.loads(unquote(raw))
    except json.JSONDecodeError:
        return {}


def _should_use_searchlist(filters: SearchFilters) -> bool:
    return bool(
        filters.title
        or filters.course_code
        or filters.kkxycode
        or filters.term
        or (filters.realname and not _has_location(filters))
    )


def _normalize_date_filter(filters: SearchFilters) -> SearchFilters:
    value = filters.create_at or filters.search_time
    if not value:
        return filters
    day = _parse_day_range(value)
    if not day:
        return filters
    start, _end = day
    return SearchFilters(
        title=filters.title,
        realname=filters.realname,
        course_code=filters.course_code,
        kkxycode=filters.kkxycode,
        term=filters.term,
        create_at=str(start),
        search_time=str(start),
        campus_id=filters.campus_id,
        building_id=filters.building_id,
        room_id=filters.room_id,
        page=filters.page,
        per_page=filters.per_page,
    )


def _parse_day_range(value: str) -> tuple[int, int] | None:
    text = value.strip()
    if not text:
        return None

    if text.isdigit():
        start = int(text)
        if start > 1_000_000_000_000:
            start //= 1000
        start_dt = datetime.fromtimestamp(start)
        start = int(start_dt.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
        end = int((start_dt.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).timestamp())
        return start, end

    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            start_dt = datetime.strptime(text[:10], fmt)
            start = int(start_dt.timestamp())
            end = int((start_dt + timedelta(days=1)).timestamp())
            return start, end
        except ValueError:
            continue
    return None


def _has_location(filters: SearchFilters) -> bool:
    return bool(filters.campus_id or filters.building_id or filters.room_id)


def _has_text_search(filters: SearchFilters) -> bool:
    return bool(
        filters.title
        or filters.realname
        or filters.course_code
        or filters.kkxycode
        or filters.term
    )


def _flatten_live_courses(data: dict[str, Any]) -> list[dict[str, Any]]:
    courses: list[dict[str, Any]] = []
    for slot in data.get("list") or []:
        if not isinstance(slot, dict):
            continue
        # 扁平结构：slot 本身就是课程（有 course_id/sub_id，不是时间段的 id）
        if "course_id" in slot or "sub_id" in slot:
            courses.append(_normalize_live_item(slot, "", ""))
            continue
        # 分组结构：slot 包含 name + list
        slot_label = slot.get("name") or ""
        slot_time = f"{slot.get('class_begin_time', '')}-{slot.get('class_end_time', '')}"
        for item in slot.get("list") or []:
            courses.append(_normalize_live_item(item, slot_label, slot_time))
    return courses


def _normalize_live_item(
    item: dict[str, Any], slot_label: str, slot_time: str
) -> dict[str, Any]:
    begin = item.get("course_begin")
    begin_ts = _to_int(begin)
    # 用 sub_status 修正 status_label（API 返回的经常不准）
    sub_status_val = _to_int(item.get("sub_status", 0))
    live_status_val = _to_int(item.get("live_status", 0))
    api_label = item.get("status_label", "")  # API 原始状态文字
    real_status = _STATUS_MAP.get(sub_status_val, api_label or "未知")

    return {
        "course_id": item.get("course_id") or item.get("id"),
        "sub_id": item.get("sub_id"),
        "title": item.get("title", ""),
        "course_code": item.get("course_code", ""),
        "kkxy_name": item.get("kkxy_name", ""),
        "lecturer_name": item.get("lecturer_name") or item.get("realname", ""),
        "room_name": item.get("room_name", ""),
        "sub_title": item.get("sub_title", ""),
        "status_label": real_status,
        # 保留原始字段方便排查
        "_raw_status": f"{api_label} (sub={sub_status_val}, live={live_status_val})",
        "term_name": item.get("term_name", ""),
        "course_time": _format_timestamp(begin_ts),
        "course_begin_ts": begin_ts,
        "time_slot": slot_label,
        "time_range": slot_time,
        "thumb": item.get("extract_thumb") or item.get("thumb", ""),
        "source": "live",
    }


def _normalize_search_item(item: dict[str, Any]) -> dict[str, Any]:
    raw_time = item.get("create_at", "")
    course_time = _format_timestamp(raw_time) if str(raw_time).isdigit() else str(raw_time or "")
    # searchlist 接口返回的 sub_type 更准确
    sub_type = item.get("sub_type", "")
    sub_status_val = _to_int(item.get("sub_status", 0))
    real_status = _STATUS_MAP.get(sub_status_val, sub_type or "未知")
    return {
        "course_id": item.get("course_id") or item.get("c.course_id"),
        "sub_id": item.get("sub_id"),
        "title": item.get("title", ""),
        "course_code": item.get("course_code", ""),
        "kkxy_name": item.get("kkxy_name", ""),
        "lecturer_name": item.get("lecturer_name")
        or item.get("realname")
        or item.get("teacher", ""),
        "room_name": item.get("room_name", ""),
        "sub_title": item.get("subject_title", ""),
        "status_label": real_status,
        "term_name": item.get("term_name", ""),
        "course_time": course_time,
        "time_slot": "",
        "time_range": "",
        "thumb": item.get("extract_thumb") or item.get("thumb", ""),
        "source": "searchlist",
    }


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _format_timestamp(value: Any) -> str:
    ts = _to_int(value)
    if not ts:
        return ""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def _format_live_day(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""

    day = _parse_day_range(text)
    if day:
        start, _end = day
        dt = datetime.fromtimestamp(start)
        return f"{dt.year}-{dt.month}-{dt.day}"

    if text.isdigit():
        ts = int(text)
        if ts > 1_000_000_000_000:
            ts //= 1000
        dt = datetime.fromtimestamp(ts)
        return f"{dt.year}-{dt.month}-{dt.day}"

    if len(text) >= 10 and text[4:5] == "-":
        parts = text[:10].split("-")
        if len(parts) == 3 and all(part.isdigit() for part in parts):
            return f"{int(parts[0])}-{int(parts[1])}-{int(parts[2])}"

    return text


def _needs_local_filter(filters: SearchFilters) -> bool:
    return bool(
        filters.title
        or filters.course_code
        or filters.kkxycode
        or filters.term
        or filters.create_at
        or filters.search_time
        or (filters.realname and _has_location(filters))
    )


def _apply_local_filters_no_date(
    courses: list[dict[str, Any]], filters: SearchFilters
) -> list[dict[str, Any]]:
    """同 _apply_local_filters，但不按日期过滤（API 已过滤）。"""
    result = courses
    if filters.title:
        result = [c for c in result if filters.title in c.get("title", "")]
    if filters.course_code:
        result = [c for c in result if filters.course_code in c.get("course_code", "")]
    if filters.kkxycode:
        result = [c for c in result
                  if filters.kkxycode in str(c.get("kkxy_name", ""))
                  or filters.kkxycode in str(c.get("kkxy_code", ""))]
    if filters.term:
        result = [c for c in result
                  if str(filters.term) in str(c.get("term", ""))
                  or str(filters.term) in str(c.get("term_name", ""))]
    if filters.realname:
        result = [c for c in result if filters.realname in str(c.get("lecturer_name", ""))]
    return result


def _apply_local_filters(
    courses: list[dict[str, Any]], filters: SearchFilters
) -> list[dict[str, Any]]:
    filters = _normalize_date_filter(filters)
    result = courses
    if filters.title:
        result = [c for c in result if filters.title in c.get("title", "")]
    if filters.course_code:
        result = [
            c for c in result if filters.course_code in c.get("course_code", "")
        ]
    if filters.kkxycode:
        result = [
            c
            for c in result
            if filters.kkxycode in str(c.get("kkxy_name", ""))
            or filters.kkxycode in str(c.get("kkxy_code", ""))
        ]
    if filters.term:
        result = [
            c
            for c in result
            if str(filters.term) in str(c.get("term", ""))
            or str(filters.term) in str(c.get("term_name", ""))
        ]
    time_value = filters.create_at or filters.search_time
    if time_value:
        day = _parse_day_range(time_value)
        if day:
            start, end = day
            result = [
                c
                for c in result
                if start <= _to_int(c.get("course_begin_ts")) < end
                # 正在直播的课程保留，即使它的 course_begin 在当天范围外
                # （比如昨晚 23:50 开始、现在还在直播的课）
                or c.get("status_label") == "直播中"
            ]
        else:
            result = [
                c
                for c in result
                if time_value in str(c.get("course_time", ""))
            ]
    if filters.realname:
        result = [
            c
            for c in result
            if filters.realname in str(c.get("lecturer_name", ""))
        ]
    return result
