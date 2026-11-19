"""Last-moment checks for the controlled WhatsApp demonstration."""
import os
from services.utils.contact_identity import full_phone_key


def demo_rejection(phone):
    if os.getenv('WHATSAPP_DEMO_MODE', 'false').lower() != 'true':
        return None
    allowed = {full_phone_key(p) for p in os.getenv('WHATSAPP_DEMO_ALLOWLIST', '').split(',')}
    key = full_phone_key(phone)
    if not key or key not in allowed:
        return 'Modo demonstração: destinatário não está na lista autorizada.'
    return None


def delivery_rejection(client_id, phone, trigger_id=None):
    reason = demo_rejection(phone)
    if reason:
        return reason
    from database import SessionLocal
    import models
    db = SessionLocal()
    try:
        key = full_phone_key(phone)
        if not key:
            return 'Telefone incompleto ou inválido.'
        blocked = db.query(models.BlockedContact.phone).filter(models.BlockedContact.client_id == client_id).all()
        if any(full_phone_key(row[0]) == key for row in blocked if row[0]):
            return 'Contato bloqueado. Nenhuma mensagem enviada.'
        if trigger_id:
            trigger = db.query(models.ScheduledTrigger).filter(models.ScheduledTrigger.id == trigger_id).first()
            if not trigger or trigger.client_id != client_id or trigger.status in ('cancelled', 'canceled', 'aborted', 'paused', 'completed', 'failed', 'expired'):
                return 'Campanha interrompida ou indisponível.'
            sent = db.query(models.MessageStatus.phone_number).filter(
                models.MessageStatus.trigger_id == trigger_id,
                models.MessageStatus.status.in_(['sent', 'delivered', 'read'])
            ).all()
            if any(full_phone_key(row[0]) == key for row in sent):
                return 'Contato já enviado nesta campanha; repetição ignorada.'
    except Exception:
        return 'Não foi possível validar o destinatário. Envio suspenso.'
    finally:
        db.close()
    return None
