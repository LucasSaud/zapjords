"""Conservative contact identity: country and area code are never discarded."""
import re


def full_phone_key(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not re.fullmatch(r"[+()\s.\-\d]+", text):
        return ""
    digits = re.sub(r"\D", "", text)
    if len(digits) in (10, 11) and not text.startswith('+'):
        digits = '55' + digits
    return digits if 10 <= len(digits) <= 15 and not digits.startswith('0') else ""


def import_phone(value) -> str:
    phone = full_phone_key(value)
    if not phone:
        raise ValueError('Telefone inválido. Informe DDI, DDD e número completo.')
    if not phone.startswith('55'):
        raise ValueError('Este perfil AppBarber aceita telefones brasileiros (DDI 55). Revise números internacionais separadamente.')
    if phone.startswith('55'):
        from routers.leads_import.parsers import VALID_BRAZIL_DDDS
        if phone[2:4] not in {str(d) for d in VALID_BRAZIL_DDDS}:
            raise ValueError('DDD brasileiro inválido.')
        number = phone[4:]
        if not ((len(number) == 9 and number.startswith('9')) or
                (len(number) == 8 and number[0] in '2345')):
            raise ValueError('Número brasileiro incompleto ou ambíguo; revise sem acrescentar dígitos automaticamente.')
    return phone
