"""北航 classroom SSO 登录：进入 SSO 页面、提交账号密码并获取 cookie。"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

CLASSROOM_URL = "https://classroom.msa.buaa.edu.cn/"
CASAPI_LOGIN_URL = (
    "https://yjapi.msa.buaa.edu.cn/casapi/index.php"
    "?forward=https%3A%2F%2Fclassroom.msa.buaa.edu.cn%2F"
    "&r=auth%2Flogin&tenant_code=21"
)
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_PROXY = "http://127.0.0.1:7897"
COOKIE_FILE = Path(__file__).resolve().parent / "cookies.json"

_EXECUTION_RE = re.compile(r'name="execution"\s+value="([^"]+)"')
_ERROR_RE = re.compile(r'id="errorDiv"[^>]*>.*?<p[^>]*>([^<]+)', re.DOTALL)


def _proxy_from_env() -> dict[str, str] | None:
    proxy = os.environ.get("BBUAA_PROXY", DEFAULT_PROXY).strip()
    if not proxy or proxy.lower() in ("none", "off", "0"):
        return None
    return {"http": proxy, "https": proxy}


def _browser_headers() -> dict[str, str]:
    return {
        "User-Agent": os.environ.get("BBUAA_USER_AGENT", DEFAULT_USER_AGENT),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(_browser_headers())
    return session


def resolve_sso_login_url(
    session: requests.Session | None = None,
    *,
    proxies: dict[str, str] | None = None,
) -> str:
    """从 classroom 入口经 CASAPI 重定向，解析当前 SSO 登录页 URL。"""
    session = session or create_session()
    if proxies is None:
        proxies = _proxy_from_env()

    resp = session.get(
        CASAPI_LOGIN_URL,
        proxies=proxies,
        timeout=30,
        allow_redirects=True,
    )
    resp.raise_for_status()
    if "sso.buaa.edu.cn" not in resp.url:
        raise RuntimeError(f"未跳转到 SSO 登录页，当前 URL: {resp.url}")
    return resp.url


def parse_login_form(html: str) -> dict[str, str]:
    match = _EXECUTION_RE.search(html)
    if not match:
        raise RuntimeError("SSO 登录页中未找到 execution 字段，无法提交表单")
    return {
        "type": "username_password",
        "execution": match.group(1),
        "_eventId": "submit",
        "submit": "LOGIN",
    }


def _parse_sso_error(html: str) -> str | None:
    match = _ERROR_RE.search(html)
    return match.group(1).strip() if match else None


def login(
    username: str,
    password: str,
    *,
    session: requests.Session | None = None,
    proxies: dict[str, str] | None = None,
) -> requests.Session:
    """完成 SSO 登录，返回带 classroom 相关 cookie 的 Session。"""
    if not username or not password:
        raise ValueError("username 与 password 不能为空")

    session = session or create_session()
    if proxies is None:
        proxies = _proxy_from_env()

    login_page = session.get(
        CASAPI_LOGIN_URL,
        proxies=proxies,
        timeout=30,
        allow_redirects=True,
    )
    login_page.raise_for_status()
    if "sso.buaa.edu.cn" not in login_page.url:
        raise RuntimeError(f"未能进入 SSO 登录页: {login_page.url}")

    form = parse_login_form(login_page.text)
    payload = {
        **form,
        "username": username,
        "password": password,
    }

    post_url = login_page.url
    resp = session.post(
        post_url,
        data=payload,
        proxies=proxies,
        timeout=30,
        allow_redirects=True,
    )

    if "sso.buaa.edu.cn/login" in resp.url:
        err = _parse_sso_error(resp.text)
        raise RuntimeError(err or f"SSO 登录失败 (HTTP {resp.status_code})")

    session.get(CLASSROOM_URL, proxies=proxies, timeout=30, allow_redirects=True)

    if not is_logged_in(session):
        raise RuntimeError("登录后未检测到 classroom 认证 cookie，请检查账号密码或验证码")

    return session


def is_logged_in(session: requests.Session) -> bool:
    markers = ("JWTUser", "_token", "login_cmc_id")
    names = {c.name for c in session.cookies}
    return any(name in names for name in markers)


def cookies_as_dict(session: requests.Session) -> dict[str, str]:
    return requests.utils.dict_from_cookiejar(session.cookies)


def cookies_as_header(session: requests.Session) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookies_as_dict(session).items())


def save_cookies(session: requests.Session, path: Path | str = COOKIE_FILE) -> Path:
    path = Path(path)
    payload = {
        "cookies": cookies_as_dict(session),
        "cookie_header": cookies_as_header(session),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_cookies(
    path: Path | str = COOKIE_FILE,
    *,
    session: requests.Session | None = None,
) -> requests.Session:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"cookie 文件不存在: {path}")

    session = session or create_session()
    data = json.loads(path.read_text(encoding="utf-8"))
    for name, value in data.get("cookies", {}).items():
        session.cookies.set(name, value)
    return session


def credentials_from_env() -> tuple[str, str]:
    username = os.environ.get("BBUAA_USERNAME") or os.environ.get("BUAA_USERNAME", "")
    password = os.environ.get("BBUAA_PASSWORD") or os.environ.get("BUAA_PASSWORD", "")
    return username.strip(), password.strip()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="北航 classroom SSO 登录并导出 cookie")
    parser.add_argument("-u", "--username", help="学号/工号（也可用 BBUAA_USERNAME）")
    parser.add_argument("-p", "--password", help="密码（也可用 BBUAA_PASSWORD）")
    parser.add_argument(
        "-o",
        "--output",
        default=str(COOKIE_FILE),
        help=f"cookie 输出路径（默认 {COOKIE_FILE.name}）",
    )
    parser.add_argument(
        "--resolve-only",
        action="store_true",
        help="仅解析并打印 SSO 登录页 URL，不提交账号密码",
    )
    args = parser.parse_args()

    proxies = _proxy_from_env()
    session = create_session()

    sso_url = resolve_sso_login_url(session, proxies=proxies)
    print(f"[+] SSO 登录页: {sso_url}")

    if args.resolve_only:
        return

    username = (args.username or credentials_from_env()[0]).strip()
    password = (args.password or credentials_from_env()[1]).strip()
    if not username or not password:
        raise SystemExit(
            "请通过 -u/-p 或环境变量 BBUAA_USERNAME / BBUAA_PASSWORD 提供账号密码"
        )

    session = login(username, password, session=session, proxies=proxies)
    out = save_cookies(session, args.output)

    print(f"[+] 登录成功，已写入 cookie: {out}")
    print(f"[+] Cookie 条目数: {len(cookies_as_dict(session))}")
    print(f"[+] 关键字段: {[n for n in cookies_as_dict(session) if n in ('JWTUser', '_token', 'login_cmc_id', 'PHPSESSID')]}")


if __name__ == "__main__":
    main()
