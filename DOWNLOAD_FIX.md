# YouTube 下载问题修复说明

## 问题描述
用户点击下载链接后，浏览器会打开视频播放器而不是下载文件。

## 原因分析
Google Video 的直链返回的 Content-Type 是 `video/mp4`，浏览器会自动播放而不是下载。由于跨域限制（CORS），前端无法直接设置 `download` 属性来强制下载。

## 解决方案
通过后端代理下载，设置正确的 `Content-Disposition` 响应头来强制浏览器下载。

## 修改内容

### 1. 后端修改 (`backend/app/api/routes.py`)
添加了新的代理下载端点：

```python
@router.get("/proxy-download")
async def proxy_download(url: str, filename: str = "video.mp4"):
    """
    代理下载 Google Video URL
    - 从 Google 服务器流式传输视频
    - 设置 Content-Disposition 头强制下载
    - 支持大文件流式传输
    """
```

**特性：**
- 流式传输，不占用服务器内存
- 自动设置正确的文件名
- 安全验证（仅允许 googlevideo.com 域名）
- 支持超时处理

### 2. 前端修改 (`frontend/src/App.tsx`)

**添加下载函数：**
```typescript
const handleDownload = (url: string, filename: string) => {
  const apiBaseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
  const proxyUrl = `${apiBaseUrl}/api/v1/proxy-download?${new URLSearchParams({
    url: url,
    filename: filename
  })}`;
  window.open(proxyUrl, '_blank');
};
```

**更新下载按钮：**
- 从 `<a>` 标签改为 `<button>`
- 使用 `handleDownload` 函数
- 自动生成正确的文件名（包含视频标题和扩展名）

## 使用方式

1. 用户输入 YouTube URL 并选择分辨率
2. 点击"Extract"按钮获取下载链接
3. 点击"Download"按钮
4. 浏览器会打开新标签页并自动开始下载

## 优势

✅ **强制下载**：浏览器不会播放，直接下载  
✅ **正确文件名**：使用视频标题作为文件名  
✅ **流式传输**：不占用服务器内存，支持大文件  
✅ **安全性**：仅允许 googlevideo.com 域名  
✅ **用户体验**：一键下载，无需右键另存为  

## 注意事项

- 下载流量会经过你的服务器（消耗带宽）
- 如果需要节省带宽，可以保留"Copy URL"功能，让用户使用下载工具
- 确保服务器有足够的带宽处理大文件下载

## 测试

1. 启动后端：`cd backend && uvicorn app.main:app --reload`
2. 启动前端：`cd frontend && npm run dev`
3. 访问前端页面
4. 输入 YouTube URL 并测试下载功能
