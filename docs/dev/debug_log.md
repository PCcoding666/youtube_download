# YouTube Video Downloader - Debug Log

## Overview
This document records the debugging process for YouTube video download failures and the implementation of AgentGo fallback mechanism.

---

## Issue 1: Initial Download Failure - "Failed to extract any player response"

### 🔴 Problem Description
**Time**: 2025-12-16 08:22:11  
**Error Message**: 
```
ERROR: [youtube] CwHD6Fg-Mjs: Failed to extract any player response
please report this issue on https://github.com/yt-dlp/yt-dlp/issues?q=
Confirm you are on the latest version using yt-dlp -U
```

**Symptoms**:
- All download strategies (1-4) failed
- Proxy node switching didn't help
- Error occurred across different proxy nodes (US, Philippines)

### 🔍 Root Cause
**Outdated yt-dlp version** (2024.10.7)
- YouTube frequently updates its API
- Old yt-dlp versions cannot parse new player response formats

### ✅ Solution
Update yt-dlp to always use the latest version:

**File**: `/backend/requirements.txt`
```diff
# Before
- yt-dlp>=2024.10.7

# After
+ yt-dlp  # Always use latest for YouTube compatibility
```

**Commands**:
```bash
docker-compose up -d --build backend
docker exec yt-transcriber-backend yt-dlp --version  # Verify: 2025.12.08
```

### 📊 Result
✅ yt-dlp updated from 2024.10.7 to 2025.12.08

---

## Issue 2: Lack of Detailed Logs

### 🔴 Problem Description
**Symptoms**:
- Download appeared to "hang" with no progress
- No error details in logs
- Difficult to diagnose actual problems

### 🔍 Root Cause
yt-dlp configuration had `quiet: True` and `no_warnings: True`, suppressing all output including errors.

### ✅ Solution
Enable detailed logging and progress tracking:

**File**: `/backend/app/services/downloader.py`
```python
# Before
'quiet': True,
'no_warnings': True,

# After
'quiet': False,  # Enable output for debugging
'no_warnings': False,  # Show warnings
'progress_hooks': [self._progress_hook],  # Track download progress
'logger': logger,  # Use our logger
```

Add progress hook method:
```python
def _progress_hook(self, d: Dict[str, Any]) -> None:
    """Progress hook for yt-dlp to track download status."""
    if d['status'] == 'downloading':
        percent = d.get('_percent_str', '0%')
        speed = d.get('_speed_str', 'N/A')
        logger.info(f"Downloading: {percent} at {speed}")
    elif d['status'] == 'finished':
        logger.info("Download completed, now post-processing...")
    elif d['status'] == 'error':
        logger.error(f"Download error: {d.get('error', 'Unknown error')}")
```

### 📊 Result
✅ Real-time download progress visible
✅ Error messages properly logged
✅ Easier debugging and troubleshooting

---

## Issue 3: AgentGo Integration & API Endpoint Errors

### 🔴 Problem Description
**Time**: 2025-12-16 16:56:44  
**Error Message**:
```
AgentGo API error: 404 - {"message":"Cannot POST /v1/browser/session"}
```

**Context**:
- Bot detection triggered: "Sign in to confirm you're not a bot"
- AgentGo fallback attempted but failed with 404 error

### 🔍 Root Cause
Incorrect AgentGo API endpoints used in initial implementation.

### ✅ Solution
Update all AgentGo API endpoints to match actual API specification:

**File**: `/backend/app/services/agentgo_service.py`

| Old Endpoint | New Endpoint | Purpose |
|-------------|-------------|---------|
| `/v1/browser/session` | `/browser/start` | Create browser session |
| `/v1/browser/task/run` | `/browser/{session_id}/execute` | Execute login script |
| `/v1/browser/session/{id}/cookies` | `/browser/{session_id}/cookies` | Get cookies |
| `/v1/browser/session/{id}/close` | `/browser/{session_id}/close` | Close session |

**Key Changes**:
```python
# Create session
response = await self._make_request(
    endpoint="/browser/start",
    data={
        "browserType": "chrome",
        "headless": False,  # AgentGo requires visible browser for login
        "options": {
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage"
            ]
        }
    }
)

# Execute login script
login_script = f"""
await page.goto('https://accounts.google.com/ServiceLogin?service=youtube');
await page.waitForTimeout(2000);
await page.type('input[type="email"]', '{self.youtube_email}');
await page.click('#identifierNext');
await page.waitForTimeout(3000);
await page.type('input[type="password"]', '{self.youtube_password}');
await page.click('#passwordNext');
await page.waitForTimeout(5000);
await page.goto('https://www.youtube.com');
"""
```

### 📊 Environment Configuration
**Required in `/backend/.env`** or **project root `/.env`**:
```bash
AGENTGO_API_KEY=your_api_key_here
AGENTGO_API_URL=https://api.datasea.network
YOUTUBE_EMAIL=your_youtube_email
YOUTUBE_PASSWORD=your_youtube_password
```

**Docker Compose**: Must pass environment variables to container
```yaml
# docker-compose.yml
services:
  backend:
    environment:
      - AGENTGO_API_KEY=${AGENTGO_API_KEY}
      - AGENTGO_API_URL=${AGENTGO_API_URL:-https://api.datasea.network}
      - YOUTUBE_EMAIL=${YOUTUBE_EMAIL}
      - YOUTUBE_PASSWORD=${YOUTUBE_PASSWORD}
```

---

## Issue 4: Bot Detection Not Triggering AgentGo Fallback

### 🔴 Problem Description
Error "Failed to extract any player response" was not recognized as bot detection, preventing AgentGo fallback from activating.

### 🔍 Root Cause
Bot detection error pattern not included in `is_bot_detection_error()` function.

### ✅ Solution
Add more bot detection error patterns:

**File**: `/backend/app/services/downloader.py`
```python
def is_bot_detection_error(error_msg: str) -> bool:
    """Check if error message indicates YouTube bot detection."""
    bot_keywords = [
        'sign in to confirm',
        'not a bot',
        'confirm you\'re not a bot',
        'verify you are human',
        'captcha',
        'unusual traffic',
        'automated queries',
        'too many requests',
        'rate limit exceeded',
        'please try again later',
        'failed to extract any player response',  # NEW: YouTube API blocked
        'unable to extract',  # NEW
        'sign in to confirm your age'  # NEW
    ]
    error_lower = error_msg.lower()
    return any(keyword in error_lower for keyword in bot_keywords)
```

### 📊 Result
✅ More error patterns detected as bot issues
✅ AgentGo fallback properly triggered

---

## Issue 5: Proxy Node IP Blocking by YouTube

### 🔴 Problem Description
**Time**: 2025-12-16 17:03:33  
**Error Message**:
```
ERROR: unable to download video data: HTTP Error 403: Forbidden
```

**Symptoms**:
- Terminal test (no proxy): ✅ Success
- Frontend test (with Vietnam proxy): ❌ 403 Forbidden
- Node switching (Korea, Philippines): ❌ Still 403 Forbidden
- Different videos: ❌ All failed with proxy

### 🔍 Root Cause Analysis

#### Test Results Comparison

| Test Method | Proxy | Video ID | Result | Notes |
|------------|-------|----------|--------|-------|
| Terminal | Vietnam IEPL | 9GZz8cA4znI | ✅ Success | First attempt, clean IP |
| Frontend | Vietnam IEPL | 9GZz8cA4znI | ❌ Failed | 68 seconds later, bot detection |
| Frontend | Vietnam IEPL | TOmDbuXg5Qs | ❌ 403 | Different video still failed |
| Terminal | None | TOmDbuXg5Qs | ✅ Success | Direct connection works |
| All tests | Any proxy node | Any video | ❌ 403 | All proxy IPs blocked |

#### Why Terminal Succeeded But Frontend Failed?

**It's NOT terminal vs frontend difference**, it's **timing and frequency**:

1. **First Request** (Terminal, 16:54:56): ✅ Success
   - Clean IP, no previous requests
   - No rate limiting triggered
   
2. **Second Request** (Frontend, 16:56:04): ❌ Failed
   - Same IP, same video
   - Only 68 seconds after first request
   - YouTube detected: `same IP + same video + short interval = Bot`

3. **Third Request** (Frontend, 16:56:39): ❌ Failed
   - IP already flagged
   - Bot detection active

#### YouTube's Anti-Bot Detection Logic
```
IF (same_ip AND same_video AND short_time_interval)
  THEN flag_as_bot
  
IF (proxy_ip_in_blacklist)
  THEN return_403_forbidden
```

### 🔍 Verification Tests

**Test 1: Check if proxy can reach YouTube**
```bash
curl -x http://127.0.0.1:33210 -I https://www.youtube.com --max-time 10
# Result: Connection established, then timeout
```

**Test 2: Direct download without proxy**
```bash
yt-dlp -f 'best[height<=720]' 'https://www.youtube.com/watch?v=TOmDbuXg5Qs' -o '/tmp/test_%(id)s.%(ext)s'
# Result: ✅ Success - 11MB downloaded
```

**Test 3: Download with proxy**
```bash
# Using Vietnam IEPL node
# Result: ❌ HTTP Error 403: Forbidden

# Using Korea IEPL node  
# Result: ❌ HTTP Error 403: Forbidden

# Using Philippines IEPL node
# Result: ❌ HTTP Error 403: Forbidden
```

### ✅ Solution

#### Temporary Fix: Disable Proxy
**File**: `/backend/.env`
```bash
# Comment out proxy to use direct connection
# YOUTUBE_PROXY=http://127.0.0.1:33210  # Temporarily disabled - proxy IPs blocked
```

**Restart backend**:
```bash
# Docker
docker-compose restart backend

# Local development
# Server will auto-reload when .env changes detected
```

#### Long-term Solutions

1. **Contact Proxy Provider**
   - Request fresh IPs or different node pools
   - SakuraCat: Try different region nodes
   - Consider residential proxies instead of datacenter IPs

2. **Implement Rate Limiting**
   - Add delays between requests
   - Cache successful downloads
   - Implement request throttling per IP

3. **Use AgentGo Cookie Authentication**
   - Get authenticated cookies via browser automation
   - Bypass bot detection with valid session
   - Requires proper YouTube credentials

4. **Rotate Through Multiple Proxy Services**
   - Don't rely on single proxy provider
   - Distribute requests across multiple IPs
   - Implement proxy health checking

---

## Issue 6: Local vs Docker Environment Differences

### 🔴 Problem Description
Environment variables configured in `/backend/.env` not working in Docker container.

### 🔍 Root Cause
Docker Compose reads `.env` from project root, not from `backend/` subdirectory.

### ✅ Solution

**Option 1: Create root `.env` file** (Recommended)
```bash
# Project root: /youtube_download/.env
AGENTGO_API_KEY=your_key
AGENTGO_API_URL=https://api.datasea.network
YOUTUBE_EMAIL=your_email
YOUTUBE_PASSWORD=your_password
```

**Option 2: Specify env_file in docker-compose.yml**
```yaml
services:
  backend:
    env_file:
      - ./backend/.env
```

### 📊 Verification
```bash
# Check if env vars loaded in container
docker exec yt-transcriber-backend env | grep -E "(YOUTUBE_EMAIL|AGENTGO_API_KEY)" | sed 's/=.*/=***/'

# Should show:
# AGENTGO_API_KEY=***
# YOUTUBE_EMAIL=***
```

---

## Lessons Learned

### 1. **Always Use Latest yt-dlp**
- YouTube API changes frequently
- Remove version constraints: `yt-dlp` instead of `yt-dlp>=2024.10.7`
- Rebuild containers after updates

### 2. **Enable Detailed Logging Early**
- Don't suppress logs in development
- Use progress hooks for visibility
- Log both successes and failures

### 3. **Understand Proxy IP Reputation**
- Datacenter IPs easily flagged by YouTube
- Test proxies before production deployment
- Monitor proxy health and rotation
- Consider residential proxies for YouTube

### 4. **YouTube's Rate Limiting is Aggressive**
- Same IP + Same video + Short interval = Ban
- Wait 5-10 minutes between retries
- Test with different videos to avoid detection
- Implement request throttling

### 5. **Bot Detection Patterns Evolve**
- Regularly update detection patterns
- Monitor yt-dlp community for new error messages
- Implement fallback mechanisms (AgentGo)

### 6. **Environment Variable Management**
- Docker Compose reads from project root `.env`
- Backend code reads from `backend/.env`
- Keep them in sync or use single source
- Document required variables clearly

### 7. **API Integration Best Practices**
- Always verify API endpoints with documentation
- Test API calls independently before integration
- Handle API errors gracefully
- Log API responses for debugging

---

## Testing Checklist

### Before Deployment
- [ ] yt-dlp version is latest
- [ ] Detailed logging enabled
- [ ] Proxy health check passes
- [ ] Environment variables configured
- [ ] Bot detection patterns updated
- [ ] AgentGo fallback configured (if needed)
- [ ] Test with multiple videos
- [ ] Test with and without proxy
- [ ] Verify rate limiting works

### During Operation
- [ ] Monitor download success rate
- [ ] Track proxy IP bans
- [ ] Watch for new error patterns
- [ ] Check yt-dlp version weekly
- [ ] Review logs for anomalies

---

## Quick Reference Commands

### Docker Operations
```bash
# View logs
docker logs yt-transcriber-backend --tail 100 -f

# Restart backend
docker-compose restart backend

# Rebuild after code changes
docker-compose up -d --build backend

# Check environment variables
docker exec yt-transcriber-backend env | grep YOUTUBE
```

### Local Development
```bash
# Start backend
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Check yt-dlp version
yt-dlp --version

# Test download without proxy
yt-dlp -f 'best[height<=720]' 'VIDEO_URL' -o '/tmp/test.mp4'
```

### Debugging
```bash
# Test proxy connectivity
curl -x http://127.0.0.1:33210 -I https://www.youtube.com --max-time 5

# Check if IP is blocked
yt-dlp --proxy http://127.0.0.1:33210 -F 'VIDEO_URL'

# Test direct connection
yt-dlp -F 'VIDEO_URL'
```

---

## Related Files

### Core Implementation
- `/backend/app/services/downloader.py` - Main download logic
- `/backend/app/services/agentgo_service.py` - AgentGo integration
- `/backend/app/config.py` - Configuration management
- `/backend/requirements.txt` - Python dependencies

### Configuration
- `/docker-compose.yml` - Container orchestration
- `/.env` - Root environment variables
- `/backend/.env` - Backend environment variables
- `/backend/.env.example` - Environment template

### Frontend
- `/frontend/.env` - Frontend API endpoint configuration

---

## Version History

| Date | Version | Changes |
|------|---------|---------|
| 2025-12-16 | 1.0.0 | Initial debug log creation |
| 2025-12-16 | 1.1.0 | Added proxy IP blocking analysis |
| 2025-12-16 | 1.2.0 | Added AgentGo integration details |

---

## Additional Resources

- [yt-dlp GitHub](https://github.com/yt-dlp/yt-dlp)
- [yt-dlp FAQ](https://github.com/yt-dlp/yt-dlp/wiki/FAQ)
- [yt-dlp Cookie Guide](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp)
- [AgentGo Documentation](https://datasea.network/)

---

**Document Author**: Debug session 2025-12-16  
**Last Updated**: 2025-12-16 17:10:00  
**Status**: Active - Proxy issues ongoing
