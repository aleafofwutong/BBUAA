# BBUAA — Break-Boundary Ur Academic Archive

> **Bedroom-BUAA**：在寝室，听你想听的课。

你是否曾经有一门梦寐以求的课程，却因为置课冲突而未能选上？  
你是否觉得在随机抽签的选课系统中，很难找到适合自己风格的老师？  
你是否觉得大学四年，应该有属于自己的课外学习机会？

BBUAA 为你提供一个在寝室就能搜索、观看直播/回放、下载 PPT 的北航 classroom 课程平台。

---

## 功能

### 课程搜索

| 功能 | 说明 |
|:---|:---|
| 多维度筛选 | 课程名、教师、编号、学院、学期、日期、校区/教学楼/教室 |
| 状态筛选 | **全部 / 🔴 直播中 / 📼 可回放 / ⏳ 回放生成中**，一键过滤 |
| 默认当天 | 登录后自动显示当天课程，无需手动选日期 |
| SSO 登录 | 模拟北航统一认证，cookie 持久化，一次登录多次使用 |
| 登出 | 右上角一键清除 cookie |

### 播放器

| 功能 | 说明 |
|:---|:---|
| 🔴📼 直播/回放切换 | 播放器顶部双按钮，可随时在直播流和回放之间切换 |
| 视频回放 | MP4 播放，支持进度条拖拽、倍速（0.5× ~ 2×）、全屏 |
| 直播流 | HLS (m3u8) 直播，通过代理解决跨域和 Origin 校验 |
| PPT 同步 | 视频播放时 PPT 幻灯片自动跟随当前时间，也可手动翻页 |
| PPT 下载 | 一键导出为 `.pptx` 文件（16:9 宽屏），可离线编辑 |

### 播放器快捷键

| 按键 | 功能 |
|:---|:---|
| `Space` | 播放 / 暂停 |
| `F` | 全屏 |
| `←` `→` | 上一页 / 下一页 PPT（同步跳转视频） |
| `Ctrl` + `←` `→` | 快退 / 快进 10 秒 |
| `↑` `↓` | 音量 ±10% |
| `M` | 静音 |

### 状态映射

北航 API 返回的状态标签与实际不符，已修正：

| API 原始标签 | 实际含义 | 播放器行为 |
|:---|:---|:---|
| "预告" | **正在直播** | 默认切到直播模式 |
| "直播中" | 回放生成中 | 直播按钮不可用，回放等待生成 |
| "回放" | 回放可观看 | 默认切到回放模式 |

---

## 快速开始

```bash
git clone https://github.com/aleafofwutong/BBUAA.git
cd BBUAA
bash setup.sh          # 一键安装依赖
bash start_bbuaa.sh     # 启动服务
```

浏览器打开 `http://127.0.0.1:8765`，输入北航学号/工号和密码登录。

### 环境要求

- Python >= 3.10
- 网络可访问 `classroom.msa.buaa.edu.cn`、`yjapi.msa.buaa.edu.cn`、`livepgc.msa.buaa.edu.cn` 等子域（可能需要代理）

### 代理配置

```bash
export BBUAA_PROXY=http://127.0.0.1:7897
bash start_bbuaa.sh
```

不需要代理：

```bash
export BBUAA_PROXY=none
```

### 可选：账号环境变量

```bash
export BBUAA_USERNAME=你的学号
export BBUAA_PASSWORD=你的密码
```

---

## 项目结构

```
BBUAA/
├── assemble/
│   ├── sso_login.py       # CAS SSO 登录，cookie 持久化
│   ├── courses.py         # 课程搜索、PPT 时间轴、视频地址解析、状态映射
│   ├── server.py          # Flask 服务：API 路由 + 视频/图片代理 + m3u8 改写
│   └── web/
│       ├── index.html     # 课程搜索页面（含状态筛选切换栏）
│       ├── player.html    # 播放器（直播/回放双模式 + PPT 同步 + 倍速 + 下载）
│       ├── app.js         # 搜索逻辑 + 筛选 + 分页
│       └── style.css      # 深色主题样式
├── docs/
│   └── stream_live.txt    # 直播流 API 抓包参考
├── start_bbuaa.sh         # 启动脚本
├── setup.sh               # 一键安装脚本
├── .gitignore
└── README.md
```

---

## 后端 API

| 路由 | 说明 |
|:---|:---|
| `GET /` | 课程搜索页面 |
| `POST /api/auth/login` | SSO 登录 |
| `GET /api/auth/logout` | 登出（删除 cookie 文件） |
| `GET /api/courses/search` | 课程搜索（支持 `status_filter=live\|playback\|generating`） |
| `GET /api/courses/detail` | 课程详情（返回 `sources.live` / `sources.replay` 分开的视频地址） |
| `GET /api/courses/ppt` | PPT 时间轴（支持多 `resource_guid` 逐个尝试） |
| `GET /api/courses/ppt/download` | PPT 导出 .pptx（PIL 校验 + 并行下载 + python-pptx 生成） |
| `GET /player/` | 播放器页面 |
| `GET /api/proxy/video` | 视频流代理（注入 Cookie + Origin 伪装 + m3u8 分片 URL 改写） |
| `GET /api/proxy/image` | 图片代理（注入 Cookie 解决跨域） |
| `POST /api/shutdown` | 关闭服务 |

---

## 技术细节

### 视频代理链路

```
浏览器 ← Flask ←(Cookie+Origin 注入)← resource.msa.buaa.edu.cn (MP4 回放)
浏览器 ← Flask ←(Origin 伪装)← livepgc/lmt.buaa.edu.cn (HLS 直播)
                                └── m3u8 分片 URL 自动改写为代理 URL
```

### 直播流获取

鼠标悬停触发 `yjapi.msa.buaa.edu.cn` API（`all=1&show_all=1` + `Bearer JWT`），从 `sub_content.output.m3u8` 提取直播 m3u8 地址。

### 状态映射修正

API 的 `status_label` 不可靠，改用 `sub_status` 数值映射：`1→直播中`、`3,5→回放生成中`、`6,7→可回放`。

---

## 技术栈

| 层 | 技术 |
|:---|:---|
| 前端 | Vanilla JS + hls.js + CSS3 |
| 后端 | Python Flask + requests + Pillow + python-pptx |
| 认证 | 北航 CAS SSO + JWT Bearer Token（从 `_token` cookie 提取） |
| 视频 | HLS (m3u8) 代理 + MP4 Range 代理 |
| 抓包 | mitmproxy |

---

## 声明

- 本项目仅供学习交流使用，**严禁用于商业和非法用途**
- 使用了部分逆向和爬虫技术，请勿滥用
- 本网站不会收集任何个人信息，但请注意保管好自己的 cookie 和密码
- 目前仅在 Chrome 浏览器测试，其他浏览器可能存在兼容性问题
- 如有疑问请在 [GitHub Issues](https://github.com/aleafofwutong/BBUAA/issues) 提交

---

*祝学业进步！*
