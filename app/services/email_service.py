"""邮件推送服务

用于定时分析任务完成后的邮件通知：HTML 摘要 + 可选 PDF 附件。
SMTP 发送放在线程池执行，避免阻塞事件循环。
"""
import asyncio
import logging
import smtplib
from email.message import EmailMessage
from typing import Any, Dict, List, Optional

from app.core.database import get_mongo_db
from app.utils.report_exporter import report_exporter

logger = logging.getLogger("webapi")

COLLECTION = "scheduled_analysis_email_config"
CONFIG_KEY = "global"

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": False,
    "smtp_host": "smtp.163.com",
    "smtp_port": 465,
    "sender": "",
    "auth_code": "",
    "recipients": [],
    "attach_pdf": True,
}


async def get_email_config() -> Dict[str, Any]:
    db = get_mongo_db()
    doc = await db[COLLECTION].find_one({"config_key": CONFIG_KEY})
    cfg = dict(DEFAULT_CONFIG)
    if doc:
        for k in DEFAULT_CONFIG:
            if k in doc:
                cfg[k] = doc[k]
    return cfg


async def update_email_config(data: Dict[str, Any]) -> Dict[str, Any]:
    db = get_mongo_db()
    update: Dict[str, Any] = {}
    for k in DEFAULT_CONFIG:
        if k in data and data[k] is not None:
            update[k] = data[k]
    await db[COLLECTION].update_one(
        {"config_key": CONFIG_KEY},
        {"$set": {"config_key": CONFIG_KEY, **update}},
        upsert=True,
    )
    return await get_email_config()


def _action_color(action: str) -> str:
    if "买入" in action:
        return "#16a34a"
    if "卖出" in action:
        return "#dc2626"
    return "#d97706"


def _fmt_price(v: Any) -> str:
    if v is None or v == "":
        return "-"
    try:
        return f"{float(v):.2f}"
    except (TypeError, ValueError):
        return str(v)


def _build_message(group_name: str, entries: List[Dict[str, Any]]) -> tuple[str, str]:
    """生成纯文本与 HTML 正文"""
    rows_plain = []
    rows_html = []

    for e in entries:
        symbol = e.get("stock_symbol") or e.get("symbol") or ""
        name = e.get("stock_name") or symbol
        status = e.get("status", "completed")
        if status != "completed":
            rows_plain.append(f"· {name}({symbol})  执行失败")
            rows_html.append(
                f'<tr><td>{name}({symbol})</td><td colspan="5" style="color:#dc2626;">执行失败</td></tr>'
            )
            continue

        decision = e.get("decision") or {}
        action = decision.get("action") or _parse_action(e.get("recommendation"))
        confidence = e.get("confidence_score", 0)
        risk = e.get("risk_level") or "中等"
        target = decision.get("target_price")
        reason = (decision.get("reasoning") or e.get("recommendation") or "").strip()
        if len(reason) > 60:
            reason = reason[:60] + "..."

        rows_plain.append(
            f"· {name}({symbol})  {action}  置信度{_pct(confidence)}%  风险{risk}  目标价{_fmt_price(target)}"
        )
        color = _action_color(action)
        rows_html.append(
            f'<tr>'
            f'<td>{name}({symbol})</td>'
            f'<td style="color:{color};font-weight:600;">{action}</td>'
            f'<td>{_fmt_price(target)}</td>'
            f'<td>{_pct(confidence)}%</td>'
            f'<td>{risk}</td>'
            f'<td style="font-size:12px;color:#6b7280;">{reason}</td>'
            f'</tr>'
        )

    plain = "\n".join(rows_plain)
    html_rows = "\n".join(rows_html)
    html = f"""\
<div style="font-family:'Microsoft YaHei',Arial,sans-serif;max-width:720px;margin:0 auto;color:#1f2937;">
  <h2 style="margin:0 0 4px;">📊 定时分析完成</h2>
  <p style="margin:0 0 16px;color:#6b7280;">任务组：{group_name}</p>
  <table style="width:100%;border-collapse:collapse;font-size:14px;">
    <thead>
      <tr style="background:#f3f4f6;text-align:left;">
        <th style="padding:8px;border:1px solid #e5e7eb;">股票</th>
        <th style="padding:8px;border:1px solid #e5e7eb;">决策</th>
        <th style="padding:8px;border:1px solid #e5e7eb;">目标价</th>
        <th style="padding:8px;border:1px solid #e5e7eb;">置信度</th>
        <th style="padding:8px;border:1px solid #e5e7eb;">风险</th>
        <th style="padding:8px;border:1px solid #e5e7eb;">理由</th>
      </tr>
    </thead>
    <tbody>
      {html_rows}
    </tbody>
  </table>
  <p style="margin-top:16px;font-size:12px;color:#9ca3af;">本邮件由定时分析任务自动生成，分析结果仅供参考，不构成投资建议。</p>
</div>"""
    return plain, html


def _parse_action(recommendation: Any) -> str:
    rec = str(recommendation or "")
    if "买入" in rec:
        return "买入"
    if "卖出" in rec:
        return "卖出"
    if "持有" in rec:
        return "持有"
    return "持有"


def _pct(v: Any) -> int:
    try:
        f = float(v)
        return round(f * 100) if f <= 1 else round(f)
    except (TypeError, ValueError):
        return 0


def _smtp_send(cfg: Dict[str, Any], msg: EmailMessage, recipients: List[str]) -> None:
    host = cfg.get("smtp_host") or "smtp.163.com"
    port = int(cfg.get("smtp_port") or 465)
    sender = cfg.get("sender")
    password = cfg.get("auth_code")

    if port == 465:
        server = smtplib.SMTP_SSL(host, port, timeout=30)
    else:
        server = smtplib.SMTP(host, port, timeout=30)
        server.ehlo()
        server.starttls()
        server.ehlo()
    try:
        server.login(sender, password)
        server.sendmail(sender, recipients, msg.as_bytes())
    finally:
        try:
            server.quit()
        except Exception:
            pass


async def send_report_email(group_name: str, entries: List[Dict[str, Any]]) -> bool:
    """发送定时分析结果邮件。返回是否已发送。"""
    cfg = await get_email_config()
    if not cfg.get("enabled"):
        logger.info(f"📧 邮件推送未启用，跳过: {group_name}")
        return False

    recipients = [r for r in (cfg.get("recipients") or []) if str(r).strip()]
    sender = cfg.get("sender")
    auth_code = cfg.get("auth_code")
    if not recipients or not sender or not auth_code:
        logger.warning(f"⚠️ 邮件配置不完整，跳过发送: {group_name}")
        return False

    plain, html = _build_message(group_name, entries)

    msg = EmailMessage()
    msg["Subject"] = f"[定时分析] {group_name} 已完成"
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.set_content(plain)
    msg.add_alternative(html, subtype="html")

    # 附加 PDF（每股一个），失败自动降级为仅正文
    if cfg.get("attach_pdf", True):
        for e in entries:
            if e.get("status") != "completed":
                continue
            try:
                pdf = await asyncio.to_thread(report_exporter.generate_pdf_report, e)
                symbol = e.get("stock_symbol") or e.get("symbol") or "report"
                msg.add_attachment(pdf, maintype="application", subtype="pdf", filename=f"{symbol}_分析报告.pdf")
            except Exception as e_pdf:
                logger.error(f"❌ PDF 生成失败，仅发送正文: {e_pdf}")

    try:
        await asyncio.to_thread(_smtp_send, cfg, msg, recipients)
        logger.info(f"✅ 邮件已发送: {group_name} -> {recipients}")
        return True
    except Exception as e:
        logger.error(f"❌ 邮件发送失败: {e}")
        return False