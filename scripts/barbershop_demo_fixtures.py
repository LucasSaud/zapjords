"""Presentation-only fixtures, installed exclusively by run_barbershop_demo.py."""
from fastapi import APIRouter, Depends, HTTPException
from core.deps import get_current_user, get_validated_client_id


def install_demo_routes(app):
    router = APIRouter()

    @router.get('/api/whatsapp/templates')
    def demo_templates(client_id=Depends(get_validated_client_id), user=Depends(get_current_user)):
        return [dict(id='demo-local', name='demonstracao_convite_sem_envio', language='pt_BR',
                     category='MARKETING', status='DEMO', is_demo=True, tags=['Demonstração fictícia'],
                     components=[dict(type='BODY', text='Olá, {{1}}! Aqui é a recepção da barbearia. Quer que a gente confira um horário para você? Se preferir não receber convites, é só avisar.')])]

    # A preview must never leave a campaign indefinitely queued without a worker.
    @router.post('/api/bulk-send/{action}')
    @router.post('/api/trigger-bulk')
    def block_demo_campaign_execution():
        raise HTTPException(409, 'Demonstração local: somente prévia. Envio e agendamento exigem WhatsApp validado e worker ativo.')

    for route in reversed(router.routes):
        app.router.routes.insert(0, route)
