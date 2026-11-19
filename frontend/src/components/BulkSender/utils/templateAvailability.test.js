import { describe, it, expect, vi } from 'vitest';
import { isUsableTemplate } from './templateAvailability';
vi.mock('../../AppContent/constants', () => ({ SIMULATE_MESSAGING: false }));

describe('Disponibilidade do template', () => {
  it('exige aprovação conhecida e impede modelo fictício fora da demonstração', () => {
    expect(isUsableTemplate({ status: 'APPROVED' })).toBe(true);
    expect(isUsableTemplate({ status: 'UNVERIFIED' })).toBe(false);
    expect(isUsableTemplate({})).toBe(false);
    expect(isUsableTemplate({ status: 'DEMO', is_demo: true })).toBe(false);
  });
});
