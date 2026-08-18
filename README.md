# xhs-vault

**收藏夹不是终点，是起点。**

小红书收藏夹是个只进不出的地方——存了几百条，再也没打开过。这个项目把它们完整取出来，
变成可搜索、可分类、可提问的本地知识库。

具体承诺：

- 把收藏夹全量导出（不是一条条贴链接）
- 提取**帖子正文 + 视频字幕 + 图片文字**
- **全程零 API 成本**，全部本地跑
- 产出：可交互看板 + Obsidian 库 + 树状画布 + 本地搜索

一个真实规模的参考：454 条收藏 → 103 万字正文，其中视频字幕 60 万字、图片 OCR 29 万字。
没花一分钱 API 费用。

## 哪些环节需要 agent

大部分不需要。这是有意的设计——抓取和处理是确定性的活，交给模型只会更慢更贵更不可靠。

| 环节 | 需要 agent 吗 |
|---|---|
| 导出清单 · 抓取 · 视频字幕 · 图片 OCR · 分类 · 生成看板 | **不需要**，纯本地脚本 |
| 安装配置、按你的收藏调分类 | 可以让 agent 代做 |
| 增强搜索 | **agent 接管** |

所以你可以完全不碰 agent 就用起来——只是搜索会退化成关键词匹配，问不了
「我想做 X，收藏夹里有哪些能用的」这类问题。

增强搜索默认走 [Claude Code](https://claude.com/claude-code)，换成别的 agent 也行，
改一个函数。细节见 [AGENTS.md](AGENTS.md)。

**把仓库直接交给任何编码 agent，让它照 `AGENTS.md` 帮你装好、按你的收藏调分类。**

## 为什么能做到零成本

三个发现，每个都省掉了一大块开销：

| | 常规做法 | 这里的做法 |
|---|---|---|
| 抓取鉴权 | 导出 cookies | **不需要**。带 `xsec_token` 的 explore 链接未登录也返回完整 `__INITIAL_STATE__` |
| 视频内容 | 下载 + Whisper 转录 | **优先用平台自带 SRT 字幕**。实测大多数视频都有，一条 curl 的事 |
| 图片文字 | 调多模态模型 OCR | **macOS Vision 本地识别**（`tools/ocr.swift`）。中文质量够用，免费，比调模型快几百倍 |

架构上的关键决定：**把「机械抓取」和「模型理解」拆开。**
抓取、识别、分类是纯本地流水线；模型只在真正需要语义判断的地方介入（问答、写总结）。
不拆开的话，几百条笔记就是几百次模型调用。

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

调优有几个坑，都是实打实踩出来的 —— 见 [docs/分类调优.md](docs/分类调优.md)。
省你几小时：通用词有毒、作者名会污染判断、顺序即优先级。

## 局限

诚实说清楚：

- **依赖小红书未公开的内部结构**（`__INITIAL_STATE__` 的字段路径、收藏接口）。
  平台改版就会坏。这类项目需要持续维护，不是一次性的
- **只在 macOS 验证过**。本地 OCR 用的是 macOS Vision framework
- **无字幕的视频不处理**。需要 Whisper，成本另算
- 分类是规则驱动的。规则能到八成左右，剩下的语义判断需要人工覆盖
  （`data/overrides.json`）或让模型逐条读
- 页面显示的收藏总数可能比导出到的多。收藏专辑里的笔记、已删除的笔记都可能造成差值

## 边界

- 只抓你自己账号的收藏，只存在你自己机器上
- 服务只监听 `127.0.0.1`，且**故意没开 CORS**——深度模式下这个接口能执行 Bash，
  开放通配 CORS 等于让你访问的任何网站都能调它
- 抓取间隔别调快。这是别人的服务器

## 致谢

思路起点是 [chenxiachan/xhs-claude-skills](https://github.com/chenxiachan/xhs-claude-skills)。
`__INITIAL_STATE__` 的解析路径、「视频优先用平台字幕」的策略判断都来自那个项目。

实测中修正了三处：cookies 不是必需的；字幕的实际位置比文档写的深一层
（`media.video.subtitles` 而非 `media.subtitles`，按错的路径找会把所有有字幕的视频
误判成需要 Whisper）；图片 OCR 用本地 Vision 就够，不必调模型。

## License

MIT
