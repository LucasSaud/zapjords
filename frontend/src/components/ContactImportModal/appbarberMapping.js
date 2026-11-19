export const appbarberFields = [
  ['appbarber_last_visit_date', 'Data do último atendimento'],
  ['appbarber_last_service', 'Serviço'],
  ['appbarber_last_professional', 'Profissional'],
];

const fold = value => String(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

export function suggestAppbarberMapping(headers) {
  const find = pattern => headers.find(h => pattern.test(fold(h))) || '';
  return {
    name: find(/nome|cliente/), phone: find(/telefone|celular|whatsapp/),
    email: '', created_at: '', tags: '', remove_tags: '',
    appbarber_last_visit_date: find(/ultimo.*(atendimento|agendamento|visita)|data.*atendimento/),
    appbarber_last_service: find(/servico/),
    appbarber_last_professional: find(/profissional|barbeiro/),
  };
}
