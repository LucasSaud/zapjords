import os
import sys
import uuid
import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import models
from database import Base
from services.webhook_delivery_status import enrich_webhook_history_whatsapp_delivery


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


def _seed_client_and_integration(db):
    client = models.Client(id=1, name="Cliente Teste")
    integ_id = uuid.uuid4()
    integ = models.WebhookIntegration(
        id=integ_id,
        client_id=1,
        name="Hotmart Teste",
        platform="hotmart",
        status="active",
    )
    db.add_all([client, integ])
    db.commit()
    return integ_id


def test_enrich_delivery_delivered_by_trigger_id(db_session):
    integ_id = _seed_client_and_integration(db_session)
    trig = models.ScheduledTrigger(
        id=501,
        client_id=1,
        integration_id=integ_id,
        contact_phone="5585998259497",
        template_name="boas_vindas_astrowake",
        status="completed",
        is_bulk=False,
    )
    ms = models.MessageStatus(
        trigger_id=501,
        message_id="wamid_deliv_1",
        phone_number="5585998259497",
        status="delivered",
        delivered_counted=True,
    )
    hist = models.WebhookHistory(
        id=10,
        integration_id=integ_id,
        event_type="compra_aprovada",
        status="processed",
        payload={"event": "PURCHASE_APPROVED"},
        processed_data={"phone": "5585998259497", "trigger_id": 501},
    )
    db_session.add_all([trig, ms, hist])
    db_session.commit()

    enrich_webhook_history_whatsapp_delivery(db_session, integ_id, [hist])
    assert hist.whatsapp_delivery is not None
    assert hist.whatsapp_delivery["delivered"] is True
    assert hist.whatsapp_delivery["status"] == "delivered"
    assert hist.whatsapp_delivery["label"] == "Template entregue no privado"
    assert hist.whatsapp_delivery["template_name"] == "boas_vindas_astrowake"


def test_enrich_delivery_read_and_failed_and_sent(db_session):
    integ_id = _seed_client_and_integration(db_session)

    trigs = [
        models.ScheduledTrigger(id=601, client_id=1, integration_id=integ_id, contact_phone="5511999990001", template_name="tpl_a", status="completed", is_bulk=False),
        models.ScheduledTrigger(id=602, client_id=1, integration_id=integ_id, contact_phone="5511999990002", template_name="tpl_b", status="completed", is_bulk=False),
        models.ScheduledTrigger(id=603, client_id=1, integration_id=integ_id, contact_phone="5511999990003", template_name="tpl_c", status="failed", failure_reason="Número inválido", is_bulk=False),
    ]
    msgs = [
        models.MessageStatus(trigger_id=601, message_id="m_read", phone_number="5511999990001", status="read", read_counted=True),
        models.MessageStatus(trigger_id=602, message_id="m_sent", phone_number="5511999990002", status="sent"),
        models.MessageStatus(trigger_id=603, message_id="m_fail", phone_number="5511999990003", status="failed", failure_reason="131026 Undeliverable"),
    ]
    hists = [
        models.WebhookHistory(id=21, integration_id=integ_id, event_type="compra_aprovada", status="processed", payload={}, processed_data={"trigger_id": 601}),
        models.WebhookHistory(id=22, integration_id=integ_id, event_type="compra_aprovada", status="processed", payload={}, processed_data={"trigger_id": 602}),
        models.WebhookHistory(id=23, integration_id=integ_id, event_type="compra_aprovada", status="processed", payload={}, processed_data={"trigger_id": 603}),
    ]
    db_session.add_all(trigs + msgs + hists)
    db_session.commit()

    enrich_webhook_history_whatsapp_delivery(db_session, integ_id, hists)

    assert hists[0].whatsapp_delivery["delivered"] is True
    assert hists[0].whatsapp_delivery["status"] == "read"

    assert hists[1].whatsapp_delivery["delivered"] is False
    assert hists[1].whatsapp_delivery["status"] == "sent"

    assert hists[2].whatsapp_delivery["delivered"] is False
    assert hists[2].whatsapp_delivery["status"] == "failed"
    assert "131026" in hists[2].whatsapp_delivery["reason"]


def test_enrich_delivery_legacy_fallback_by_phone_and_integration(db_session):
    integ_id = _seed_client_and_integration(db_session)
    now = datetime.now(timezone.utc)
    trig = models.ScheduledTrigger(
        id=701,
        client_id=1,
        integration_id=str(integ_id),
        contact_phone="5585998259497",
        template_name="tpl_legado",
        status="completed",
        is_bulk=False,
        created_at=now,
    )
    ms = models.MessageStatus(
        trigger_id=701,
        message_id="wamid_legado",
        phone_number="5585998259497",
        status="delivered",
        delivered_counted=True,
    )
    hist = models.WebhookHistory(
        id=30,
        integration_id=integ_id,
        event_type="compra_aprovada",
        status="processed",
        payload={},
        processed_data={"phone": "5585998259497"},
        created_at=now,
    )
    db_session.add_all([trig, ms, hist])
    db_session.commit()

    enrich_webhook_history_whatsapp_delivery(db_session, integ_id, [hist])
    assert hist.whatsapp_delivery is not None
    assert hist.whatsapp_delivery["delivered"] is True
    assert hist.whatsapp_delivery["trigger_id"] == 701


def test_list_webhook_history_filters_by_date_and_delivery_status(db_session):
    from routers.webhooks.history import list_webhook_history
    integ_id = _seed_client_and_integration(db_session)

    t1 = models.ScheduledTrigger(id=801, client_id=1, integration_id=str(integ_id), contact_phone="5511999990001", template_name="tpl_ok", status="completed", is_bulk=False)
    t2 = models.ScheduledTrigger(id=802, client_id=1, integration_id=str(integ_id), contact_phone="5511999990002", template_name="tpl_err", status="failed", is_bulk=False)
    m1 = models.MessageStatus(trigger_id=801, message_id="w_ok_1", phone_number="5511999990001", status="delivered", delivered_counted=True)
    m2 = models.MessageStatus(trigger_id=802, message_id="w_err_1", phone_number="5511999990002", status="failed", failure_reason="Erro")

    h1 = models.WebhookHistory(
        id=41,
        integration_id=integ_id,
        event_type="compra_aprovada",
        status="processed",
        payload={},
        processed_data={"phone": "5511999990001", "trigger_id": 801},
        created_at=datetime(2026, 11, 15, 18, 0, 0, tzinfo=timezone.utc),
    )
    h2 = models.WebhookHistory(
        id=42,
        integration_id=integ_id,
        event_type="compra_aprovada",
        status="processed",
        payload={},
        processed_data={"phone": "5511999990002", "trigger_id": 802},
        created_at=datetime(2026, 11, 15, 19, 0, 0, tzinfo=timezone.utc),
    )
    h3 = models.WebhookHistory(
        id=43,
        integration_id=integ_id,
        event_type="compra_aprovada",
        status="processed",
        payload={},
        processed_data={"phone": "5511999990001", "trigger_id": 801},
        created_at=datetime(2026, 11, 14, 18, 0, 0, tzinfo=timezone.utc),
    )
    db_session.add_all([t1, t2, m1, m2, h1, h2, h3])
    db_session.commit()

    fake_user = models.User(id=1, email="admin@test.com", role="super_admin", client_id=1)

    res_all_day15 = list_webhook_history(
        integration_id=str(integ_id),
        search=None,
        date="2026-11-15",
        delivery_status=None,
        x_client_id=1,
        db=db_session,
        current_user=fake_user,
    )
    assert [h.id for h in res_all_day15] == [42, 41]

    res_delivered_day15 = list_webhook_history(
        integration_id=str(integ_id),
        search=None,
        date="2026-11-15",
        delivery_status="delivered",
        x_client_id=1,
        db=db_session,
        current_user=fake_user,
    )
    assert [h.id for h in res_delivered_day15] == [41]

