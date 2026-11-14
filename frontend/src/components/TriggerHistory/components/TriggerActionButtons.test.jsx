import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import TriggerActionButtons from './TriggerActionButtons';
import { useTriggerActions } from '../hooks/useTriggerActions';

describe('TriggerActionButtons - Reenviar para Contatos Restantes', () => {
  it('deve exibir o botão de reenviar para os contatos restantes mesmo quando status for completed e restarem contatos', () => {
    const handleStartNow = vi.fn();
    const handleEditParams = vi.fn();
    const triggerWithRemaining = {
      id: 1566,
      is_bulk: true,
      status: 'completed',
      total_contacts: 1326,
      total_sent: 378,
      total_failed: 24,
      total_skipped: 1,
      total_blocked: 0
    };

    render(
      <table>
        <tbody>
          <tr>
            <TriggerActionButtons
              triggerWithActions={triggerWithRemaining}
              handleStartNow={handleStartNow}
              handleEditParams={handleEditParams}
              handleViewPipeline={vi.fn()}
              handleCancel={vi.fn()}
              handleRetry={vi.fn()}
              handleDelete={vi.fn()}
              user={{ role: 'admin' }}
            />
          </tr>
        </tbody>
      </table>
    );

    const resumeBtn = screen.getByTitle('Reenviar para os 923 contatos restantes');
    expect(resumeBtn).toBeInTheDocument();

    fireEvent.click(resumeBtn);
    expect(handleStartNow).toHaveBeenCalledWith(1566, 923);
  });

  it('não deve exibir o botão de reenviar restantes quando status for completed e restarem 0 contatos', () => {
    const handleStartNow = vi.fn();
    const triggerCompletedFull = {
      id: 1567,
      is_bulk: true,
      status: 'completed',
      total_contacts: 100,
      total_sent: 98,
      total_failed: 2,
      total_skipped: 0,
      total_blocked: 0
    };

    render(
      <table>
        <tbody>
          <tr>
            <TriggerActionButtons
              triggerWithActions={triggerCompletedFull}
              handleStartNow={handleStartNow}
              handleEditParams={vi.fn()}
              handleViewPipeline={vi.fn()}
              handleCancel={vi.fn()}
              handleRetry={vi.fn()}
              handleDelete={vi.fn()}
              user={{ role: 'admin' }}
            />
          </tr>
        </tbody>
      </table>
    );

    expect(screen.queryByTitle(/contatos restantes/i)).toBeNull();
    expect(screen.queryByTitle(/Retomar Disparo/i)).toBeNull();
  });

  it('useTriggerActions.handleStartNow deve abrir confirmação específica quando houver contatos restantes', () => {
    const setModalConfig = vi.fn();
    const { result } = renderHook(() =>
      useTriggerActions({
        activeClient: { id: 1 },
        setTriggers: vi.fn(),
        fetchHistory: vi.fn(),
        setModalConfig,
        setSelectedIds: vi.fn(),
        setMonitoringTrigger: vi.fn(),
        selectedIds: []
      })
    );

    act(() => {
      result.current.handleStartNow(1566, 923);
    });

    expect(setModalConfig).toHaveBeenCalledWith({
      isOpen: true,
      type: 'start_now',
      id: 1566,
      title: 'Reenviar para Contatos Restantes',
      message: 'Tem certeza que deseja reenviar este disparo apenas para os 923 contatos restantes que ainda não receberam?',
      confirmText: 'Sim, Enviar Restantes (923)',
      isDangerous: false
    });
  });
});
