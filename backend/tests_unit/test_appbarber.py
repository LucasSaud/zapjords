import io
import json
from datetime import datetime, timezone
from unittest.mock import patch
import pytest
from fastapi import BackgroundTasks, HTTPException, UploadFile
import models
from routers.leads_import import execute_import, preview_import
from routers.leads_import.processor import process_import_in_bg
from routers.leads_import.appbarber import read_appbarber
from routers.barbershop import context, save_request, ReceptionRequest
from services.delivery_policy import delivery_rejection, demo_rejection
from services.utils.contact_identity import import_phone

MAPPING = dict(name='Nome', phone='Telefone', appbarber_last_visit_date='Data do ultimo atendimento',
               appbarber_last_service='Servico', appbarber_last_professional='Profissional')
HEADER = 'Nome;Telefone;Data do ultimo atendimento;Servico;Profissional\n'


@pytest.fixture(autouse=True)
def isolated_upload_storage(tmp_path, monkeypatch):
    # A test database can reuse import IDs; never touch a running demo's files.
    import routers.leads_import as routes
    from routers.leads_import import storage
    monkeypatch.setattr(routes, 'IMPORT_FILES_DIR', str(tmp_path))
    monkeypatch.setattr(storage, 'IMPORT_FILES_DIR', str(tmp_path))


@pytest.fixture
def shop(db_session):
    item = models.Client(name='Barbearia ' + __import__('uuid').uuid4().hex)
    db_session.add(item); db_session.commit()
    return item


def run_import(db, shop, rows, variables=None):
    history = models.ContactImportHistory(client_id=shop.id, filename='appbarber.csv', status='pending')
    db.add(history); db.commit()
    process_import_in_bg(history.id, (HEADER + rows).encode(), 'csv', {**MAPPING, '_profile': 'appbarber', '_date_semantics': 'completed_visit'}, shop.id, 'campanha_teste')
    db.expire_all()
    return db.get(models.ContactImportHistory, history.id)


def test_preserves_five_fields_and_different_area_codes(db_session, shop):
    h = run_import(db_session, shop, 'Ana;11999990001;01/10/2026;Corte;Carlos\nBeto;21999990001;02/10/2026;Barba;Rui\n')
    assert h.status == 'completed' and h.imported_rows == 2
    rows = db_session.query(models.WebhookLead).filter_by(client_id=shop.id).order_by(models.WebhookLead.phone).all()
    assert [r.phone for r in rows] == ['5511999990001','5521999990001']
    assert rows[0].variables == dict(appbarber_last_visit_date='2026-10-01', appbarber_last_service='Corte', appbarber_last_professional='Carlos')
    assert rows[0].metadata_payload['appbarber']['import_id'] == h.id


def test_reimport_preserves_creation_other_variables_and_block(db_session, shop):
    original = datetime(2020, 1, 1, tzinfo=timezone.utc)
    lead = models.WebhookLead(client_id=shop.id, name='Ana', phone='5511999990001', created_at=original,
                              variables={'other':'keep'}, tags='vip')
    db_session.add_all([lead, models.BlockedContact(client_id=shop.id, phone=lead.phone)]); db_session.commit()
    rows = 'Ana;11999990001;01/10/2026;Corte;Carlos\n'
    run_import(db_session, shop, rows); run_import(db_session, shop, rows)
    db_session.refresh(lead)
    assert db_session.query(models.WebhookLead).filter_by(client_id=shop.id).count() == 1
    assert lead.created_at.year == 2020 and lead.variables['other'] == 'keep'
    assert 'vip' in lead.tags
    assert db_session.query(models.BlockedContact).filter_by(client_id=shop.id).count() == 1


def test_rejects_conflicts_and_invalid_dates_without_losing_valid_rows(db_session, shop):
    h=run_import(db_session, shop, 'Ana;11999990001;01/10/2026;Corte;Carlos\nOutra;11999990001;02/10/2026;Barba;Rui\nBeto;21999990002;31/02/2026;Corte;Carlos\nCris;31999990003;02/10/2026;Corte;Carlos\n')
    assert h.error_rows == 3 and h.imported_rows == 1
    assert db_session.query(models.ImportRowResult).filter_by(import_id=h.id).count() == 4


def test_duplicates_keep_latest_and_older_import_does_not_regress(db_session, shop):
    h=run_import(db_session, shop, 'Ana;11999990001;01/09/2026;Corte;Carlos\nAna;11999990001;01/10/2026;Barba;Rui\n')
    assert h.rejected_duplicate_rows == 1
    run_import(db_session, shop, 'Ana;11999990001;01/08/2026;Corte;Carlos\n')
    lead=db_session.query(models.WebhookLead).filter_by(client_id=shop.id).one()
    assert lead.variables['appbarber_last_service'] == 'Barba'
    assert lead.variables['appbarber_last_visit_date'] == '2026-10-01'


@pytest.mark.parametrize('raw,expected',[('55912345678','5555912345678'),('1132345678','551132345678'),('+5511999990001','5511999990001')])
def test_phone_keeps_area_code_55_and_landline(raw,expected):
    assert import_phone(raw)==expected


def test_international_phone_is_not_reinterpreted_as_brazilian():
    with pytest.raises(ValueError, match='brasileiros'):
        import_phone('+12025550123')


def test_malformed_csv_is_not_silently_truncated():
    with pytest.raises(ValueError): read_appbarber((HEADER+'Ana;11999990001;01/10/2026;Corte;Carlos;extra').encode(),'csv')


@pytest.mark.asyncio
async def test_api_import_stores_file_privately_and_cleans_after_success(db_session, shop):
    tasks=BackgroundTasks()
    response=await execute_import(tasks, UploadFile(filename='crm.csv', file=io.BytesIO((HEADER+'Ana;11999990001;01/10/2026;Corte;Carlos\n').encode())),
        json.dumps(MAPPING), 'teste', '', 'appbarber', 'completed_visit', shop.id, db_session, models.User(id=1))
    history=db_session.get(models.ContactImportHistory,response['import_id'])
    from pathlib import Path
    path=Path(history.file_path)
    assert 'static' not in path.parts and path.exists()
    await tasks()
    db_session.expire_all()
    assert not path.exists() and db_session.get(models.ContactImportHistory,history.id).status=='completed'


@pytest.mark.asyncio
async def test_large_upload_returns_413():
    with pytest.raises(HTTPException) as exc:
        await preview_import(UploadFile(filename='large.csv', file=io.BytesIO(b'x'*(5*1024*1024+1))), 'appbarber', models.User(id=1))
    assert exc.value.status_code==413


@pytest.mark.parametrize('kind', ['agendar', 'remarcar', 'cancelar'])
def test_request_needs_manual_crm_confirmation_and_is_private(db_session, shop, kind):
    run_import(db_session,shop,'Ana;11999990001;01/10/2026;Corte;Carlos\n')
    convo=models.ChatConversation(client_id=shop.id,phone='5511999990001')
    user=models.User(email=__import__('uuid').uuid4().hex+'@example.test',client_id=shop.id)
    db_session.add_all([convo,user]);db_session.commit()
    result=save_request(convo.id,ReceptionRequest(kind=kind,details='Anterior sexta 10h; solicitado sábado 10h com Carlos'),shop.id,db_session,user)
    with pytest.raises(HTTPException):
        save_request(convo.id,ReceptionRequest(kind='remarcar',details='Concluído',request_id=result['id'],status='confirmed'),shop.id,db_session,user)
    saved=save_request(convo.id,ReceptionRequest(kind='remarcar',details='CRM conferido: sábado 10h',request_id=result['id'],status='confirmed',crm_confirmed=True),shop.id,db_session,user)
    assert saved['status']=='confirmed'
    assert saved['kind'] == kind
    result=context(convo.id,shop.id,db_session,user)
    assert result['requests'][0]['status']=='confirmed'
    assert result['variables']['appbarber_last_professional']=='Carlos'
    messages=db_session.query(models.ChatMessage).filter_by(conversation_id=convo.id).all()
    assert all(m.meta_data['private'] and m.meta_data['skip_agentflow'] for m in messages)
    with pytest.raises(HTTPException) as exc: context(convo.id,shop.id+100,db_session,user)
    assert exc.value.status_code==404


def test_demo_allowlist_and_fresh_block_check(db_session,shop,monkeypatch):
    monkeypatch.setenv('WHATSAPP_DEMO_MODE','true')
    monkeypatch.setenv('WHATSAPP_DEMO_ALLOWLIST','5511999990001')
    assert demo_rejection('5521999990001')
    assert delivery_rejection(shop.id,'5511999990001') is None
    db_session.add(models.BlockedContact(client_id=shop.id,phone='11999990001'));db_session.commit()
    assert 'bloqueado' in delivery_rejection(shop.id,'5511999990001')
    monkeypatch.setenv('WHATSAPP_DEMO_ALLOWLIST','')
    assert demo_rejection('5511999990001')


def test_delivery_policy_rechecks_pause_and_previous_sent_result(db_session, shop, monkeypatch):
    monkeypatch.setenv('WHATSAPP_DEMO_MODE', 'false')
    trigger = models.ScheduledTrigger(client_id=shop.id, status='processing')
    db_session.add(trigger); db_session.commit()
    assert delivery_rejection(shop.id, '5511999990001', trigger.id) is None
    trigger.status = 'paused'; db_session.commit()
    assert 'interrompida' in delivery_rejection(shop.id, '5511999990001', trigger.id)
    trigger.status = 'processing'
    db_session.add(models.MessageStatus(trigger_id=trigger.id, message_id='test-' + __import__('uuid').uuid4().hex,
                                      phone_number='5511999990001', status='sent'))
    db_session.commit()
    assert 'já enviado' in delivery_rejection(shop.id, '5511999990001', trigger.id)


def test_xlsx_real_date_cell_is_preserved():
    import pandas as pd
    from routers.leads_import.appbarber import visit_date
    content = io.BytesIO()
    pd.DataFrame([{'Data': datetime(2026, 10, 1), 'Telefone': '11999990001'}]).to_excel(content, index=False)
    frame = read_appbarber(content.getvalue(), 'xlsx')
    assert visit_date(frame.iloc[0]['Data']).isoformat() == '2026-10-01'
    assert frame.iloc[0]['Telefone'] == '11999990001'


def test_new_visit_does_not_reuse_stale_service(db_session, shop):
    run_import(db_session, shop, 'Ana;11999990001;01/09/2026;Barba;Carlos\n')
    run_import(db_session, shop, 'Ana;11999990001;01/10/2026;;\n')
    lead = db_session.query(models.WebhookLead).filter_by(client_id=shop.id).one()
    assert lead.variables['appbarber_last_service'] == ''
    assert lead.variables['appbarber_last_professional'] == ''


def test_reactivation_filters_and_excludes_blocked_pending_unverified(db_session, shop):
    from services.barbershop_reactivation import reactivation_audience
    run_import(db_session, shop, 'Ana;11999990001;01/01/2020;Corte;Carlos\nBeto;21999990001;01/01/2020;Corte;Carlos\nCris;31999990003;01/01/2020;Barba;Rui\nDani;41999990004;01/01/2020;Corte;Carlos\n')
    db_session.add(models.BlockedContact(client_id=shop.id, phone='11999990001'))
    db_session.add(models.ChatConversation(client_id=shop.id, phone='5531999990003', labels=['Pendente no AppBarber']))
    dani = db_session.query(models.WebhookLead).filter_by(client_id=shop.id, name='Dani').one()
    dani.metadata_payload = {'appbarber': {'date_semantics': 'appointment'}}
    db_session.commit()
    result = reactivation_audience(db_session, shop.id, 30)
    assert [item['name'] for item in result['contacts']] == ['Beto']
    assert result['excluded'] == {'bloqueado': 1, 'pedido_pendente': 1, 'data_nao_conferida': 1}
    assert result['agenda_checked'] is False
    assert reactivation_audience(db_session, shop.id, 30, professional='Rui')['total'] == 0
    assert reactivation_audience(db_session, shop.id + 1000, 30)['total'] == 0


@pytest.mark.asyncio
async def test_low_level_whatsapp_never_calls_http_outside_allowlist(monkeypatch):
    from core.clients.whatsapp.client import WhatsAppClient
    monkeypatch.setenv('WHATSAPP_DEMO_MODE', 'true')
    monkeypatch.setenv('WHATSAPP_DEMO_ALLOWLIST', '')
    with patch('httpx.AsyncClient') as http:
        result = await WhatsAppClient(client_id=1).send_template('5511999990001', 'convite')
        assert result['error'] is True
        text_result = await WhatsAppClient(client_id=1).send_text_official('5511999990001', 'Teste')
        assert text_result['error'] is True
        http.assert_not_called()


@pytest.mark.asyncio
async def test_public_import_path_is_unavailable():
    import httpx
    from main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/static/imports/import_1.csv')
    assert response.status_code == 404


def test_failed_import_also_removes_private_file(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from database import Base
    import database
    # Use real committed transactions, since this scenario exercises rollback.
    engine = create_engine(f'sqlite:///{tmp_path / "failure.db"}')
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(database, 'SessionLocal', sessions)
    path = tmp_path / 'broken.csv'
    path.write_text('bad')
    with sessions() as db:
        history = models.ContactImportHistory(client_id=1, filename='broken.csv', status='pending', file_path=str(path))
        db.add(history); db.commit()
        import_id = history.id
    process_import_in_bg(import_id, b'bad', 'csv', {**MAPPING, '_profile': 'appbarber'}, 1)
    with sessions() as db:
        assert db.get(models.ContactImportHistory, import_id).status == 'failed'
    assert not path.exists()
    engine.dispose()


def test_private_request_never_calls_external_webhook(db_session, shop):
    from services.chat_webhook_service import after_message_insert
    from unittest.mock import Mock
    message = models.ChatMessage(conversation_id=1, sender_type='system', content='interno', meta_data={'private': True})
    with patch('services.chat_webhook_service.dispatch_webhook_in_thread') as dispatch:
        after_message_insert(None, Mock(), message)
        dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_block_prefetch_keeps_different_area_codes(db_session, shop):
    from services.bulk_dispatch_helpers import prefetch_blocked_and_resting
    db_session.add(models.BlockedContact(client_id=shop.id, phone='5511999990001')); db_session.commit()
    blocked, _ = await prefetch_blocked_and_resting(shop.id, [], None, db_session)
    assert '5511999990001' in blocked
    assert '99990001' not in blocked and '5521999990001' not in blocked


@pytest.mark.asyncio
async def test_cached_template_is_not_assumed_approved(db_session, shop):
    from routers.whatsapp_modules.template_routes import list_templates
    from unittest.mock import AsyncMock, Mock
    db_session.add(models.WhatsAppTemplateCache(id=98117, client_id=shop.id, name='convite', language='pt_BR', body='Olá'))
    db_session.commit()
    client = Mock(get_whatsapp_templates=AsyncMock(return_value=[]))
    with patch('routers.whatsapp_modules.template_routes.get_chatwoot_client', return_value=client):
        result = await list_templates(False, False, shop.id, models.User(id=1), db_session)
        assert result == []
        result = await list_templates(False, True, shop.id, models.User(id=1), db_session)
        assert result[0]['status'] == 'UNVERIFIED'
