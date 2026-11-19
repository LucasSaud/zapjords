"""Reviewable audience from a dated AppBarber export, never an agenda sync."""
from collections import Counter
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from fastapi import HTTPException
import models
from routers.leads_import.appbarber import visit_date
from services.utils.contact_identity import full_phone_key


def reactivation_audience(db, client_id, minimum_days, service='', professional=''):
    leads = db.query(models.WebhookLead).filter_by(client_id=client_id).limit(5001).all()
    if len(leads) > 5000:
        raise HTTPException(400, 'Esta versão permite revisar até 5.000 contatos por barbearia.')
    identities = Counter(full_phone_key(lead.phone) for lead in leads)
    blocked = {full_phone_key(row.phone) for row in db.query(models.BlockedContact).filter_by(client_id=client_id).all()}
    resting = {full_phone_key(row.phone) for row in db.query(models.RestingContact).filter(
        models.RestingContact.client_id == client_id, models.RestingContact.expires_at > datetime.now(timezone.utc)).all()}
    pending = {full_phone_key(row.phone) for row in db.query(models.ChatConversation).filter_by(client_id=client_id).all()
               if 'Pendente no AppBarber' in (row.labels or [])}
    today = datetime.now(ZoneInfo('America/Sao_Paulo')).date()
    counts = Counter()
    contacts = []
    for lead in leads:
        source = (lead.metadata_payload or {}).get('appbarber')
        if not source:
            continue
        variables = lead.variables or {}
        if service and variables.get('appbarber_last_service', '').casefold() != service.strip().casefold():
            continue
        if professional and variables.get('appbarber_last_professional', '').casefold() != professional.strip().casefold():
            continue
        phone = full_phone_key(lead.phone)
        reason = None
        if not phone or identities[phone] != 1:
            reason = 'identidade_ambigua'
        elif phone in blocked:
            reason = 'bloqueado'
        elif phone in resting:
            reason = 'em_descanso'
        elif phone in pending:
            reason = 'pedido_pendente'
        elif source.get('date_semantics') != 'completed_visit':
            reason = 'data_nao_conferida'
        try:
            days = (today - visit_date(variables.get('appbarber_last_visit_date'))).days
        except ValueError:
            reason = reason or 'data_invalida'
            days = 0
        if reason:
            counts[reason] += 1
        elif days < minimum_days:
            counts['atendimento_recente'] += 1
        else:
            contacts.append(dict(id=lead.id, phone=phone, name=lead.name, variables=variables,
                                 days_inactive=days, is_blocked=False))
    contacts.sort(key=lambda item: (-item['days_inactive'], item['phone']))
    return dict(contacts=contacts, total=len(contacts), excluded=dict(counts), reference_date=today.isoformat(),
                agenda_checked=False, source='appbarber_file')
