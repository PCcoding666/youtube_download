#!/usr/bin/env python3
"""
测试 1080p 视频下载 - 支持直接下载和 m3u8 流式下载
"""
import asyncio
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

OUTPUT_DIR = "/tmp/test_downloads"
# 找一个有 1080p 的视频
TARGET_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Rick Astley - Never Gonna Give You Up


async def test_extract_and_merge():
    """测试提取 URL 然后用 FFmpeg 下载（支持直接下载和 m3u8 流式）"""
    from app.services.url_extractor import YouTubeURLExtractor
    from app.services.agentgo_service import get_agentgo_service
    
    print("=" * 60)
    print("1080p FFmpeg 下载测试（支持 m3u8 流式）")
    print("=" * 60)
    
    # 1. 获取 AgentGo 认证
    print("\n[1] 获取 AgentGo 认证...")
    service = get_agentgo_service()
    auth_bundle = None
    if service.is_configured():
        auth_bundle = await service.get_youtube_authentication_bundle(
            force_refresh=True,
            region='us'
        )
        if auth_bundle:
            print(f"    ✅ Visitor Data: {auth_bundle.visitor_data[:30] if auth_bundle.visitor_data else 'None'}...")
            print(f"    ✅ Cookie File: {auth_bundle.cookie_file_path}")
    
    # 2. 提取视频 URL
    print(f"\n[2] 提取视频 URL: {TARGET_URL}")
    extractor = YouTubeURLExtractor(region='us', auth_bundle=auth_bundle)
    
    try:
        video = await extractor.extract(TARGET_URL)
        print(f"    ✅ 标题: {video.title}")
        print(f"    ✅ 时长: {video.duration}s")
        
        # 获取 1080p 下载 URL
        urls = video.get_download_urls(resolution="1080")
        
        video_url = urls.get('video_url')
        audio_url = urls.get('audio_url')
        is_streaming = urls.get('is_streaming', False)
        needs_merge = urls.get('needs_merge', False)
        
        print(f"\n    视频 URL: {video_url[:80] if video_url else 'None'}...")
        print(f"    音频 URL: {audio_url[:80] if audio_url else 'None'}...")
        print(f"    需要合并: {needs_merge}")
        print(f"    是流式(m3u8): {is_streaming}")
        
        if urls.get('video_format'):
            vf = urls['video_format']
            print(f"    视频格式: {vf.get('height')}p {vf.get('ext')} {vf.get('vcodec')}")
        
        if urls.get('audio_format'):
            af = urls['audio_format']
            print(f"    音频格式: {af.get('ext')} {af.get('acodec')}")
        
        if not video_url:
            print("\n    ❌ 没有获取到视频 URL")
            return False
        
    except Exception as e:
        print(f"    ❌ 提取失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 3. 用 FFmpeg 下载
    print("\n[3] FFmpeg 下载...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    start_time = time.time()
    import subprocess
    
    output_file = os.path.join(OUTPUT_DIR, f"{video.video_id}_1080p.mp4")
    proxy = os.environ.get('HTTP_PROXY', 'http://127.0.0.1:7890')
    
    # 根据是否是 m3u8 流式来构建不同的 FFmpeg 命令
    if is_streaming:
        # m3u8 流式下载 - 单个 URL 包含视频+音频
        print("    📺 模式: m3u8 流式下载")
        cmd = [
            'ffmpeg', '-y',
            '-hide_banner',
            '-loglevel', 'info',
            '-stats',
            '-http_proxy', proxy,
            # HLS 特定选项
            '-reconnect', '1',
            '-reconnect_streamed', '1',
            '-reconnect_delay_max', '5',
            '-i', video_url,
            # 输出选项
            '-c', 'copy',
            '-bsf:a', 'aac_adtstoasc',
            '-movflags', '+faststart',
            output_file
        ]
    elif needs_merge and audio_url:
        # 分离的视频+音频流 - 需要合并
        print("    📺 模式: 视频+音频分离下载并合并")
        cmd = [
            'ffmpeg', '-y',
            '-hide_banner',
            '-loglevel', 'info',
            '-stats',
            '-http_proxy', proxy,
            '-reconnect', '1',
            '-reconnect_streamed', '1',
            '-reconnect_delay_max', '5',
            '-i', video_url,
            '-reconnect', '1',
            '-reconnect_streamed', '1',
            '-reconnect_delay_max', '5',
            '-i', audio_url,
            '-c', 'copy',
            '-bsf:a', 'aac_adtstoasc',
            '-movflags', '+faststart',
            '-map', '0:v:0',
            '-map', '1:a:0',
            output_file
        ]
    else:
        # 单个 URL（可能已包含音频）
        print("    📺 模式: 单文件下载")
        cmd = [
            'ffmpeg', '-y',
            '-hide_banner',
            '-loglevel', 'info',
            '-stats',
            '-http_proxy', proxy,
            '-reconnect', '1',
            '-reconnect_streamed', '1',
            '-reconnect_delay_max', '5',
            '-i', video_url,
            '-c', 'copy',
            '-bsf:a', 'aac_adtstoasc',
            '-movflags', '+faststart',
            output_file
        ]
    
    print(f"    代理: {proxy}")
    
    # 预估大小（m3u8 流式可能没有 filesize）
    video_size = urls.get('video_format', {}).get('filesize') if urls.get('video_format') else None
    audio_size = urls.get('audio_format', {}).get('filesize') if urls.get('audio_format') else None
    if video_size:
        total_size_mb = ((video_size or 0) + (audio_size or 0)) / (1024 * 1024)
        print(f"    预估总大小: {total_size_mb:.1f} MB")
    else:
        total_size_mb = 0
        print("    预估总大小: 未知 (m3u8 流式)")
    
    # 打印调试信息
    print(f"\n    [DEBUG] FFmpeg 命令前10个参数: {cmd[:10]}")
    print(f"    [DEBUG] 视频URL: {video_url[:80]}...")
    if audio_url:
        print(f"    [DEBUG] 音频URL: {audio_url[:80]}...")
    
    print("\n    开始下载...", flush=True)
    
    env = os.environ.copy()
    env['http_proxy'] = proxy
    env['https_proxy'] = proxy
    
    try:
        print("    [DEBUG] 启动 FFmpeg...", flush=True)
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        print(f"    [DEBUG] FFmpeg PID: {process.pid}", flush=True)
        
        download_start = time.time()
        import select
        
        line_count = 0
        last_progress_time = time.time()
        
        while process.poll() is None:
            ready, _, _ = select.select([process.stderr], [], [], 0.5)
            
            if ready:
                line = process.stderr.readline()
                if line:
                    line_count += 1
                    line = line.decode('utf-8', errors='ignore').strip()
                    
                    # 显示前5行输出
                    if line_count <= 5:
                        print(f"\n    [DEBUG] 输出#{line_count}: {line[:120]}", flush=True)
                    
                    if 'size=' in line:
                        last_progress_time = time.time()
                        try:
                            size_part = line.split('size=')[1].split()[0]
                            if 'kB' in size_part:
                                current_size_kb = int(size_part.replace('kB', '').strip())
                                elapsed = time.time() - download_start
                                if elapsed > 0:
                                    avg_speed = current_size_kb / elapsed
                                    current_mb = current_size_kb / 1024
                                    if total_size_mb > 0:
                                        progress = min(100, (current_mb / total_size_mb) * 100)
                                        eta = (total_size_mb - current_mb) / (avg_speed / 1024) if avg_speed > 0 else 0
                                        print(f"\r    📊 {current_mb:.1f}/{total_size_mb:.1f} MB ({progress:.0f}%) | {avg_speed:.0f} KB/s | ETA: {eta:.0f}s   ", end='', flush=True)
                                    else:
                                        # m3u8 没有预估大小，只显示已下载和速度
                                        print(f"\r    📊 {current_mb:.1f} MB | {avg_speed:.0f} KB/s | {elapsed:.0f}s   ", end='', flush=True)
                        except Exception:
                            pass
                    elif ('error' in line.lower() and 'error=' not in line.lower()) or 'failed' in line.lower():
                        # 真正的错误，排除 FFmpeg 的 error= 统计信息
                        if '403' in line or '404' in line or 'connection' in line.lower():
                            print(f"\n    ❌ {line}")
            else:
                elapsed = time.time() - download_start
                no_progress = time.time() - last_progress_time
                if no_progress > 3:
                    print(f"\r    ⏳ 等待中... {elapsed:.0f}s (无进度: {no_progress:.0f}s)   ", end='', flush=True)
        
        _, stderr = process.communicate()
        process.wait()
        
        elapsed = time.time() - start_time
        print(f"\n    [DEBUG] FFmpeg 完成，总输出行数: {line_count}")
        
        if process.returncode == 0 and os.path.exists(output_file):
            size_mb = os.path.getsize(output_file) / (1024 * 1024)
            avg_speed = (size_mb * 1024) / elapsed if elapsed > 0 else 0
            print("\n    ✅ 下载成功!")
            print(f"    文件: {output_file}")
            print(f"    大小: {size_mb:.2f} MB")
            print(f"    耗时: {elapsed:.1f}s")
            print(f"    平均速度: {avg_speed:.0f} KB/s")
            return True
        else:
            print(f"\n    ❌ FFmpeg 返回码: {process.returncode}")
            if stderr:
                print(f"    错误信息: {stderr.decode('utf-8', errors='ignore')[-500:]}")
            return False
            
    except Exception as e:
        print(f"\n    ❌ FFmpeg 下载失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    success = await test_extract_and_merge()
    
    print("\n" + "=" * 60)
    if success:
        print("✅ 测试成功!")
    else:
        print("❌ 测试失败")
    print("=" * 60)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
