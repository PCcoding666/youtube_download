# YouTube Video Downloader Skill

A pay-per-use YouTube video download service. Authenticate with API Key, pay with credits.

## Authentication

All API calls require an API Key in the Authorization header:

```
Authorization: Bearer sk-yt-xxxxx
```

Get your API Key at: https://u2foru.site/?page=apikeys

## Credits

- **Rate**: S$1 SGD = 5 Credits
- **Cost**: 1 credit per successful download
- **Failed downloads**: No charge
- **Expiry**: Credits never expire
- **Min recharge**: S$1 (suggested S$10), custom integer amount
- **Recharge**: https://u2foru.site/?page=pricing

## Endpoints

### POST /api/v1/skill/download

Download a YouTube video.

**Request:**
```json
{
  "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "resolution": "720"
}
```

**Parameters:**
- `youtube_url` (required): YouTube video URL
- `resolution` (optional): "360", "480", "720", "1080", "best", "audio". Default: "720"

**Response (success):**
```json
{
  "success": true,
  "download_url": "https://oss-bucket.aliyuncs.com/skill/abc123/video.mp4",
  "video_title": "Video Title",
  "video_duration": 212,
  "file_size": 52428800,
  "resolution": "720",
  "credits_used": 1,
  "credits_remaining": 24,
  "processing_time": 45.2
}
```

**Response (insufficient credits):**
```json
{
  "success": false,
  "credits_remaining": 0,
  "error_message": "Credit insufficient (current: 0). Please recharge at the website."
}
```

### GET /api/v1/skill/balance

Check credit balance.

**Response:**
```json
{
  "credit_balance": 25,
  "username": "user123"
}
```

### GET /api/v1/skill/health

Health check (no authentication required).

**Response:**
```json
{
  "status": "healthy",
  "service": "YouTube Video Downloader Skill",
  "version": "1.0.0",
  "credit_rate": "1 download = 1 credit, S$1 = 5 credits"
}
```

## Error Codes

| Code | Meaning |
|------|---------|
| 200  | Success |
| 401  | Invalid or missing API Key |
| 402  | Insufficient credits |
| 400  | Invalid request (bad URL, etc.) |
| 500  | Server error (no credits charged) |

## Example (curl)

```bash
# Download a video
curl -X POST https://u2foru.site/api/v1/skill/download \
  -H "Authorization: Bearer sk-yt-xxxxx" \
  -H "Content-Type: application/json" \
  -d '{"youtube_url": "https://youtube.com/watch?v=dQw4w9WgXcQ", "resolution": "720"}'

# Check balance
curl https://u2foru.site/api/v1/skill/balance \
  -H "Authorization: Bearer sk-yt-xxxxx"
```

## Example (Python)

```python
import requests

API_KEY = "sk-yt-xxxxx"
BASE_URL = "https://u2foru.site"

# Download
resp = requests.post(
    f"{BASE_URL}/api/v1/skill/download",
    headers={"Authorization": f"Bearer {API_KEY}"},
    json={"youtube_url": "https://youtube.com/watch?v=dQw4w9WgXcQ", "resolution": "720"}
)
data = resp.json()
if data["success"]:
    print(f"Download URL: {data['download_url']}")
    print(f"Credits remaining: {data['credits_remaining']}")
```
