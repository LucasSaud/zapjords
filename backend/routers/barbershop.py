"""Reception work log. The AppBarber agenda remains authoritative."""
from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import models
from core.deps import get_db, get_current_user, get_validated_client_id
from services.utils.contact_identity import full_phone_key

router = APIRouter()


@router.get('/barbershop/reactivation')
def reactivation(minimum_days: int = Query(30, ge=1, le=3650), service: str = Query('', max_length=200),
                 professional: str = Query('', max_length=200), client_id: int = Depends(get_validated_client_id),
                 db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    from services.barbershop_reactivation import reactivation_audience
    return reactivation_audience(db, client_id, minimum_days, service, professional)


def conversation(db, conversation_id, client_id):
    convo = db.query(models.ChatConversation).filter_by(id=conversation_id, client_id=client_id).first()
    if not convo:
        raise HTTPException(404, 'Conversa não encontrada.')
    return convo


def request_history(db, conversation_id):
    messages = db.query(models.ChatMessage).filter_by(conversation_id=conversation_id, sender_type='system').order_by(models.ChatMessage.id).all()
    latest = {}
    for message in messages:
        data = (message.meta_data or {}).get('barbershop_request')
        if data:
            latest[data['id']] = data
    return list(latest.values())


@router.get('/chat/conversations/{conversation_id}/barbershop')
def context(conversation_id: int, client_id: int = Depends(get_validated_client_id),
            db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    convo = conversation(db, conversation_id, client_id)
    leads = db.query(models.WebhookLead).filter_by(client_id=client_id).all()
    matching = [lead for lead in leads if full_phone_key(lead.phone) and full_phone_key(lead.phone) == full_phone_key(convo.phone)]
    lead = matching[0] if len(matching) == 1 else None
    requests = request_history(db, convo.id)
    return dict(enabled=bool(requests) or any((item.metadata_payload or {}).get('appbarber') for item in leads),
                variables=(lead.variables or {}) if lead else {},
                source=((lead.metadata_payload or {}).get('appbarber') or {}) if lead else {},
                requests=requests, ambiguous=len(matching) > 1)


class ReceptionRequest(BaseModel):
    kind: Literal['agendar', 'remarcar', 'cancelar']
    details: str = Field(min_length=3, max_length=2000)
    request_id: Optional[str] = None
    status: Literal['pending', 'confirmed'] = 'pending'
    crm_confirmed: bool = False


@router.post('/chat/conversations/{conversation_id}/barbershop/requests')
def save_request(conversation_id: int, payload: ReceptionRequest,
                 client_id: int = Depends(get_validated_client_id), db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)):
    convo = conversation(db, conversation_id, client_id)
    if not payload.details.strip():
        raise HTTPException(400, 'Descreva o pedido e o resultado da consulta ao CRM.')
    old = next((item for item in request_history(db, convo.id) if item['id'] == payload.request_id), None)
    if payload.request_id and not old:
        raise HTTPException(404, 'Solicitação não encontrada nesta conversa.')
    if old and old['status'] == 'confirmed':
        raise HTTPException(409, 'Solicitação já concluída; registre um novo pedido.')
    if payload.status == 'confirmed' and (not old or not payload.crm_confirmed):
        raise HTTPException(400, 'Confirme a operação no AppBarber antes de concluir a solicitação pendente.')
    data = dict(id=old['id'] if old else str(uuid4()), kind=old['kind'] if old else payload.kind,
                details=payload.details.strip(), status=payload.status,
                user_id=user.id, updated_at=datetime.now(timezone.utc).isoformat())
    status_text = 'Confirmado manualmente no AppBarber' if data['status'] == 'confirmed' else 'Pendente no AppBarber'
    db.add(models.ChatMessage(conversation_id=convo.id, sender_type='system', user_id=user.id,
                             message_type='text', content=f"🔒 Anotação Privada: {data['kind']} — {status_text}. {data['details']}",
                             meta_data={'private': True, 'skip_agentflow': True, 'barbershop_request': data}))
    labels = [label for label in (convo.labels or []) if label not in ('Pendente no AppBarber', 'Concluído no AppBarber')]
    other_pending = any(item['status'] == 'pending' and item['id'] != data['id'] for item in request_history(db, convo.id))
    labels.append('Pendente no AppBarber' if data['status'] == 'pending' or other_pending else 'Concluído no AppBarber')
    convo.labels = labels
    convo.status = 'open'
    db.commit()
    return data
