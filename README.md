# xhs-vault

把小红书收藏夹导出到本地，提取正文、视频字幕和图片里的文字，生成可搜索的知识库。

小红书没有收藏夹导出功能，存进去的内容只能在 App 里一条条翻。这个项目把它们取出来，
落成本地文件。

能做到什么：

- 一次导出整个收藏夹，不用手动贴链接
- 提取三种内容：帖子正文、视频字幕、图片里的文字
- 全程本地运行，不调用付费 API
- 产出：可交互看板、Obsidian 笔记库、树状画布、本地搜索

在一个 454 条的收藏夹上实测：提取到 103 万字，其中视频字幕 60 万字、图片 OCR 29 万字。

## 哪些环节需要 agent

大部分不需要。抓取和处理的输入输出是确定的，用脚本比用模型更快，出错也更好排查。

| 环节 | 需要 agent 吗 |
|---|---|
| 导出清单 · 抓取 · 视频字幕 · 图片 OCR · 分类 · 生成看板 | 不需要，纯本地脚本 |
| 安装配置、按你的收藏调分类 | 可以让 agent 代做 |
| 增强搜索 | agent 接管 |

不用 agent 也能跑完整条流水线，只是搜索退化成关键词匹配，问不了
「我想做 X，收藏夹里有哪些能用的」这类问题。

增强搜索默认调 [Claude Code](https://claude.com/claude-code)，改一个函数就能换成别的 agent，
细节见 [AGENTS.md](AGENTS.md)。把仓库交给编码 agent，它可以照那份说明帮你装好、
按你的收藏调分类。

## 为什么不用付费 API

三处实测结果：

| | 常见做法 | 这里的做法 |
|---|---|---|
| 抓取鉴权 | 导出 cookies | 不需要。带 `xsec_token` 的 explore 链接未登录也返回完整 `__INITIAL_STATE__` |
| 视频内容 | 下载后用 Whisper 转录 | 优先取平台自带的 SRT 字幕。实测 152 个视频里 124 个有字幕，共 60 万字 |
| 图片文字 | 调多模态模型做 OCR | macOS Vision 本地识别（`tools/ocr.swift`）。实测 109 篇 / 约 830 张图 / 288,193 字 |

抓取、识别、分类都是本地脚本，模型只用在搜索问答这一处。
454 篇笔记如果每篇调一次模型，就是 454 次调用。

## 快速开始

### 0. 拉全量清单（唯一需要手动的一步）

1. Chrome 装 [Tampermonkey](https://www.tampermonkey.net/)
2. **`chrome://extensions` → 开发者模式 → Tampermonkey 详情 → 打开「允许用户脚本」**
   （Chrome 138+ 新增的总闸，不开脚本不会注入）
3. 新建脚本，粘贴 `userscript/xhs-export.user.js` 全文，保存
4. 打开小红书 → 我 → 收藏，右上角出现面板 → 点「开始滚动抓取」，**别切走标签页**
5. 数字不再增长后点「导出清单 JSON」，把文件放进 `data/`

### 1. 抓取与处理

```bash
python3 scraper/fetch.py            # 抓页面 → data/raw/ + data/subs/（字幕）
python3 scraper/classify.py         # 按标题分类 + 抽实体
python3 scraper/build_corpus.py     # 归一化 + 打处理档位
swiftc -O -o tools/ocr tools/ocr.swift -framework Vision -framework AppKit
python3 scraper/ocr_notes.py        # 本地 OCR
python3 scraper/build_corpus.py     # 并入 OCR 结果
python3 scraper/reclassify.py       # 用正文补分类（标题判断不了的）
python3 scraper/build_canvas.py     # 树状结构
python3 scraper/build_vault.py      # → out/vault/（Obsidian）
python3 scraper/build_html.py       # → out/dashboard.html
```

每步都可中断可续跑。`fetch.py` 默认每条间隔 1.5~3 秒，**不要调快**。

### 2. 用起来

双击 `start.command`，或 `python3 serve.py`，然后开 http://127.0.0.1:8899/dashboard.html

想让它常驻：双击 `install-autostart.command` 装一次（macOS LaunchAgent，可卸载）。

## 看板

四个视图：

- **回看** — 你自己写的分析结论（放 `out/回看.md`，会渲染进来）
- **搜索** — 关键词检索 + Claude 问答
- **画布** — 树状：领域 → 分类 → 子簇 → 笔记，可拖可缩
- **列表** — 全部笔记，可筛可搜，点开读全文

点任何笔记都能在本地读全文（帖子正文 / 视频字幕 / 图片文字分开标注），也能一键跳原帖。

## 搜索

两层：

| 层 | 机制 | 依赖 |
|---|---|---|
| 关键词 | BM25（字符 bigram，中文不需要分词器） | 无，离线可用 |
| Claude 问答 | 本地服务桥接 `claude -p` | [Claude Code](https://claude.com/claude-code) |

浏览器不能直接调模型（没有 API key，且有 CORS 限制），所以走本地桥接：

```
dashboard  →  serve.py (127.0.0.1)  →  claude -p  →  回答
```

问答有两种模式：

- **深度**（默认）：只告诉 Claude「库在哪、检索脚本怎么用」，它自己多轮搜索、
  自己决定读哪几条、交叉比对。1~2 分钟
- **快速**：服务端先用 BM25 筛 8 条塞给它读。~15 秒

深度模式成立的前提是 `claude -p` 有完整工具权限（能跑 Bash、读文件）。

## 把分类改成你自己的

（也可以直接让 agent 照 `AGENTS.md` 替你做。）


**只需要改 `scraper/taxonomy.py` 一个文件。** 默认那套是通用的，跑完之后看看
「其他」桶里有什么，回来改。

调优的坑记在 [docs/分类调优.md](docs/分类调优.md)：通用词会造成大面积误判、
作者名混进判断依据会带偏整条、规则顺序决定优先级。

## 局限

- **依赖小红书未公开的内部结构**（`__INITIAL_STATE__` 的字段路径、收藏接口）。
  平台改版就会坏，需要持续维护
- **只在 macOS 验证过**。本地 OCR 用的是 macOS Vision framework
- **无字幕的视频不处理**。需要 Whisper，成本另算
- 分类是规则驱动的。规则能到八成左右，剩下的语义判断需要人工覆盖
  （`data/overrides.json`）或让模型逐条读
- 页面显示的收藏总数可能比导出到的多。收藏专辑里的笔记、已删除的笔记都可能造成差值

## 边界

- 只抓你自己账号的收藏，只存在你自己机器上
- 服务只监听 `127.0.0.1`，并且没有开 CORS。深度模式下这个接口能执行 Bash，
  开放通配 CORS 会让你访问的任何网站都能调这个接口
- 抓取间隔别调快，那会给小红书的服务器增加负载，也更容易触发风控

## 致谢

思路起点是 [chenxiachan/xhs-claude-skills](https://github.com/chenxiachan/xhs-claude-skills)。
`__INITIAL_STATE__` 的解析路径、「视频优先用平台字幕」的策略判断都来自那个项目。

实测中修正了三处：cookies 不是必需的；字幕的实际位置比文档写的深一层
（`media.video.subtitles` 而非 `media.subtitles`，按错的路径找会把所有有字幕的视频
误判成需要 Whisper）；图片 OCR 用本地 Vision 就够，不必调模型。

## License

MIT
