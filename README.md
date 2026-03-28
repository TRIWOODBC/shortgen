# ShortGen - AI 视频生成 Agent

AI 驱动的短视频自动化生产工具，支持两种模式：
1. **剧情模式**：输入一段剧情描述，自动分镜并生成视频
2. **热点模式**：自动获取最新热点，生成热点视频

## 功能特性

- 🎬 **智能分镜**：使用 Claude AI 将剧情转换为专业分镜脚本
- 🔥 **热点追踪**：自动获取微博/知乎/百度等平台热点
- 🎥 **视频生成**：支持 即梦、Runway Gen-3、Pika Labs 等视频生成平台
- 🇨🇳 **国内优化**：即梦平台无需翻墙，更适合国内用户
- 📱 **竖屏优化**：默认 9:16 比例，适合短视频平台
- 🔄 **批量处理**：支持多场景批量生成

## 项目结构

```
shortgen/
├── main.py              # 主入口和 CLI
├── requirements.txt     # 依赖
├── .env.example         # 环境变量模板
├── src/
│   ├── __init__.py
│   ├── config.py        # 配置管理
│   ├── models.py        # 数据模型
│   ├── storyboard.py    # 分镜生成器
│   ├── trending.py      # 热点获取器
│   └── video_gen.py     # 视频生成器
└── output/              # 输出目录
    ├── videos/          # 生成的视频
    ├── storyboards/     # 分镜脚本
    └── images/          # 生成的图片
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，填入你的 API 密钥
```

必需配置：
- `ANTHROPIC_API_KEY` - Claude API 密钥
- **视频生成（三选一）**：
  - **即梦（推荐国内用户）**: `DREAMINA_SESSION_ID`, `DREAMINA_UID`, `DREAMINA_DID`
  - Runway: `RUNWAY_API_KEY`
  - Pika: `PIKA_API_KEY`

可选配置：
- `NEWS_API_KEY` - NewsAPI 密钥（用于国际新闻热点）
- `HTTP_PROXY` / `HTTPS_PROXY` - 代理设置

### 3. 运行

**交互模式（推荐新手）**：
```bash
python main.py -i
```

**从剧情生成视频**：
```bash
python main.py -p "一个年轻人独自在深夜的地铁站等车，突然听到奇怪的声音..."
```

**从文件读取剧情**：
```bash
python main.py -f plot.txt
```

**根据热点生成视频**：
```bash
python main.py -t
```

指定热点类别：
```bash
python main.py -t -c tech  # 科技热点
```

## 使用示例

### 示例 1：自定义剧情

```bash
python main.py -p "一位老人在海边等待日出，回忆年轻时的爱情故事" -o sunrise_memory
```

输出：
- `output/storyboards/sunrise_memory.json` - 分镜脚本（JSON）
- `output/storyboards/sunrise_memory.md` - 分镜脚本（Markdown，可阅读）
- `output/videos/sunrise_memory_*.mp4` - 生成的视频片段

### 示例 2：热点视频

```bash
python main.py -t
```

流程：
1. 自动获取当前微博热搜
2. 选择热度最高的话题
3. AI 根据热点创作剧情
4. 生成分镜脚本
5. 调用视频 API 生成视频

## 配置详解

### 视频生成平台选择

当前支持：

| 平台 | 特点 | 配置项 | 适用场景 |
|-----|------|-------|---------|
| **即梦 (Dreamina)** ⭐ | 字节出品，国内直连，速度快 | `DREAMINA_SESSION_ID` / `UID` / `DID` | 国内用户首选 |
| Runway Gen-3 | 质量最高，支持 10 秒 | `RUNWAY_API_KEY` | 追求画质 |
| Pika Labs | 免费额度多，速度快 | `PIKA_API_KEY` | 快速测试 |

**优先级**：如果同时配置了多个，默认优先使用即梦（国内用户最友好）。

#### 即梦 (Dreamina) 配置方法

由于即梦目前没有开放官方 API，需要通过 Cookie 方式调用：

1. 打开浏览器，访问 https://jimeng.jianying.com/
2. 登录你的账号
3. 按 `F12` 打开开发者工具 → Application/应用 → Cookies
4. 找到并复制以下三个值：
   - `sessionid`
   - `uid`
   - `did`
5. 填入 `.env` 文件：
   ```env
   DREAMINA_SESSION_ID=xxx
   DREAMINA_UID=xxx
   DREAMINA_DID=xxx
   ```

6. **指定使用即梦**（可选）：
   ```env
   VIDEO_PROVIDER=dreamina
   ```

### 热点数据源

| 数据源 | 特点 | 是否需要 API Key |
|-------|------|-----------------|
| NewsAPI | 国际新闻，分类详细 | 需要 `NEWS_API_KEY` |
| 微博热搜 | 国内热点，实时性强 | 不需要 |
| 知乎热榜 | 深度话题讨论 | 不需要 |
| 百度热搜 | 综合搜索热点 | 不需要 |

**默认**：如果没有配置 `NEWS_API_KEY`，使用微博热搜。

### 代理设置

如果需要代理访问 API：

```env
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890
```

## 开发计划

- [x] 添加即梦 (Dreamina) 支持
- [ ] 添加可灵支持
- [x] 支持图片生成视频（Img2Video）- 即梦已实现
- [ ] 视频自动剪辑合并
- [ ] 添加背景音乐和配音
- [ ] 支持字幕生成
- [ ] Web UI 界面

## 注意事项

1. **API 费用**：视频生成 API 通常按秒计费，请注意用量
2. **生成时间**：单个场景视频生成可能需要 1-5 分钟
3. **网络要求**：
   - 即梦：国内直连，无需翻墙 ⭐
   - Runway/Pika：可能需要海外网络
4. **Cookie 有效期**：即梦的 `sessionid` 可能会过期，需要定期更新
5. **内容审核**：生成的视频需遵守平台内容规范

## License

MIT
