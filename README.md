# ShortGen

ShortGen 是一个本地 CLI 项目，用来把一段剧情自动变成短视频生产流程。

当前这版重点已经放在这条链路上：

1. 输入剧情
2. LLM 生成分镜稿
3. 生成角色图
4. 生成分镜图
5. 生成视频片段
6. 可选生成音频并用 FFmpeg 合成成片

项目现在更适合做原型验证和自动化内容生产测试，还不是一个完全打磨好的产品平台。

## 当前能力

- 剧情转分镜稿
- 热点转剧情再转分镜
- 角色图生成
- 分镜图生成
- 即梦 / Runway / Pika 视频生成路由
- 可选 TTS、BGM、FFmpeg 合成
- 每次运行按项目名单独输出到独立文件夹

## 当前推荐用法

如果你在国内环境、并且想先把“分镜稿 + 角色图 + 分镜图 + 视频”跑通，当前推荐组合是：

- `LLM_PROVIDER=deepseek`
- `VIDEO_PROVIDER=dreamina`
- `CHARACTER_IMAGE_PROVIDER=signed_aksk`
- `CHARACTER_IMAGE_MODEL=jimeng_t2i_v40`

## 环境要求

- Python 3.10+
- `ffmpeg` 已安装并可在命令行直接调用

macOS 安装 FFmpeg：

```bash
brew install ffmpeg
```

## 安装

```bash
cd shortgen-1
pip install -r requirements.txt
cp .env.example .env
```

然后去编辑项目根目录下的 `.env` 文件，把你自己的 API 信息填进去。

## API 要填在哪里

统一填写在：

- [`.env`](./.env.example)

实际使用时请先复制一份：

```bash
cp .env.example .env
```

然后改 `.env`，不要直接改 `.env.example`。

## 最小可运行配置

至少需要两类配置：

1. 一个 LLM Key，用来生成分镜稿
2. 一个视频 provider，用来生成视频

如果你还要生成角色图，建议同时配置火山即梦图片能力。

最小示例：

```env
# 分镜 LLM
LLM_PROVIDER=deepseek
LLM_API_KEY=your_llm_api_key

# 视频生成：即梦
VIDEO_PROVIDER=dreamina
VOLC_ACCESS_KEY=your_volc_access_key
VOLC_SECRET_KEY=your_volc_secret_key
JIMENG_MODEL=jimeng_t2v_v30

# 角色图 / 分镜图
CHARACTER_IMAGE_PROVIDER=signed_aksk
CHARACTER_IMAGE_MODEL=jimeng_t2i_v40
```

## 常用配置说明

### 1. LLM 配置

在 `.env` 里填写：

```env
LLM_PROVIDER=deepseek
LLM_API_KEY=your_llm_api_key
```

支持的 `LLM_PROVIDER`：

- `deepseek`
- `glm`
- `kimi`
- `openai`
- `custom`

如果你要接自定义 OpenAI 兼容接口，可以再补：

```env
LLM_BASE_URL=https://your-openai-compatible-endpoint
LLM_MODEL=your-model-name
```

### 2. 即梦视频配置

如果你用即梦做视频，在 `.env` 里填写：

```env
VIDEO_PROVIDER=dreamina
VOLC_ACCESS_KEY=your_volc_access_key
VOLC_SECRET_KEY=your_volc_secret_key
JIMENG_MODEL=jimeng_t2v_v30
```

常见模型值：

- `jimeng_t2v_v30`
- `jimeng_t2v_v30_pro`

### 3. 角色图 / 分镜图配置

当前项目默认推荐这一组：

```env
CHARACTER_IMAGE_PROVIDER=signed_aksk
CHARACTER_IMAGE_MODEL=jimeng_t2i_v40
```

这条链路会使用你上面已经填写的：

- `VOLC_ACCESS_KEY`
- `VOLC_SECRET_KEY`

也就是说，如果你已经配好了即梦视频 AK/SK，通常不需要再额外给角色图单独配一套鉴权。

如果你要改成 Ark 图片接口，再填写：

```env
CHARACTER_IMAGE_PROVIDER=ark
ARK_API_KEY=your_ark_api_key
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
```

### 4. 音频配置

如果你想启用旁白 / 对话 TTS，在 `.env` 里填写：

```env
VOLC_TTS_APP_ID=your_tts_app_id
VOLC_TTS_ACCESS_TOKEN=your_tts_access_token
VOLC_TTS_DEFAULT_VOICE=zh_female_shuangkuaisisi_moon_bigtts
```

### 5. 热点和代理配置

可选：

```env
NEWS_API_KEY=your_newsapi_key
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890
```

## `.env.example` 里这些字段分别是干什么的

- `LLM_PROVIDER`：分镜稿用哪个 LLM
- `LLM_API_KEY`：分镜稿生成必须
- `VIDEO_PROVIDER`：视频生成平台
- `VOLC_ACCESS_KEY` / `VOLC_SECRET_KEY`：即梦视频、签名图片接口共用
- `JIMENG_MODEL`：即梦视频模型
- `CHARACTER_IMAGE_PROVIDER`：角色图 / 分镜图生成方式
- `CHARACTER_IMAGE_MODEL`：角色图 / 分镜图模型或 `req_key`
- `VOLC_TTS_APP_ID` / `VOLC_TTS_ACCESS_TOKEN`：音频合成
- `NEWS_API_KEY`：热点模式可选
- `HTTP_PROXY` / `HTTPS_PROXY`：网络代理可选

## 使用方式

### 1. 交互模式

```bash
python main.py -i
```

### 2. 用一句剧情直接生成

基础模式：

```bash
python main.py -p "一个年轻人独自在深夜的地铁站等车"
```

完整模式：

```bash
python main.py -p "一个年轻人独自在深夜的地铁站等车" --full
```

### 3. 从文件读取剧情

```bash
python main.py -f plot.txt --full
```

### 4. 指定视频 provider

```bash
python main.py -p "一个古代将军守城的故事" --provider dreamina --full
```

### 5. 热点模式

```bash
python main.py -t --full
```

指定热点类别：

```bash
python main.py -t -c tech --full
```

### 6. 关闭音频或角色增强

```bash
python main.py -p "一个海边回忆故事" --full --no-audio
python main.py -p "一个海边回忆故事" --full --no-characters
```

## 输出目录

现在每次运行都会建立独立项目目录：

```text
output/projects/<项目名>/
├── storyboards/
├── characters/
├── images/
├── videos/
├── audios/
└── final/
```

如果你通过 `-o my_project` 指定输出名，项目目录通常会变成：

```text
output/projects/my_project/
```

如果你不传 `-o`，程序会自动生成一个带时间戳的项目名。

## 当前实现边界

已经可用：

- 剧情 -> 分镜稿
- 角色图生成
- 分镜图生成
- 视频生成
- 基础音频和最终合成
- 输出目录按项目隔离

仍在持续优化：

- 角色图参与分镜图生成时，不同 provider 的参考图支持程度不同
- 音频和镜头时长的精确对齐还可以继续加强
- 外部 API 的稳定性、配额和风控会直接影响结果

## 依赖说明

项目运行依赖见 [requirements.txt](./requirements.txt)。

核心依赖包括：

- `openai`
- `python-dotenv`
- `pydantic`
- `httpx`
- `requests`
- `Pillow`
- `beautifulsoup4`
- `volcengine`

## 建议

如果你是第一次跑，建议顺序是：

1. 先配置好 `.env`
2. 先跑一段短剧情
3. 先确认 `storyboards/`、`characters/`、`images/` 是否正常
4. 再去跑完整视频

这样更容易排查是 LLM、图片、视频，还是 FFmpeg 哪一层出了问题。
