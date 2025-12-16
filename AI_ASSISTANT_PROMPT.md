# AI 助手项目构建提示词

## 🎯 项目背景与目标

你是一位拥有 10 年经验的全栈架构师，现在需要帮我从零开始构建一个轻量级 MVP 产品。

### 商业模式参考
- **对标产品**: clipto.com
- **核心业务**: YouTube 视频下载 + AI 语音转文字（Transcription）
- **目标市场**: 巴西（需考虑低配设备优化）

### 技术约束
- **必须使用**: Python + FastAPI 后端
- **AI 服务**: 阿里云 Paraformer-v2（语音转文字）
- **云存储**: 阿里云 OSS
- **视频下载**: yt-dlp（支持最新反爬机制）

---

## 📋 核心功能需求

### MVP 必须实现（P0）
1. **YouTube 视频下载**
   - 支持标准 YouTube URL 解析
   - 支持 720p 及以下清晰度
   - 实现三重降级策略（默认模式 → Android 客户端 → TV Embedded）
   - 支持代理配置（绕过地域限制）

2. **音频提取与转录**
   - 使用 FFmpeg 从视频提取音频
   - 音频格式：单声道、16kHz、WAV
   - 使用阿里云 Paraformer-v2 API 进行转录
   - 返回带时间戳的转录结果（精确到毫秒）

3. **云存储**
   - 视频文件上传到阿里云 OSS
   - 音频文件上传到阿里云 OSS
   - 生成公网可访问的 URL

4. **REST API**
   - `POST /api/v1/process` - 提交视频处理任务
   - `GET /api/v1/status/{task_id}` - 查询处理状态
   - `GET /api/v1/result/{task_id}` - 获取转录结果
   - `GET /api/v1/download/{task_id}/subtitle` - 下载 SRT 字幕

### 推荐实现（P1）
- 用户认证（JWT Token）
- 配额管理（每月视频数量限制）
- 异步任务队列（Celery + Redis）
- 处理进度实时更新

### 暂不实现（移除的功能）
- ❌ 关键帧提取
- ❌ LLM 视频总结
- ❌ 场景检测
- ❌ 复杂的前端界面

---

## 🛠️ 技术栈要求

### 后端框架
```python
fastapi==0.100.0
uvicorn==0.23.0
python-multipart>=0.0.6
```

### 核心依赖
```python
# 视频下载
yt-dlp>=2024.10.7

# AI 转录
dashscope>=1.14.0

# 云存储
oss2>=2.18.0

# 音视频处理
ffmpeg-python>=0.2.0

# 基础工具
python-dotenv>=1.0.0
asyncio>=3.4.3
requests>=2.31.0
```

### 系统依赖
- FFmpeg >= 4.4
- Redis >= 6.0（可选，用于任务队列）

---

## 📁 项目结构要求

```
mvp_youtube_transcriber/
├── app/
│   ├── main.py                  # FastAPI 应用入口
│   ├── config.py                # 配置管理
│   ├── models.py                # Pydantic 数据模型
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py            # API 路由
│   ├── services/
│   │   ├── __init__.py
│   │   ├── downloader.py        # YouTube 下载服务
│   │   ├── transcriber.py       # 音频转录服务
│   │   └── storage.py           # OSS 存储服务
│   └── utils/
│       ├── __init__.py
│       └── ffmpeg_tools.py      # FFmpeg 工具函数
├── tests/
│   ├── test_downloader.py
│   ├── test_transcriber.py
│   └── test_integration.py
├── .env.example
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## 🔑 核心代码实现要求

### 1. YouTube 下载器（downloader.py）

**必须实现的功能**:
```python
class YouTubeDownloader:
    def __init__(self, proxy: Optional[str] = None):
        """初始化下载器，支持可选的代理配置"""
        pass
    
    async def download(self, url: str, output_dir: str) -> str:
        """
        下载 YouTube 视频
        
        实现要求：
        1. 三重降级策略（默认 → Android → TV Embedded）
        2. 支持代理配置
        3. 返回下载的视频文件路径
        4. 优先下载 720p 及以下清晰度
        """
        pass
    
    def _build_ytdl_config(self) -> dict:
        """
        构建 yt-dlp 配置
        
        必须包含：
        - User-Agent 浏览器模拟
        - extractor_args 客户端切换
        - 代理配置
        - 格式选择
        """
        pass
```

**关键配置参数**:
```python
ytdl_opts = {
    'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best',
    'merge_output_format': 'mp4',
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0 Safari/537.36',
    },
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'web'],
        }
    },
    'proxy': proxy,  # 如果提供
    'no_cache_dir': True,
}
```

### 2. 音频转录器（transcriber.py）

**必须实现的功能**:
```python
class ParaformerTranscriber:
    def __init__(self, api_key: str):
        """使用阿里云 API Key 初始化"""
        pass
    
    async def transcribe_from_url(
        self, 
        audio_url: str,
        enable_diarization: bool = True
    ) -> List[Dict]:
        """
        从音频 URL 转录
        
        实现要求：
        1. 调用 Paraformer-v2 异步 API
        2. 轮询任务状态（每 5 秒查询一次）
        3. 最多等待 5 分钟
        4. 返回带时间戳的转录段落
        """
        pass
    
    def _parse_result(self, output) -> List[Dict]:
        """
        解析 Paraformer 返回结果
        
        返回格式：
        [
            {
                'text': '这是一句话',
                'start_time': 0.1,  # 秒
                'end_time': 3.5,
                'speaker_id': 0
            }
        ]
        """
        pass
```

**API 调用流程**:
```python
# 1. 提交异步任务
response = Transcription.async_call(
    model='paraformer-v2',
    file_urls=[audio_url],
    diarization_enabled=True
)
task_id = response.output.task_id

# 2. 轮询状态
while elapsed < 300:  # 最多 5 分钟
    await asyncio.sleep(5)
    result = Transcription.fetch(task=task_id)
    
    if result.output.task_status == "SUCCEEDED":
        return self._parse_result(result.output)
```

### 3. OSS 存储服务（storage.py）

**必须实现的功能**:
```python
class OSSStorage:
    def __init__(
        self, 
        access_key_id: str,
        access_key_secret: str,
        bucket_name: str,
        endpoint: str
    ):
        """初始化 OSS 客户端"""
        pass
    
    async def upload_file(
        self, 
        local_path: str, 
        object_key: str
    ) -> str:
        """
        上传文件到 OSS
        
        返回：公网可访问的 URL
        """
        pass
    
    def get_public_url(self, object_key: str) -> str:
        """生成 OSS 公网 URL"""
        return f"https://{self.bucket_name}.{self.endpoint}/{object_key}"
```

### 4. FFmpeg 工具函数（ffmpeg_tools.py）

```python
async def extract_audio(
    video_path: str, 
    output_path: Optional[str] = None
) -> str:
    """
    从视频提取音频
    
    要求：
    - 单声道（mono）
    - 16kHz 采样率
    - PCM 16-bit 编码
    - WAV 格式
    """
    cmd = [
        'ffmpeg', '-i', video_path,
        '-vn',
        '-acodec', 'pcm_s16le',
        '-ar', '16000',
        '-ac', '1',
        '-f', 'wav',
        output_path, '-y'
    ]
    
    process = await asyncio.create_subprocess_exec(*cmd)
    await process.communicate()
    return output_path
```

### 5. API 路由（routes.py）

```python
@router.post("/api/v1/process")
async def process_video(request: ProcessRequest):
    """
    处理视频
    
    请求体：
    {
        "youtube_url": "https://www.youtube.com/watch?v=xxx",
        "enable_transcription": true
    }
    
    响应：
    {
        "task_id": "uuid-xxx",
        "status": "processing"
    }
    """
    pass

@router.get("/api/v1/status/{task_id}")
async def get_status(task_id: str):
    """
    查询任务状态
    
    响应：
    {
        "status": "processing|completed|failed",
        "progress": 50,
        "error_message": null
    }
    """
    pass

@router.get("/api/v1/result/{task_id}")
async def get_result(task_id: str):
    """
    获取处理结果
    
    响应：
    {
        "video_url": "https://oss.aliyuncs.com/xxx.mp4",
        "audio_url": "https://oss.aliyuncs.com/xxx.wav",
        "transcript": [
            {
                "text": "转录内容",
                "start_time": 0.1,
                "end_time": 3.5
            }
        ]
    }
    """
    pass
```

---

## 🔧 环境配置要求

### .env.example
```bash
# 阿里云 AI 服务
QWEN_API_KEY=sk-your-api-key-here

# 阿里云 OSS
OSS_ACCESS_KEY_ID=your-access-key-id
OSS_ACCESS_KEY_SECRET=your-access-key-secret
OSS_BUCKET=your-bucket-name
OSS_ENDPOINT=oss-cn-beijing.aliyuncs.com

# YouTube 代理（可选）
YOUTUBE_PROXY=http://127.0.0.1:7890

# 应用配置
TEMP_DIR=/tmp/video_processing
LOG_LEVEL=INFO
```

### config.py
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # API Keys
    qwen_api_key: str
    
    # OSS
    oss_access_key_id: str
    oss_access_key_secret: str
    oss_bucket: str
    oss_endpoint: str
    
    # Optional
    youtube_proxy: Optional[str] = None
    temp_dir: str = "/tmp/video_processing"
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"

settings = Settings()
```

---

## 🧪 测试要求

### 单元测试
```python
# tests/test_downloader.py
async def test_download_youtube_video():
    """测试下载 YouTube 视频"""
    downloader = YouTubeDownloader()
    video_path = await downloader.download(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "/tmp"
    )
    assert os.path.exists(video_path)

# tests/test_transcriber.py
async def test_transcribe_audio():
    """测试音频转录"""
    transcriber = ParaformerTranscriber(api_key="sk-xxx")
    segments = await transcriber.transcribe_from_url(
        "https://oss.aliyuncs.com/test.wav"
    )
    assert len(segments) > 0
    assert 'text' in segments[0]
```

### 集成测试
```python
# tests/test_integration.py
async def test_full_pipeline():
    """测试完整处理流程"""
    # 1. 下载视频
    downloader = YouTubeDownloader()
    video_path = await downloader.download(url, "/tmp")
    
    # 2. 提取音频
    audio_path = await extract_audio(video_path)
    
    # 3. 上传到 OSS
    storage = OSSStorage(...)
    audio_url = await storage.upload_file(audio_path, "test.wav")
    
    # 4. 转录
    transcriber = ParaformerTranscriber(...)
    segments = await transcriber.transcribe_from_url(audio_url)
    
    assert len(segments) > 0
```

---

## 🚀 启动与部署

### 本地开发
```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
vim .env  # 填写真实的 API Key

# 3. 启动服务
uvicorn app.main:app --reload --port 8000

# 4. 访问 API 文档
open http://localhost:8000/docs
```

### Docker 部署
```dockerfile
FROM python:3.9-slim

# 安装 FFmpeg
RUN apt-get update && apt-get install -y ffmpeg

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY app/ /app/
WORKDIR /app

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.yml
```yaml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - QWEN_API_KEY=${QWEN_API_KEY}
      - OSS_ACCESS_KEY_ID=${OSS_ACCESS_KEY_ID}
    volumes:
      - /tmp:/tmp
```

---

## 📊 性能指标要求

### 处理速度
- 单个 5 分钟视频处理时间：< 2 分钟
- 下载速度：> 1MB/s
- 转录速度：实时的 0.1 倍（5 分钟音频约 30 秒）

### 资源使用
- 内存峰值：< 2GB
- CPU 使用率：< 80%
- 磁盘临时空间：< 500MB/视频

### 可靠性
- YouTube 下载成功率：> 95%
- 音频转录成功率：> 90%
- API 可用性：> 99%

---

## 💰 成本优化建议

### 1. 视频质量控制
```python
# 降低到 480p 节省 50% 流量
'format': 'bestvideo[height<=480]+bestaudio/best[height<=480]/best'
```

### 2. 音频压缩
```python
# 使用 8kHz MP3 替代 16kHz WAV
cmd = [
    'ffmpeg', '-i', video_path,
    '-vn', '-ar', '8000', '-ac', '1',
    '-b:a', '64k', '-f', 'mp3',
    output_path, '-y'
]
```

### 3. OSS 生命周期
- 7 天后自动删除临时文件
- 30 天后迁移到归档存储

---

## 🎨 代码风格要求

### 命名规范
- 类名：大驼峰（`YouTubeDownloader`）
- 函数名：小写下划线（`extract_audio`）
- 常量：大写下划线（`MAX_RETRY_COUNT`）

### 文档字符串
```python
async def download(self, url: str, output_dir: str) -> str:
    """
    Download YouTube video to local directory.
    
    Args:
        url: YouTube video URL
        output_dir: Local directory to save video
        
    Returns:
        Path to downloaded video file
        
    Raises:
        DownloadError: If all download strategies fail
    """
    pass
```

### 错误处理
```python
try:
    video_path = await downloader.download(url)
except DownloadError as e:
    logger.error(f"Download failed: {e}")
    raise HTTPException(
        status_code=503,
        detail=f"Failed to download video: {str(e)}"
    )
```

---

## 📖 文档交付要求

请在项目完成后提供以下文档：

1. **README.md** - 项目简介、快速开始、API 文档
2. **DEPLOYMENT.md** - 部署指南（Docker、云服务器）
3. **TROUBLESHOOTING.md** - 常见问题与解决方案
4. **API.md** - API 端点详细说明（或使用 Swagger）

---

## ✅ 验收标准

### 功能验收
- [ ] 可以成功下载 YouTube 视频（测试 10 个不同的 URL）
- [ ] 可以正确提取音频（单声道 16kHz WAV）
- [ ] 可以成功调用 Paraformer 转录（准确率 > 90%）
- [ ] 转录结果包含正确的时间戳
- [ ] 文件成功上传到阿里云 OSS
- [ ] API 端点全部可访问（/docs 页面正常）

### 性能验收
- [ ] 5 分钟视频处理时间 < 2 分钟
- [ ] 内存使用峰值 < 2GB
- [ ] 可以同时处理 3 个视频任务

### 代码质量
- [ ] 单元测试覆盖率 > 80%
- [ ] 所有测试通过（pytest）
- [ ] 代码符合 PEP 8 规范（flake8）
- [ ] 无严重安全漏洞（bandit）

---

## 🚨 注意事项

### 安全性
- ⚠️ **绝对不要**将 API Key 硬编码到代码中
- ⚠️ **必须使用**环境变量管理敏感信息
- ⚠️ **需要配置** CORS 白名单（生产环境）

### 稳定性
- 所有外部 API 调用必须有重试机制（最多 3 次）
- 必须处理网络超时（timeout 60 秒）
- 临时文件必须在处理完成后清理

### 可维护性
- 每个函数不超过 50 行
- 复杂逻辑必须添加注释
- 关键步骤必须记录日志

---

## 📞 技术支持参考

### 官方文档
- **yt-dlp**: https://github.com/yt-dlp/yt-dlp
- **Paraformer**: https://help.aliyun.com/zh/model-studio/paraformer
- **阿里云 OSS Python SDK**: https://help.aliyun.com/document_detail/32026.html
- **FastAPI**: https://fastapi.tiangolo.com/

### 常见问题
- YouTube 403 错误 → 使用代理 + Android 客户端
- Paraformer 超时 → 增加轮询时间到 10 分钟
- OSS 上传失败 → 检查 Bucket 权限配置

---

**提示词版本**: v1.0  
**适用场景**: 从零开始构建 YouTube 视频下载 + AI 转录 MVP 项目  
**预计开发时间**: 7-10 天（单人）  
**技术难度**: 中级（需要熟悉 Python 异步编程）

---

## 🎯 开始指令

请根据以上要求，按照以下步骤开始构建项目：

1. **创建项目结构** - 按照指定的目录结构创建文件
2. **实现核心服务** - 依次实现 downloader.py、transcriber.py、storage.py
3. **开发 API 路由** - 实现所有 REST API 端点
4. **编写测试** - 确保单元测试和集成测试通过
5. **配置部署** - 编写 Dockerfile 和 docker-compose.yml
6. **生成文档** - 完善 README 和 API 文档

请开始执行！
