from datetime import timedelta
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

import models
from core.logger import logger
from services.utils.phone_utils import normalize_phone


def _classify_delivery(trigger: models.ScheduledTrigger, messages: List[models.MessageStatus]) -> dict:
    """
    Classifica o status real de entrega no privado do contato a partir do ScheduledTrigger
    e dos registros de MessageStatus associados.
    """
    tpl_name = trigger.template_name or (trigger.funnel.name if getattr(trigger, "funnel", None) else None)
    trig_status = str(getattr(trigger, "status", "") or "").lower()

    has_read = any(
        (m.status in ("read", "interaction")) or bool(m.read_counted)
        for m in messages
    )
    has_interaction = any(
        (m.status == "interaction") or bool(m.is_interaction) or bool(m.interaction_counted)
        for m in messages
    )
    has_delivered = any(
        (m.status in ("delivered", "read", "interaction")) or bool(m.delivered_counted) or bool(m.is_interaction)
        for m in messages
    )
    has_sent = any(m.status == "sent" for m in messages)
    failed_msgs = [m for m in messages if m.status == "failed"]

    latest_ts = None
    for m in messages:
        dt = m.updated_at or m.timestamp
        if dt and (latest_ts is None or dt > latest_ts):
            latest_ts = dt
    if latest_ts is None:
        latest_ts = trigger.updated_at or trigger.created_at

    base = {
        "trigger_id": trigger.id,
        "template_name": tpl_name,
        "phone": trigger.contact_phone,
        "updated_at": latest_ts.isoformat() if latest_ts else None,
    }

    if has_interaction:
        return {**base, "status": "interaction", "delivered": True, "label": "Template entregue e interagiu no privado"}
    if has_read:
        return {**base, "status": "read", "delivered": True, "label": "Template entregue e lido no privado"}
    if has_delivered:
        return {**base, "status": "delivered", "delivered": True, "label": "Template entregue no privado"}

    if failed_msgs or trig_status in ("failed", "aborted"):
        reason = next((m.failure_reason for m in reversed(failed_msgs) if m.failure_reason), None) or trigger.failure_reason
        return {**base, "status": "failed", "delivered": False, "label": "Falha no envio", "reason": reason}

    if trig_status in ("cancelled", "canceled"):
        return {**base, "status": "cancelled", "delivered": False, "label": "Cancelado / Bloqueado", "reason": trigger.failure_reason}

    if has_sent or trig_status == "completed":
        return {**base, "status": "sent", "delivered": False, "label": "Enviado à Meta (aguardando entrega)"}

    if trig_status in ("queued", "pending", "processing", "scheduled"):
        return {**base, "status": "queued", "delivered": False, "label": "Na fila / Agendado"}

    return {**base, "status": trig_status or "pending", "delivered": False, "label": "Aguardando disparo"}


def _to_naive_utc(dt):
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is not None:
        return dt.replace(tzinfo=None)
    return dt


def enrich_webhook_history_whatsapp_delivery(
    db: Session,
    integration_id,
    history_items: List[models.WebhookHistory]
) -> None:
    """
    Popula o atributo transitório `whatsapp_delivery` em cada item de WebhookHistory,
    indicando se o template/funil disparado pelo webhook chegou no privado do contato.
    """
    if not history_items:
        return

    for item in history_items:
        item.whatsapp_delivery = None

    try:
        explicit_ids = set()
        phones_to_lookup = set()
        min_created = None

        for item in history_items:
            pdata = item.processed_data if isinstance(item.processed_data, dict) else {}
            tid = pdata.get("trigger_id")
            if tid:
                try:
                    explicit_ids.add(int(tid))
                except (TypeError, ValueError):
                    pass
            p_norm = normalize_phone(pdata.get("phone") or "")
            if p_norm:
                phones_to_lookup.add(p_norm)
                if len(p_norm) >= 8:
                    phones_to_lookup.add(p_norm[-8:])
            item_dt = _to_naive_utc(item.created_at)
            if item_dt and (min_created is None or item_dt < min_created):
                min_created = item_dt

        triggers_by_id: Dict[int, models.ScheduledTrigger] = {}
        if explicit_ids:
            explicit_trigs = db.query(models.ScheduledTrigger).filter(
                models.ScheduledTrigger.id.in_(list(explicit_ids))
            ).all()
            for t in explicit_trigs:
                triggers_by_id[t.id] = t

        fallback_trigs: List[models.ScheduledTrigger] = []
        if phones_to_lookup:
            q_fb = db.query(models.ScheduledTrigger).filter(
                models.ScheduledTrigger.integration_id == str(integration_id),
                models.ScheduledTrigger.is_bulk == False
            )
            fallback_trigs = q_fb.order_by(models.ScheduledTrigger.created_at.desc()).limit(200).all()
            for t in fallback_trigs:
                triggers_by_id.setdefault(t.id, t)

        if not triggers_by_id:
            return

        all_trig_ids = list(triggers_by_id.keys())
        child_trigs = db.query(models.ScheduledTrigger).filter(
            models.ScheduledTrigger.parent_id.in_(all_trig_ids)
        ).all()
        child_map: Dict[int, List[int]] = {}
        query_msg_trig_ids = set(all_trig_ids)
        for ct in child_trigs:
            if ct.parent_id:
                child_map.setdefault(ct.parent_id, []).append(ct.id)
                query_msg_trig_ids.add(ct.id)

        all_msgs = db.query(models.MessageStatus).filter(
            models.MessageStatus.trigger_id.in_(list(query_msg_trig_ids))
        ).order_by(models.MessageStatus.id.asc()).all()

        msgs_by_trig: Dict[int, List[models.MessageStatus]] = {}
        for m in all_msgs:
            msgs_by_trig.setdefault(m.trigger_id, []).append(m)

        for item in history_items:
            pdata = item.processed_data if isinstance(item.processed_data, dict) else {}
            matched_trig: Optional[models.ScheduledTrigger] = None

            tid = pdata.get("trigger_id")
            if tid:
                try:
                    matched_trig = triggers_by_id.get(int(tid))
                except (TypeError, ValueError):
                    matched_trig = None

            if not matched_trig:
                p_norm = normalize_phone(pdata.get("phone") or "")
                p_suf = p_norm[-8:] if len(p_norm) >= 8 else p_norm
                if p_norm:
                    for t in fallback_trigs:
                        t_phone = normalize_phone(t.contact_phone or "")
                        if not t_phone:
                            continue
                        if t_phone == p_norm or (p_suf and t_phone.endswith(p_suf)):
                            t_dt = _to_naive_utc(t.created_at)
                            h_dt = _to_naive_utc(item.created_at)
                            if h_dt and t_dt:
                                diff_sec = (t_dt - h_dt).total_seconds()
                                if diff_sec < -60:
                                    continue
                            matched_trig = t
                            break

            if matched_trig:
                rel_msgs = list(msgs_by_trig.get(matched_trig.id, []))
                for cid in child_map.get(matched_trig.id, []):
                    rel_msgs.extend(msgs_by_trig.get(cid, []))
                item.whatsapp_delivery = _classify_delivery(matched_trig, rel_msgs)
            else:
                item.whatsapp_delivery = None
    except Exception as e:
        logger.warning(f"⚠️ [WEBHOOK_DELIVERY_STATUS] Erro ao enriquecer status de entrega: {e}")
