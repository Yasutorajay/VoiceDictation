from __future__ import annotations

BRAND_NAME = "RanLiAiJay"
APP_VERSION = "2.0"
BRAND_CN = "燃力AiJay"
ATTRIBUTION = f"{BRAND_CN} 提供技术支持"
OFFICIAL_ACCOUNT_NAME = "燃砺Ai百宝库"
COPYRIGHT_NOTICE = (
    "本软件由 RanLiAiJay 自主设计并借助 AI 工具研发。"
    "RanLiAiJay 对自有代码、品牌与产品方案保留商用权利；未经授权，第三方不得复制、改名、"
    "移除署名或用于商业分发。"
    "第三方开源组件和模型依各自许可证执行。"
)


def attribution_text() -> str:
    return ATTRIBUTION


def official_download_text() -> str:
    return (
        f"微信搜索公众号「{OFFICIAL_ACCOUNT_NAME}」领取官方下载包。\n\n"
        f"{COPYRIGHT_NOTICE}"
    )
