import os
import sys
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import models
from database import Base
from services.bulk_persistence import get_sent_phones_set
from services.triggers_service import start_now_trigger_logic
from services.bulk import process_bulk_send


@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db, TestingSessionLocal
    finally:
        db.close()


@pytest.mark.asyncio
async def test_get_sent_phones_set_includes_all_processed_statuses(in_memory_db):
    """
    Garante que get_sent_phones_set retorna todos os telefones já processados
    (sent, delivered, read, interaction, skipped, failed, blocked) e não apenas 'sent'.
    """
    db, _ = in_memory_db
    trig = models.ScheduledTrigger(
        id=1566,
        client_id=1,
        template_name="disparo_follownup_astrowake_blackfriday",
        is_bulk=True,
        status="completed",
        total_contacts=6
    )
    db.add(trig)
    db.add_all([
        models.MessageStatus(trigger_id=1566, message_id="m1", phone_number="5511999990001", status="sent"),
        models.MessageStatus(trigger_id=1566, message_id="m2", phone_number="5511999990002", status="delivered"),
        models.MessageStatus(trigger_id=1566, message_id="m3", phone_number="5511999990003", status="read"),
        models.MessageStatus(trigger_id=1566, message_id="m4", phone_number="5511999990004", status="skipped"),
        models.MessageStatus(trigger_id=1566, message_id="m5", phone_number="5511999990005", status="failed"),
    ])
    db.commit()

    processed_set = await get_sent_phones_set(db, 1566)
    assert "5511999990001" in processed_set
    assert "5511999990002" in processed_set
    assert "5511999990003" in processed_set
    assert "5511999990004" in processed_set
    assert "5511999990005" in processed_set
    assert "5511999990006" not in processed_set


@pytest.mark.asyncio
async def test_process_bulk_send_resume_sends_only_to_remaining_and_preserves_counts(in_memory_db):
    """
    Valida que ao retomar um disparo parcial (ex: 2 já enviados/entregues, 1 falha e 2 restantes),
    process_bulk_send envia SOMENTE para os 2 restantes e preserva os contadores anteriores.
    """
    db, SessionFactory = in_memory_db

    contacts = [
        {"name": "C1", "phone": "5511999990001"},
        {"name": "C2", "phone": "5511999990002"},
        {"name": "C3", "phone": "5511999990003"},
        {"name": "C4", "phone": "5511999990004"},
        {"name": "C5", "phone": "5511999990005"},
    ]
    trig = models.ScheduledTrigger(
        id=1566,
        client_id=1,
        template_name="disparo_follownup",
        is_bulk=True,
        status="queued",
        contacts_list=contacts,
        total_contacts=5,
        total_sent=2,
        total_delivered=1,
        total_failed=1
    )
    db.add(trig)
    db.add_all([
        models.MessageStatus(trigger_id=1566, message_id="wamid_1", phone_number="5511999990001", status="sent"),
        models.MessageStatus(trigger_id=1566, message_id="wamid_2", phone_number="5511999990002", status="delivered", delivered_counted=True),
        models.MessageStatus(trigger_id=1566, message_id="wamid_3", phone_number="5511999990003", status="failed", failure_reason="Erro Meta"),
    ])
    db.commit()

    sent_calls = []

    async def fake_send_smart_message(chatwoot, phone, trigger_id, *args, **kwargs):
        sent_calls.append(phone)
        return {"id": f"wamid_new_{phone}", "type": "TEMPLATE"}

    with patch("services.bulk.SessionLocal", side_effect=SessionFactory), \
         patch("services.bulk.ChatwootClient", return_value=MagicMock(simulate=False)), \
         patch("services.bulk.resolve_template_body_with_sync", AsyncMock(return_value=("Corpo teste", {"quick_replies": [], "has_special_buttons": False}))), \
         patch("services.bulk.send_smart_message", side_effect=fake_send_smart_message), \
         patch("services.bulk.rabbitmq.publish_event", AsyncMock()):

        await process_bulk_send(
            trigger_id=1566,
            template_name="disparo_follownup",
            contacts=contacts,
            delay=0,
            concurrency=2
        )

    # Deve ter disparado APENAS para os 2 contatos restantes (0004 e 0005)
    assert sent_calls == ["5511999990004", "5511999990005"]

    db.expire_all()
    updated_trig = db.query(models.ScheduledTrigger).get(1566)
    assert updated_trig.status == "completed"
    assert updated_trig.total_sent == 4
    assert updated_trig.total_failed == 1


@pytest.mark.asyncio
async def test_process_bulk_send_reclaims_wamid_on_status_match_race_condition(in_memory_db):
    """
    Valida que se um webhook rápido de entrega associou o novo wamid a um registro antigo
    de outro trigger ([STATUS_MATCH]), o bulk.py recupera o wamid sem causar UniqueViolation.
    """
    db, SessionFactory = in_memory_db

    # Registro antigo de outro trigger que teve o message_id sobrescrito pela condição de corrida
    old_ms = models.MessageStatus(
        trigger_id=1000,
        message_id="wamid_race_123",
        phone_number="5521988887777",
        status="delivered",
        delivered_counted=True
    )
    trig = models.ScheduledTrigger(
        id=2000,
        client_id=1,
        template_name="tpl_race",
        is_bulk=True,
        status="queued",
        contacts_list=[{"phone": "5521988887777"}],
        total_contacts=1
    )
    db.add_all([old_ms, trig])
    db.commit()

    async def fake_send(*args, **kwargs):
        return {"id": "wamid_race_123", "type": "TEMPLATE"}

    with patch("services.bulk.SessionLocal", side_effect=SessionFactory), \
         patch("services.bulk.ChatwootClient", return_value=MagicMock(simulate=False)), \
         patch("services.bulk.resolve_template_body_with_sync", AsyncMock(return_value=("Texto", {"quick_replies": [], "has_special_buttons": False}))), \
         patch("services.bulk.send_smart_message", side_effect=fake_send), \
         patch("services.bulk.rabbitmq.publish_event", AsyncMock()):

        await process_bulk_send(
            trigger_id=2000,
            template_name="tpl_race",
            contacts=[{"phone": "5521988887777"}],
            delay=0,
            concurrency=1
        )

    db.expire_all()
    new_ms = db.query(models.MessageStatus).filter_by(trigger_id=2000, message_id="wamid_race_123").first()
    assert new_ms is not None
    assert new_ms.status == "delivered"


@pytest.mark.asyncio
async def test_start_now_trigger_logic_enqueues_completed_trigger_even_with_recent_heartbeat(in_memory_db):
    """
    Garante que start_now_trigger_logic publica na fila 'zapvoice_bulk_sends' quando o disparo
    está com status 'completed' ou 'failed', mesmo que last_heartbeat tenha menos de 30s.
    """
    db, _ = in_memory_db
    from datetime import datetime
    trig = models.ScheduledTrigger(
        id=1566,
        client_id=1,
        template_name="disparo_follownup",
        is_bulk=True,
        status="completed",
        contacts_list=[{"phone": "5511999990001"}, {"phone": "5511999990002"}],
        processed_data={"last_heartbeat": datetime.utcnow().isoformat()},
        delay_seconds=1,
        concurrency_limit=10
    )
    db.add(trig)
    db.commit()

    with patch("services.triggers_service.rabbitmq.publish", AsyncMock()) as mock_pub:
        res = await start_now_trigger_logic(1566, db)
        assert res["status"] == "success"
        assert mock_pub.called
        assert trig.status == "queued"


@pytest.mark.asyncio
async def test_process_bulk_send_isolates_batch_exception_and_continues_next_batches(in_memory_db):
    """
    Garante que se um lote sofrer uma exceção inesperada durante o processamento/commit,
    o erro é isolado no lote e os lotes seguintes continuam sendo enviados até o fim.
    """
    db, SessionFactory = in_memory_db
    contacts = [
        {"phone": "5511999990011"},
        {"phone": "5511999990012"},
    ]
    trig = models.ScheduledTrigger(
        id=3000,
        client_id=1,
        template_name="tpl_batch_iso",
        is_bulk=True,
        status="queued",
        contacts_list=contacts,
        total_contacts=2
    )
    db.add(trig)
    db.commit()

    sent_phones = []

    async def fake_send(chatwoot, phone, *args, **kwargs):
        sent_phones.append(phone)
        return {"id": f"wamid_{phone}", "type": "TEMPLATE"}

    call_count = {"n": 0}
    orig_update = __import__("services.bulk", fromlist=["update_trigger_stats"]).update_trigger_stats

    def flaky_update_stats(db_s, tid, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("Falha simulada no lote 1")
        return orig_update(db_s, tid, **kwargs)

    with patch("services.bulk.SessionLocal", side_effect=SessionFactory), \
         patch("services.bulk.ChatwootClient", return_value=MagicMock(simulate=False)), \
         patch("services.bulk.resolve_template_body_with_sync", AsyncMock(return_value=("Texto", {"quick_replies": [], "has_special_buttons": False}))), \
         patch("services.bulk.send_smart_message", side_effect=fake_send), \
         patch("services.bulk.update_trigger_stats", side_effect=flaky_update_stats), \
         patch("services.bulk.rabbitmq.publish_event", AsyncMock()):

        await process_bulk_send(
            trigger_id=3000,
            template_name="tpl_batch_iso",
            contacts=contacts,
            delay=0,
            concurrency=1
        )

    # Ambos os lotes foram tentados mesmo após falha no lote 1
    assert sent_phones == ["5511999990011", "5511999990012"]

