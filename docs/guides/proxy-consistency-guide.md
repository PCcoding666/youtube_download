# AgentGo 和 yt-dlp IP 一致性配置指南

## 问题描述

当 AgentGo 获取 YouTube 认证 Token 时使用的 IP 地址与 yt-dlp 下载时使用的 IP 地址不一致时，YouTube 可能会返回 403 错误，因为它检测到认证信息与请求来源不匹配。

## 解决方案

### 1. 查看 AgentGo 的 IP 信息

系统现在会自动获取并显示 AgentGo 浏览器的 IP 信息：

```
🌐 AgentGo browser IP: 1.2.3.4 (US)
⚠️  PROXY CONSISTENCY: For optimal success rate, ensure yt-dlp uses the same IP as AgentGo.
```

### 2. 配置代理以匹配 AgentGo IP

#### 方法 A: 使用相同区域的代理服务

1. **确定 AgentGo 区域**：查看日志中的 `Region: us` 信息
2. **配置代理**：在 `.env` 文件中设置代理：

```bash
# 示例：使用美国区域的代理
YOUTUBE_PROXY_LIST=http://us-proxy1.example.com:8080,http://us-proxy2.example.com:8080

# 或者使用 SOCKS5 代理
YOUTUBE_PROXY_LIST=socks5://us-proxy.example.com:1080
```

#### 方法 B: 使用 VPN 确保相同 IP

1. 连接到与 AgentGo 相同区域的 VPN
2. 确保 VPN 覆盖整个系统网络
3. 重启服务以使用新的网络环境

### 3. 验证 IP 一致性

系统会自动检查 IP 一致性：

```
✅ IP consistency check passed: 1.2.3.4
```

或者：

```
❌ IP MISMATCH DETECTED! Current IP: 5.6.7.8, AgentGo IP: 1.2.3.4
```

### 4. 代理配置示例

#### 环境变量配置 (.env)

```bash
# 代理列表（支持多个代理轮换）
YOUTUBE_PROXY_LIST=http://proxy1.example.com:8080,http://proxy2.example.com:8080

# 或者单个代理
YOUTUBE_PROXY_LIST=socks5://proxy.example.com:1080
```

#### 代理格式支持

- HTTP 代理：`http://proxy.example.com:8080`
- HTTPS 代理：`https://proxy.example.com:8080`
- SOCKS5 代理：`socks5://proxy.example.com:1080`
- 带认证的代理：`http://username:password@proxy.example.com:8080`

### 5. 最佳实践

1. **区域匹配**：选择与 AgentGo 区域相同的代理服务器
2. **稳定性**：使用稳定、高质量的代理服务
3. **监控**：定期检查日志中的 IP 一致性信息
4. **备用方案**：配置多个相同区域的代理作为备用

### 6. 故障排除

#### 常见问题

1. **403 Forbidden 错误**
   - 检查 IP 一致性日志
   - 确认代理配置正确
   - 尝试使用不同的代理服务器

2. **代理连接失败**
   - 验证代理服务器可用性
   - 检查代理认证信息
   - 确认网络防火墙设置

3. **IP 检测失败**
   - 检查网络连接
   - 确认可以访问 IP 检测服务
   - 查看详细错误日志

#### 调试命令

```bash
# 检查当前 IP
curl https://httpbin.org/ip

# 测试代理连接
curl --proxy http://proxy.example.com:8080 https://httpbin.org/ip
```

### 7. 高级配置

#### 动态代理选择

系统支持根据 AgentGo 区域自动选择匹配的代理：

```python
# 在代码中可以根据区域选择代理
region_proxies = {
    'us': ['http://us-proxy1.com:8080', 'http://us-proxy2.com:8080'],
    'uk': ['http://uk-proxy1.com:8080', 'http://uk-proxy2.com:8080'],
    'de': ['http://de-proxy1.com:8080', 'http://de-proxy2.com:8080']
}
```

#### 代理健康检查

系统会自动标记失败的代理并轮换到可用的代理。

## 总结

通过确保 AgentGo 和 yt-dlp 使用相同的 IP 地址或相同区域的代理，可以显著提高 YouTube 下载的成功率，减少 403 错误的发生。