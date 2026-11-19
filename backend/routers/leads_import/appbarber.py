"""AppBarber file adapter. Does not read or write the CRM agenda."""
import csv
import io
import os
import re
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import models
from services.utils.contact_identity import import_phone, full_phone_key
from .parsers import _split_tags

FIELDS = ('name', 'phone', 'appbarber_last_visit_date',
          'appbarber_last_service', 'appbarber_last_professional')
MAX_ROWS = 5000


def text_cell(value):
    return '' if value is None or pd.isna(value) else str(value).strip()


def visit_date(value):
    value = text_cell(value)
    # Excel date cells are read as midnight timestamps; no timezone conversion.
    if re.fullmatch(r'\d{4}-\d{2}-\d{2} 00:00:00', value):
        value = value[:10]
    for fmt, pattern in [('%d/%m/%Y', r'\d{2}/\d{2}/\d{4}'),
                         ('%Y-%m-%d', r'\d{4}-\d{2}-\d{2}')]:
        if re.fullmatch(pattern, value):
            try:
                parsed = datetime.strptime(value, fmt).date()
                if parsed > datetime.now(ZoneInfo('America/Sao_Paulo')).date():
                    raise ValueError('Data futura não identifica cliente inativo.')
                return parsed
            except ValueError:
                break
    raise ValueError('Data inválida ou futura. Use DD/MM/AAAA ou AAAA-MM-DD.')


def read_appbarber(content, extension):
    if extension == 'xlsx':
        df = pd.read_excel(io.BytesIO(content), dtype=str)
    elif extension == 'csv':
        try:
            decoded = content.decode('utf-8-sig')
        except UnicodeDecodeError:
            decoded = content.decode('cp1252')
        try:
            dialect = csv.Sniffer().sniff(decoded[:8192], delimiters=';,\t')
        except csv.Error:
            raise ValueError('CSV sem delimitador reconhecido. Use ponto e vírgula, vírgula ou tabulação.')
        rows = list(csv.reader(io.StringIO(decoded), dialect, strict=True))
        if not rows or len(set(rows[0])) != len(rows[0]):
            raise ValueError('Cabeçalhos ausentes ou duplicados.')
        if any(len(row) != len(rows[0]) for row in rows[1:] if row):
            raise ValueError('CSV com quantidade de colunas diferente entre linhas. Corrija o arquivo.')
        df = pd.DataFrame([row for row in rows[1:] if row], columns=rows[0])
    else:
        raise ValueError('Para AppBarber, use CSV ou XLSX.')
    if len(df) > MAX_ROWS:
        raise ValueError(f'O limite por importação é {MAX_ROWS} linhas.')
    if df.empty:
        raise ValueError('O arquivo não contém contatos.')
    return df


def validate_mapping(mapping, columns):
    if not isinstance(mapping, dict):
        raise ValueError('Mapeamento inválido.')
    for key in FIELDS:
        if not isinstance(mapping.get(key), str) or mapping[key] not in columns:
            raise ValueError(f'Mapeie a coluna de {key}.')
    if len({mapping[key] for key in FIELDS}) != len(FIELDS):
        raise ValueError('Selecione uma coluna diferente para cada campo AppBarber.')
    if mapping.get('created_at'):
        raise ValueError('Último atendimento não pode alterar a data de cadastro.')


def process_appbarber(db, history, content, extension, mapping, client_id, fixed_tags):
    """One bounded transaction: a crash can safely replay the entire import."""
    if history.status == 'completed':
        return
    df = read_appbarber(content, extension)
    validate_mapping(mapping, df.columns)
    now = datetime.now(timezone.utc)
    results = {}
    groups = {}
    for index, row in df.iterrows():
        result = dict(import_id=history.id, row_index=int(index) + 2,
                      name=text_cell(row[mapping['name']]), phone=text_cell(row[mapping['phone']]))
        try:
            result['phone'] = import_phone(result['phone'])
            day = visit_date(row[mapping['appbarber_last_visit_date']])
            if not result['name']:
                raise ValueError('Nome ausente; revise a identidade do cliente.')
            groups.setdefault(result['phone'], []).append((index, row, day, result))
        except ValueError as exc:
            result.update(status='error', reason=str(exc))
        results[index] = result

    existing = {}
    for lead in db.query(models.WebhookLead).filter(models.WebhookLead.client_id == client_id).all():
        key = full_phone_key(lead.phone)
        if key:
            existing.setdefault(key, []).append(lead)
    client = db.get(models.Client, client_id)
    imported = 0
    for phone, entries in groups.items():
        names = {entry[3]['name'].casefold() for entry in entries}
        matches = existing.get(phone, [])
        if len(names) > 1 or len(matches) > 1 or (matches and matches[0].name and matches[0].name.strip().casefold() not in names):
            for _, _, _, result in entries:
                result.update(status='error', reason='Telefone associado a identidades conflitantes. Revisão manual necessária.')
            continue
        entries.sort(key=lambda entry: entry[2], reverse=True)
        _, row, day, result = entries[0]
        for _, _, _, duplicate in entries[1:]:
            duplicate.update(status='rejected_duplicate_file', reason='Mesmo telefone e identidade; mantida a visita válida mais recente.')
        lead = matches[0] if matches else models.WebhookLead(
            client_id=client_id, project_id=client.project_id if client else None,
            imported_by_client_id=client_id, phone=phone, name=result['name'],
            platform='appbarber', last_event_type='importado', total_events=1)
        variables = dict(lead.variables or {})
        old_date = variables.get('appbarber_last_visit_date', '')
        if not old_date or day.isoformat() >= old_date:
            variables['appbarber_last_visit_date'] = day.isoformat()
            for key in FIELDS[3:]:
                value = text_cell(row[mapping[key]])
                # A new visit must not inherit the previous visit's service.
                variables[key] = value
            lead.variables = variables
            meta = dict(lead.metadata_payload or {})
            meta['appbarber'] = dict(source='file', import_id=history.id, imported_at=now.isoformat(),
                                    date_semantics=mapping.get('_date_semantics', 'appointment'))
            lead.metadata_payload = meta
        lead.tags = ', '.join(dict.fromkeys(_split_tags(lead.tags) + ['appbarber'] + _split_tags(fixed_tags)))
        db.add(lead)
        result.update(status='updated' if matches else 'imported', reason=None)
        imported += 1
    db.query(models.ImportRowResult).filter(models.ImportRowResult.import_id == history.id).delete()
    db.add_all([models.ImportRowResult(**result) for result in results.values()])
    history.original_total_rows = len(df)
    history.total_rows = len(df)
    history.imported_rows = imported
    history.error_rows = sum(result.get('status') == 'error' for result in results.values())
    history.rejected_duplicate_rows = sum(result.get('status') == 'rejected_duplicate_file' for result in results.values())
    history.rejected_invalid_phone_rows = 0
    history.status = 'completed'
    history.updated_at = now
    db.commit()
