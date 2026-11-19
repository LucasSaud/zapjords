"""Local-only presentation server: SQLite, no broker, no external delivery.

Run with the backend dependencies installed. This is not a production launcher.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'backend'
DATA = BACKEND / 'var' / 'barbershop_demo'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    credentials_path = DATA / 'access.json'
    if credentials_path.exists():
        access = json.loads(credentials_path.read_text())
    else:
        access = dict(email='demo@barbearia.local', password=secrets.token_urlsafe(20), secret=secrets.token_urlsafe(48))
        credentials_path.write_text(json.dumps(access, indent=2))
        credentials_path.chmod(0o600)
    os.environ.update(DATABASE_URL=f'sqlite:///{DATA / "demo.db"}', SECRET_KEY=access['secret'],
                      SIMULATE_MESSAGING='true', WHATSAPP_DEMO_MODE='true', WHATSAPP_DEMO_ALLOWLIST='',
                      ENABLE_SCHEDULER='false')
    sys.path.insert(0, str(BACKEND))
    os.chdir(BACKEND)
    # File SQLite needs one connection per concurrent session. StaticPool is
    # suitable only for the single-connection in-memory test database.
    import database
    from sqlalchemy import create_engine
    database.engine.dispose()
    database.engine = create_engine(os.environ['DATABASE_URL'], connect_args={'check_same_thread': False, 'timeout': 30})
    database.SessionLocal.configure(bind=database.engine)
    with database.engine.connect() as connection:
        connection.exec_driver_sql('PRAGMA journal_mode=WAL')
    from main import app
    from database import Base, engine, SessionLocal
    from core.security import get_password_hash
    import models
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        shop = db.query(models.Client).filter_by(name='Barbearia Demonstração').first()
        if not shop:
            shop = models.Client(name='Barbearia Demonstração')
            db.add(shop); db.flush()
        user = db.query(models.User).filter_by(email=access['email']).first()
        if not user:
            user = models.User(email=access['email'], full_name='Recepção Demonstração',
                               hashed_password=get_password_hash(access['password']), role='super_admin',
                               client_id=shop.id, accessible_clients=[shop])
            db.add(user)
        if not db.query(models.ChatConversation).filter_by(client_id=shop.id).first():
            from datetime import datetime, timezone
            convo = models.ChatConversation(client_id=shop.id, phone='5511999990001', contact_name='Ana Demonstração',
                                            last_contact_message_at=datetime.now(timezone.utc), last_message_content='Mensagem fictícia: quero remarcar meu corte.', unread_count=1)
            db.add(convo); db.flush()
            db.add(models.ChatMessage(conversation_id=convo.id, sender_type='contact', message_type='text',
                                      content='Mensagem fictícia: quero remarcar meu corte.', meta_data={'demo': True, 'skip_agentflow': True}))
        db.commit()
    # This launcher intentionally does not run schedulers, broker or external listeners.
    # Production startup remains unchanged.
    app.router.on_startup.clear()
    app.router.on_shutdown.clear()
    from rabbitmq_client import rabbitmq
    async def no_broker(*args, **kwargs):
        return False
    rabbitmq.publish = no_broker
    rabbitmq.publish_event = no_broker
    rabbitmq.connect = no_broker
    rabbitmq.subscribe_events = no_broker
    from barbershop_demo_fixtures import install_demo_routes
    install_demo_routes(app)
    # Resume only this isolated database's interrupted file imports.
    from routers.leads_import.processor import process_import_in_bg
    with SessionLocal() as db:
        pending = [(item.id, item.file_ext, json.loads(item.mapping_json or '{}'), item.client_id, item.fixed_tags or '')
                   for item in db.query(models.ContactImportHistory).filter(models.ContactImportHistory.status.in_(['pending', 'processing'])).all()]
    for import_id, extension, mapping, client_id, tags in pending:
        process_import_in_bg(import_id, None, extension, mapping, client_id, tags)
    print(f'Demonstração local sem envio externo. Acesso em {credentials_path}', flush=True)
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
