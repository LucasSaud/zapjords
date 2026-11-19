import { describe, expect, it } from 'vitest';
import { suggestAppbarberMapping } from './appbarberMapping';

describe('Perfil AppBarber', () => {
  it('mapeia os cinco campos sem alterar a data de cadastro', () => {
    const mapping = suggestAppbarberMapping(['Nome','Telefone','Data do último atendimento','Serviço','Profissional']);
    expect(mapping.appbarber_last_visit_date).toBe('Data do último atendimento');
    expect(mapping.created_at).toBe('');
    expect(mapping.appbarber_last_service).toBe('Serviço');
    expect(mapping.appbarber_last_professional).toBe('Profissional');
    expect(mapping.phone).toBe('Telefone');
  });
});
