# YouTube 1080p 视频下载实现指南

本文档记录了 YouTube 1080p 视频下载、FFmpeg 合成、OSS 上传的完整实现路径。

## 系统架构

```
用户请求 → Backend API → 
  ├── AgentGo (云端浏览器) → Cookies + Visitor Data
  ├── bgutil (Docker:4416) → PO Token
  ├── yt-dlp → URL 提取 (需要代理)
  ├── FFmpeg → 视频/音频合成 (需要代理)
  └── OSS (新加坡) → 文件存储 (禁用代理)
```

## 核心发现

### 1. 1080p 视频的特殊性

YouTube 的 1080p 及以上分辨率视频通常是 **video-only** 格式，需要单独下载音频流并合成：

- 720p 及以下：通常有 video+audio 合并格式，可直接下载
- 1080p 及以上：只有 video-only 格式，必须用 FFmpeg 合成

### 2. 代理配置的关键点

| 操作 | 代理需求 | 原因 |
|------|---------|------|
| yt-dlp URL 提取 | ✅ 需要 | 访问 YouTube API |
| FFmpeg 下载流 | ✅ 需要 | 下载 googlevideo.com 资源 |
| OSS 上传 | ❌ 禁用 | 新加坡 OSS 不需要代理，代理反而会导致连接问题 |

### 3. YouTube URL 的 IP 绑定

YouTube 的下载 URL 是 **IP 绑定** 的：
- 提取 URL 时的代理 IP 必须与下载时一致
- 如果代理 IP 变化，会返回 403 错误
- 建议使用 ClashX **全局模式** 保持 IP 稳定

## 环境配置

### backend/.env

```bash
# 阿里云 OSS 配置 (新加坡区域)
OSS_ACCESS_KEY_ID=your_access_key_id
OSS_ACCESS_KEY_SECRET=your_access_key_secret
OSS_ENDPOINT=oss-ap-southeast-1.aliyuncs.com
OSS_BUCKET=your-bucket-name

# HTTP 代理 (ClashX) - 本地开发用，生产环境可不配置
HTTP_PROXY=http://127.0.0.1:7890

# AgentGo 云端浏览器
AGENTGO_API_KEY=your_agentgo_api_key
AGENTGO_API_URL=https://api.datasea.network
```

### OSS Bucket 配置

- Bucket 名称: `youtube-download-sg`
- 区域: `ap-southeast-1` (新加坡)
- 权限: **公共读** (Public Read)
- 访问 URL 格式: `https://youtube-download-sg.oss-ap-southeast-1.aliyuncs.com/{object_key}`

## 核心代码实现

### 1. URL 提取 (url_extractor.py)

```python
class ExtractedVideo:
    def get_download_urls(self, resolution: str = "720") -> Dict[str, Any]:
        """
        获取下载 URL，优先级：
        1. 直接下载 (https) - 可直接下载
        2. 流式 (m3u8) - 需要 FFmpeg 转换
        """
        # 1080p 通常只有 video-only 格式
        if video_only_formats:
            best_video = select_best_format(video_only_formats, target_height)
            result['video_url'] = best_video.url
            result['needs_merge'] = True  # 标记需要合成
            
            # 获取最佳音频
            if audio_only_formats:
                result['audio_url'] = audio.url
```

关键点：
- `needs_merge=True` 表示需要 FFmpeg 合成
- 优先选择 MP4/M4A 格式 (H.264/AAC)
- 代理通过 `settings.http_proxy` 配置

### 2. FFmpeg 合成 (stream_converter.py)

```python
async def convert_and_merge(
    self,
    video_url: str,
    audio_url: Optional[str],
    output_dir: str,
    filename: Optional[str] = None,
    timeout: int = 900
) -> str:
    """合成视频和音频流"""
    
    cmd = [
        'ffmpeg',
        '-y',
        '-hide_banner',
        '-loglevel', 'info',  # 显示进度
        '-stats',             # 显示编码进度
        
        # 重连选项
        '-reconnect', '1',
        '-reconnect_streamed', '1',
        '-reconnect_delay_max', '5',
        '-timeout', '30000000',  # 30秒超时
        
        '-i', video_url,
        '-i', audio_url,
        
        '-c', 'copy',  # 不重新编码，直接复制
        '-bsf:a', 'aac_adtstoasc',
        '-movflags', '+faststart',
        '-map', '0:v:0',  # 映射视频流
        '-map', '1:a:0',  # 映射音频流
        
        output_file
    ]
    
    # 设置代理环境变量
    env = os.environ.copy()
    if settings.http_proxy:
        env['http_proxy'] = settings.http_proxy
        env['https_proxy'] = settings.http_proxy
```

关键参数：
- `-loglevel info -stats`: 显示下载进度
- `-timeout 30000000`: 30秒连接超时，防止卡死
- `-c copy`: 直接复制流，不重新编码（速度快）
- `-map 0:v:0 -map 1:a:0`: 正确映射视频和音频流

### 3. OSS 上传 (storage.py)

```python
class OSSStorage:
    def _disable_proxy_env(self) -> dict:
        """临时禁用代理环境变量"""
        saved = {}
        for key in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY']:
            if key in os.environ:
                saved[key] = os.environ.pop(key)
        return saved
    
    def _restore_proxy_env(self, saved: dict):
        """恢复代理环境变量"""
        for key, value in saved.items():
            os.environ[key] = value
    
    async def upload_file(self, local_path: str, object_key: str) -> str:
        def do_upload():
            # 上传前禁用代理
            saved_proxy = self._disable_proxy_env()
            try:
                with open(local_path, 'rb') as f:
                    result = self.bucket.put_object(object_key, f)
                return result
            finally:
                # 上传后恢复代理
                self._restore_proxy_env(saved_proxy)
        
        result = await loop.run_in_executor(None, do_upload)
        return self.get_public_url(object_key)
    
    def get_public_url(self, object_key: str) -> str:
        """生成公共访问 URL (bucket 需要公共读权限)"""
        return f"https://{self.bucket_name}.{self.endpoint}/{object_key}"
```

关键点：
- 上传时 **必须禁用代理**，否则连接新加坡 OSS 会失败
- Bucket 设置为公共读后，直接返回简单 URL，无需签名

## 测试结果

### 1080p 视频下载测试

```
Video: 1080p mp4 avc1.640028
Audio: m4a mp4a.40.2
Downloading and merging...

FFmpeg 进度:
frame=  xxx fps=xx time=00:01:23.45 bitrate=xxxx kbps speed=x.xx

下载完成:
- 分辨率: 1920x1080
- 文件大小: 43.01 MB
- 下载耗时: 161.90s
- 上传耗时: 16.19s (2.66 MB/s)

OSS URL: https://youtube-download-sg.oss-ap-southeast-1.aliyuncs.com/videos/test_1080p_xxx/xxx_1080p.mp4
```

## 常见问题

### 1. FFmpeg 下载很慢/卡住

**原因**: 代理不稳定或未使用全局模式

**解决**: 
- ClashX 切换到 **全局模式**
- 确保代理 IP 稳定

### 2. 403 Forbidden 错误

**原因**: URL 提取和下载时的代理 IP 不一致

**解决**:
- 使用全局代理模式
- 确保整个流程使用同一代理

### 3. OSS 上传失败

**原因**: 代理干扰了 OSS 连接

**解决**:
- 上传时禁用代理环境变量
- 确认 Bucket 区域配置正确

### 4. 看不到下载进度

**原因**: FFmpeg 默认 `-loglevel warning` 不显示进度

**解决**:
- 使用 `-loglevel info -stats`

## 依赖服务

| 服务 | 端口 | 用途 |
|------|------|------|
| Backend API | 8000 | FastAPI 后端 |
| Frontend | 5173 | Vite 开发服务器 |
| bgutil PO Token | 4416 | YouTube 反爬 Token |
| ClashX Proxy | 7890 | HTTP 代理 |

## 启动命令

```bash
# 1. 启动 PO Token Provider
cd backend/bgutil-ytdlp-pot-provider/server
node build/main.js

# 2. 启动后端
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000

# 3. 启动前端
cd frontend
npm run dev
```

## 文件路径

- URL 提取: `backend/app/services/url_extractor.py`
- FFmpeg 合成: `backend/app/services/stream_converter.py`
- OSS 存储: `backend/app/services/storage.py`
- 环境配置: `backend/.env`

---

**最后更新**: 2026-01-20
