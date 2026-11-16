import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import HistoryModal from './index';

describe('HistoryModal Component', () => {
  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    integration: { id: 'int-123', name: 'LndingPage - Bussola Quiz' },
    webhookHistory: [],
    loadingHistory: false,
    webhookHistorySearch: '',
    setWebhookHistorySearch: vi.fn(),
    webhookHistoryStatusFilter: '',
    setWebhookHistoryStatusFilter: vi.fn(),
    webhookHistoryMappingFilter: '',
    setWebhookHistoryMappingFilter: vi.fn(),
    historyCurrentPage: 1,
    setHistoryCurrentPage: vi.fn(),
    historyPageSize: 20,
    setHistoryPageSize: vi.fn(),
    selectedHistoryIds: [],
    handleSelectAll: vi.fn(),
    handleToggleSelect: vi.fn(),
    handleResendWebhook: vi.fn(),
    handleSyncHistory: vi.fn(),
    handleSyncAllHistory: vi.fn(),
    handleExportHistory: vi.fn(),
    handleImportHistory: vi.fn(),
    isSyncingAll: false,
    isSyncing: false,
    isResending: false,
    setConfirmDeleteHistory: vi.fn(),
    setConfirmResendHistory: vi.fn(),
    setEditJsonModal: vi.fn(),
    setMaximizedJson: vi.fn(),
    fetchHistory: vi.fn(),
    bulkResendProgress: null,
    setBulkResendProgress: vi.fn(),
    handleUpdateCustomFieldsMapping: vi.fn(),
  };

  it('não renderiza se isOpen for falso', () => {
    const { container } = render(<HistoryModal {...defaultProps} isOpen={false} />);
    expect(container.firstChild).toBeNull();
  });

  it('mantém a barra de pesquisa e controles visíveis quando a busca não encontra registros', () => {
    render(
      <HistoryModal
        {...defaultProps}
        webhookHistory={[]}
        webhookHistorySearch="5511987654322"
      />
    );

    // Header presente
    expect(screen.getByText(/Histórico: LndingPage - Bussola Quiz/i)).toBeInTheDocument();

    // Input de busca continua visível e com o valor buscado
    const searchInput = screen.getByPlaceholderText('Buscar por nome, telefone ou payload...');
    expect(searchInput).toBeInTheDocument();
    expect(searchInput).toHaveValue('5511987654322');

    // Mensagem de busca vazia
    expect(screen.getByText('Nenhum registro encontrado')).toBeInTheDocument();
    expect(screen.getByText(/Não encontramos webhooks para "5511987654322"/i)).toBeInTheDocument();

    // Botão de limpar busca e filtros
    const clearBtn = screen.getByText('Limpar Filtros e Busca');
    expect(clearBtn).toBeInTheDocument();

    // Clicar em limpar chama as funções de reset
    fireEvent.click(clearBtn);
    expect(defaultProps.setWebhookHistorySearch).toHaveBeenCalledWith('');
    expect(defaultProps.setWebhookHistoryStatusFilter).toHaveBeenCalledWith('');
    expect(defaultProps.setWebhookHistoryMappingFilter).toHaveBeenCalledWith('');
    expect(defaultProps.fetchHistory).toHaveBeenCalledWith('int-123', '', '');
  });

  it('exibe estado vazio de integração sem webhooks mas mantém barra de controles visível', () => {
    render(
      <HistoryModal
        {...defaultProps}
        webhookHistory={[]}
        webhookHistorySearch=""
      />
    );

    expect(screen.getByPlaceholderText('Buscar por nome, telefone ou payload...')).toBeInTheDocument();
    expect(screen.getByText('Esta integração ainda não recebeu webhooks.')).toBeInTheDocument();
    expect(screen.getByText(/Importar Histórico/i)).toBeInTheDocument();
  });

  it('renderiza registros quando webhookHistory possui dados válidos', () => {
    const mockItems = [
      {
        id: 1,
        event_type: 'compra_aprovada',
        status: 'success',
        created_at: '2026-09-26T12:00:00Z',
        processed_data: { contact_name: 'Cliente Teste', phone: '5511999999999' },
      },
    ];

    render(
      <HistoryModal
        {...defaultProps}
        webhookHistory={mockItems}
      />
    );

    expect(screen.getByText(/1 registro\(s\)/i)).toBeInTheDocument();
  });

  it('filtra por entrega no WhatsApp (Chegou no Privado) e por data de recebimento', () => {
    const mockItems = [
      {
        id: 1,
        event_type: 'compra_aprovada',
        status: 'processed',
        created_at: '2026-11-15T15:00:00Z',
        processed_data: { name: 'Contato Entregue Dia 15', phone: '5511999990001' },
        whatsapp_delivery: { status: 'delivered', delivered: true, label: 'Template entregue no privado' },
      },
      {
        id: 2,
        event_type: 'compra_aprovada',
        status: 'processed',
        created_at: '2026-11-15T16:00:00Z',
        processed_data: { name: 'Contato Falha Dia 15', phone: '5511999990002' },
        whatsapp_delivery: { status: 'failed', delivered: false, label: 'Falha no envio' },
      },
      {
        id: 3,
        event_type: 'compra_aprovada',
        status: 'processed',
        created_at: '2026-11-14T15:00:00Z',
        processed_data: { name: 'Contato Entregue Dia 14', phone: '5511999990003' },
        whatsapp_delivery: { status: 'delivered', delivered: true, label: 'Template entregue no privado' },
      },
    ];

    render(
      <HistoryModal
        {...defaultProps}
        webhookHistory={mockItems}
      />
    );

    expect(screen.getByText(/3 registro\(s\)/i)).toBeInTheDocument();

    const deliverySelect = screen.getByLabelText('Filtrar por entrega no WhatsApp');
    fireEvent.change(deliverySelect, { target: { value: 'delivered' } });
    expect(screen.getByText(/2 registro\(s\)/i)).toBeInTheDocument();

    const dateInput = screen.getByLabelText('Filtrar por data de recebimento');
    fireEvent.change(dateInput, { target: { value: '2026-11-15' } });
    expect(screen.getByText(/1 registro\(s\)/i)).toBeInTheDocument();
    expect(defaultProps.fetchHistory).toHaveBeenCalledWith('int-123', '', '', false, '2026-11-15');
  });
});
