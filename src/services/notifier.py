"""WeChat Enterprise Robot Notifier - sends notifications via WeChat Enterprise robots.

Provides async functions to send text messages through WeChat Enterprise
robot webhooks for status updates and alerts.
"""
import httpx
from loguru import logger


async def send_wecom_text(webhook: str, content: str) -> None:
    """Send a text message via WeChat Enterprise robot webhook.

    Sends text content through a pre-configured WeChat Enterprise webhook.
    Gracefully handles network errors and missing webhooks.

    Args:
        webhook: WeChat Enterprise robot webhook URL.
        content: Text message content to send.
    """
    if not webhook:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook, json={
                "msgtype": "text",
                "text": {"content": content}
            })
            resp.raise_for_status()
        logger.info("[WeCom] 推送成功")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[WeCom] 推送失败: {exc}")
