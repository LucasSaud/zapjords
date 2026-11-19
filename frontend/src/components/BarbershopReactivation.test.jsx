import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import BarbershopReactivation from './BarbershopReactivation';
import BarbershopContext from '../pages/ChatConversations/components/ChatContactSidebar/BarbershopContext';
import { fetchWithAuth } from '../AuthContext';

vi.mock('../AuthContext', () => ({ fetchWithAuth: vi.fn() }));
vi.mock('react-hot-toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
const response = data => ({ ok: true, json: async () => data });
beforeEach(() => vi.resetAllMocks());

describe('Operação da barbearia', () => {
  it('exige conferência antes de carregar público e invalida a revisão ao mudar o filtro', async () => {
    const contacts = [{ phone: '5511999990001', name: 'Ana', days_inactive: 40, variables: { appbarber_last_service: 'Corte' } }];
    fetchWithAuth.mockResolvedValue(response({ contacts, total: 1, excluded: { bloqueado: 1 } }));
    const select = vi.fn();
    render(<BarbershopReactivation clientId={1} onSelect={select} />);
    fireEvent.click(screen.getByText('Revisar público'));
    expect(await screen.findByText('Ana')).toBeInTheDocument();
    expect(screen.getByText('Usar nesta campanha')).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByText('Usar nesta campanha'));
    expect(select).toHaveBeenCalledWith(contacts);
    fireEvent.change(screen.getByLabelText('Dias sem atendimento'), { target: { value: 60 } });
    expect(screen.queryByText('Usar nesta campanha')).not.toBeInTheDocument();
  });

  it('registra pedido e exige confirmação do CRM para concluir', async () => {
    fetchWithAuth.mockResolvedValueOnce(response({ enabled: true, variables: { appbarber_last_professional: 'Carlos' }, source: {}, requests: [] }));
    render(<BarbershopContext conversationId={10} clientId={1} />);
    expect(await screen.findByText('Carlos')).toBeInTheDocument();
    fetchWithAuth.mockResolvedValueOnce(response({ id: 'r1', kind: 'remarcar', details: 'Sábado 10h', status: 'pending' }));
    fireEvent.change(screen.getByLabelText('Tipo de solicitação'), { target: { value: 'remarcar' } });
    fireEvent.change(screen.getByLabelText('Detalhes da solicitação'), { target: { value: 'Sábado 10h' } });
    fireEvent.click(screen.getByText('Registrar novo pedido'));
    expect(await screen.findByText('remarcar · Pendente no AppBarber')).toBeInTheDocument();
    expect(screen.getByText('Registrar conclusão no CRM')).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Detalhes da solicitação'), { target: { value: 'Confirmado sábado 10h no CRM' } });
    fireEvent.click(screen.getByRole('checkbox'));
    fetchWithAuth.mockResolvedValueOnce(response({ id: 'r1', kind: 'remarcar', details: 'Confirmado', status: 'confirmed' }));
    fireEvent.click(screen.getByText('Registrar conclusão no CRM'));
    await waitFor(() => expect(screen.getByText(/1 solicitação.*concluída/)).toBeInTheDocument());
    const payload = JSON.parse(fetchWithAuth.mock.calls[2][1].body);
    expect(payload).toMatchObject({ request_id: 'r1', status: 'confirmed', crm_confirmed: true });
  });
});
