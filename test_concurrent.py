#!/usr/bin/env python3
"""
YouTube Download Service - 并发测试脚本
测试 AgentGo 端点的并发极限
"""

import asyncio
import aiohttp
import time
import json
import argparse
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime

# 测试用的 YouTube 视频 URL 列表（短视频，提取速度快）
TEST_VIDEOS = [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # Rick Astley
    "https://www.youtube.com/watch?v=9bZkp7q19f0",  # Gangnam Style
    "https://www.youtube.com/watch?v=kJQP7kiw5Fk",  # Despacito
    "https://www.youtube.com/watch?v=JGwWNGJdvx8",  # Ed Sheeran
    "https://www.youtube.com/watch?v=RgKAFK5djSk",  # Wiz Khalifa
    "https://www.youtube.com/watch?v=OPf0YbXqDm0",  # Mark Ronson
    "https://www.youtube.com/watch?v=CevxZvSJLk8",  # Katy Perry
    "https://www.youtube.com/watch?v=e-ORhEE9VVg",  # Taylor Swift
    "https://www.youtube.com/watch?v=hT_nvWreIhg",  # OneRepublic
    "https://www.youtube.com/watch?v=YQHsXMglC9A",  # Adele
]

@dataclass
class TestResult:
    """单次请求的测试结果"""
    video_url: str
    success: bool
    duration: float
    error_message: Optional[str] = None
    video_title: Optional[str] = None
    method: Optional[str] = None

@dataclass
class ConcurrencyTestResult:
    """并发测试的汇总结果"""
    concurrency: int
    total_requests: int
    successful: int
    failed: int
    total_time: float
    avg_time: float
    min_time: float
    max_time: float
    requests_per_second: float
    results: List[TestResult]

async def extract_video(
    session: aiohttp.ClientSession,
    base_url: str,
    video_url: str,
    endpoint: str = "/api/v1/extract/agentgo",
    resolution: str = "720"
) -> TestResult:
    """发送单个提取请求"""
    start_time = time.time()
    
    payload = {
        "youtube_url": video_url,
        "resolution": resolution
    }
    
    try:
        async with session.post(
            f"{base_url}{endpoint}",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=300)  # 5分钟超时
        ) as response:
            duration = time.time() - start_time
            data = await response.json()
            
            if data.get("success"):
                return TestResult(
                    video_url=video_url,
                    success=True,
                    duration=duration,
                    video_title=data.get("video_info", {}).get("title"),
                    method=data.get("method", "unknown")
                )
            else:
                return TestResult(
                    video_url=video_url,
                    success=False,
                    duration=duration,
                    error_message=data.get("error_message", "Unknown error")
                )
    except asyncio.TimeoutError:
        return TestResult(
            video_url=video_url,
            success=False,
            duration=time.time() - start_time,
            error_message="Request timed out (300s)"
        )
    except Exception as e:
        return TestResult(
            video_url=video_url,
            success=False,
            duration=time.time() - start_time,
            error_message=str(e)
        )

async def run_concurrency_test(
    base_url: str,
    concurrency: int,
    endpoint: str,
    total_requests: Optional[int] = None
) -> ConcurrencyTestResult:
    """运行指定并发数的测试"""
    
    # 默认请求数 = 并发数
    if total_requests is None:
        total_requests = concurrency
    
    print(f"\n{'='*60}")
    print(f"🚀 开始测试: 并发数={concurrency}, 总请求数={total_requests}")
    print(f"   端点: {endpoint}")
    print(f"{'='*60}")
    
    # 准备任务列表
    video_urls = []
    for i in range(total_requests):
        video_urls.append(TEST_VIDEOS[i % len(TEST_VIDEOS)])
    
    start_time = time.time()
    
    # 使用连接池
    connector = aiohttp.TCPConnector(limit=concurrency)
    async with aiohttp.ClientSession(connector=connector) as session:
        # 创建所有任务
        tasks = [
            extract_video(session, base_url, url, endpoint)
            for url in video_urls
        ]
        
        # 并发执行
        results = await asyncio.gather(*tasks)
    
    total_time = time.time() - start_time
    
    # 统计结果
    successful = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)
    durations = [r.duration for r in results]
    
    test_result = ConcurrencyTestResult(
        concurrency=concurrency,
        total_requests=total_requests,
        successful=successful,
        failed=failed,
        total_time=total_time,
        avg_time=sum(durations) / len(durations) if durations else 0,
        min_time=min(durations) if durations else 0,
        max_time=max(durations) if durations else 0,
        requests_per_second=total_requests / total_time if total_time > 0 else 0,
        results=results
    )
    
    # 打印结果
    print(f"\n📊 测试结果 (并发数={concurrency}):")
    print(f"   ✅ 成功: {successful}/{total_requests}")
    print(f"   ❌ 失败: {failed}/{total_requests}")
    print(f"   ⏱️  总耗时: {total_time:.2f}s")
    print(f"   📈 平均响应时间: {test_result.avg_time:.2f}s")
    print(f"   🔻 最短响应时间: {test_result.min_time:.2f}s")
    print(f"   🔺 最长响应时间: {test_result.max_time:.2f}s")
    print(f"   🚄 吞吐量: {test_result.requests_per_second:.2f} req/s")
    
    # 打印失败详情
    if failed > 0:
        print(f"\n   ❌ 失败详情:")
        for r in results:
            if not r.success:
                print(f"      - {r.video_url[:50]}...")
                print(f"        错误: {r.error_message}")
    
    return test_result

async def progressive_test(
    base_url: str,
    endpoint: str,
    start_concurrency: int = 1,
    max_concurrency: int = 20,
    step: int = 2
):
    """渐进式并发测试，找到极限"""
    
    print("\n" + "="*70)
    print("🔬 渐进式并发测试 - 寻找 AgentGo 并发极限")
    print("="*70)
    print(f"起始并发: {start_concurrency}")
    print(f"最大并发: {max_concurrency}")
    print(f"步进: {step}")
    print(f"端点: {endpoint}")
    print(f"测试 URL: {base_url}")
    print("="*70)
    
    all_results = []
    
    concurrency = start_concurrency
    while concurrency <= max_concurrency:
        result = await run_concurrency_test(
            base_url=base_url,
            concurrency=concurrency,
            endpoint=endpoint,
            total_requests=concurrency  # 每轮测试数 = 并发数
        )
        all_results.append(result)
        
        # 如果失败率超过 50%，停止测试
        failure_rate = result.failed / result.total_requests if result.total_requests > 0 else 0
        if failure_rate > 0.5:
            print(f"\n⚠️  失败率 {failure_rate*100:.1f}% 超过 50%，停止测试")
            break
        
        concurrency += step
        
        # 等待一下，让服务恢复
        if concurrency <= max_concurrency:
            print(f"\n⏳ 等待 5 秒后进行下一轮测试...")
            await asyncio.sleep(5)
    
    # 打印汇总报告
    print("\n" + "="*70)
    print("📋 并发测试汇总报告")
    print("="*70)
    print(f"{'并发数':^8} | {'成功':^6} | {'失败':^6} | {'成功率':^8} | {'平均响应':^10} | {'吞吐量':^10}")
    print("-"*70)
    
    for r in all_results:
        success_rate = r.successful / r.total_requests * 100 if r.total_requests > 0 else 0
        print(f"{r.concurrency:^8} | {r.successful:^6} | {r.failed:^6} | {success_rate:^7.1f}% | {r.avg_time:^9.2f}s | {r.requests_per_second:^9.2f}/s")
    
    # 找出最佳并发数
    best_result = max(all_results, key=lambda r: r.requests_per_second if r.failed == 0 else 0)
    print("-"*70)
    print(f"\n🏆 推荐并发数: {best_result.concurrency}")
    print(f"   (在无失败情况下，吞吐量最高: {best_result.requests_per_second:.2f} req/s)")
    
    return all_results

async def main():
    parser = argparse.ArgumentParser(description="YouTube Download 并发测试")
    parser.add_argument(
        "--url",
        default="https://u2foru.site",
        help="API 基础 URL (默认: https://u2foru.site)"
    )
    parser.add_argument(
        "--endpoint",
        default="/api/v1/extract/agentgo",
        choices=["/api/v1/extract/agentgo", "/api/v1/extract/direct"],
        help="测试端点 (默认: /api/v1/extract/agentgo)"
    )
    parser.add_argument(
        "--mode",
        default="progressive",
        choices=["progressive", "single"],
        help="测试模式: progressive=渐进测试, single=单次测试"
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="单次测试的并发数 (默认: 5)"
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=20,
        help="渐进测试的最大并发数 (默认: 20)"
    )
    parser.add_argument(
        "--step",
        type=int,
        default=2,
        help="渐进测试的步进 (默认: 2)"
    )
    
    args = parser.parse_args()
    
    print(f"\n🎬 YouTube Download Service - 并发测试")
    print(f"   时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 先测试 API 是否可用
    print(f"\n📡 测试 API 连接: {args.url}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{args.url}/api/v1/health", timeout=aiohttp.ClientTimeout(total=10)) as response:
                data = await response.json()
                if data.get("status") == "healthy":
                    print("   ✅ API 健康")
                else:
                    print(f"   ⚠️ API 状态: {data}")
    except Exception as e:
        print(f"   ❌ API 连接失败: {e}")
        return
    
    if args.mode == "progressive":
        await progressive_test(
            base_url=args.url,
            endpoint=args.endpoint,
            start_concurrency=1,
            max_concurrency=args.max_concurrency,
            step=args.step
        )
    else:
        await run_concurrency_test(
            base_url=args.url,
            concurrency=args.concurrency,
            endpoint=args.endpoint,
            total_requests=args.concurrency
        )

if __name__ == "__main__":
    asyncio.run(main())
