# BBUAA — Break-Boundary Ur Academic Archive

> **Bedroom-BUAA**：在寝室，听你想听的课。

你是否曾经有一门梦寐以求的课程，却因为置课冲突而未能选上？  
你是否觉得在随机抽签的选课系统中，很难找到适合自己风格的老师？  
你是否觉得大学四年，应该有属于自己的课外学习机会？

BBUAA 为你提供一个在寝室就能搜索、回放、下载北航 classroom 课程的平台。

---

## 功能

| 功能 | 说明 |
|:---: |:---:|
| **课程搜索** | 按课程名、教师、编号、学院、学期、日期、校区/教学楼/教室多维度筛选 |
| **视频回放** | 在浏览器中直接播放课程录播视频，支持进度条拖拽、倍速（0.5× ~ 2×）、全屏 |
| **PPT 同步** | 视频播放时 PPT 幻灯片自动跟随，也可手动翻页 |
| **PPT 下载** | 一键导出为 `.pptx` 文件（16:9 宽屏），可离线编辑 |
| **SSO 登录** | 模拟北航统一认证，cookie 持久化，一次登录多次使用 |
| **登出** | 右上角一键清除 cookie |

### 搜索维度

课程名称 · 教师名称 · 课程编号 · 开课学院 · 学期 · 上课日期 · 校区 · 教学楼 · 教室

### 播放器快捷键

| 按键 | 功能 |
|:---|:---|
| `Space` | 播放 / 暂停 |
| `F` | 全屏 |
| `←` `→` | 上一页 / 下一页 PPT（同步跳转视频） |
| `Ctrl` + `←` `→` | 快退 / 快进 10 秒 |
| `↑` `↓` | 音量 ±10% |
| `M` | 静音 |

---

## 快速开始

```bash
git clone https://github.com/aleafofwutong/BBUAA.git
cd BBUAA
bash setup.sh          # 一键安装依赖
bash start_bbuaa.sh     # 启动服务
```

浏览器打开 `http://127.0.0.1:8765`，输入北航学号/工号和密码登录即可搜索课程。

### 环境要求

- Python >= 3.10
- 网络可访问 `classroom.msa.buaa.edu.cn`（可能需要代理）

### 代理配置

如果校园网无法直接访问 BUA 服务器，需配置代理：

```bash
export BBUAA_PROXY=http://127.0.0.1:7897
bash start_bbuaa.sh
```

如果不需要代理：

```bash
export BBUAA_PROXY=none
```

### 可选：账号环境变量

```bash
export BBUAA_USERNAME=你的学号
export BBUAA_PASSWORD=你的密码
```

设置后登录页会自动填入。

---

## 项目结构

```
BBUAA/
├── assemble/              # 核心模块
│   ├── __init__.py
│   ├── sso_login.py       # SSO 登录，cookie 管理
│   ├── courses.py         # 课程搜索 / PPT 时间轴 / 视频地址解析
│   ├── server.py          # Flask Web 服务，API 路由，视频/图片代理
│   └── web/
│       ├── index.html     # 课程搜索页面
│       ├── player.html    # 视频 + PPT 同步播放器
│       ├── app.js         # 搜索页面逻辑
│       ├── style.css      # 样式
│       └── cookies.json   # 登录凭证缓存
├── start_bbuaa.sh         # 启动脚本
├── setup.sh               # 一键安装脚本
└── README.md
```

### 后端 API

| 路由 | 说明 |
|:---|:---|
| `GET /` | 课程搜索页面 |
| `POST /api/auth/login` | SSO 登录 |
| `GET /api/auth/logout` | 登出（删除 cookie） |
| `GET /api/courses/search` | 课程搜索 |
| `GET /api/courses/detail` | 课程详情（视频地址） |
| `GET /api/courses/ppt` | PPT 时间轴 |
| `GET /api/courses/ppt/download` | PPT 导出 .pptx |
| `GET /player/` | 播放器页面 |
| `GET /api/proxy/video` | 视频流代理（注入 cookie） |
| `GET /api/proxy/image` | 图片代理（注入 cookie） |
| `POST /api/shutdown` | 关闭服务 |

---

## 技术栈

| 层 | 技术 |
|:---|:---|
| 前端 | Vanilla JS + hls.js + CSS3 |
| 后端 | Python Flask + requests |
| 认证 | 北航 CAS SSO 模拟 + JWT Bearer Token |
| 视频 | HLS (m3u8) / MP4 流代理 |
| PPT | python-pptx 生成 + PIL 图片处理 |
| 抓包 | mitmproxy (addons.py) |

---

## 声明

- 本项目仅供学习交流使用，**严禁用于商业和非法用途**
- 使用了部分逆向和爬虫技术，请勿滥用
- 本网站不会收集任何个人信息，但请注意保管好自己的 cookie 和密码
- 目前仅在 Chrome 浏览器测试，其他浏览器可能存在兼容性问题
- 如有疑问请在 [GitHub Issues](https://github.com/aleafofwutong/BBUAA/issues) 提交

---

*祝学业进步！*
