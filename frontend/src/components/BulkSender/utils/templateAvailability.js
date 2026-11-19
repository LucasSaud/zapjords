import { SIMULATE_MESSAGING } from '../../AppContent/constants';

export const isUsableTemplate = template => {
  if (template?.is_demo) return SIMULATE_MESSAGING && template.status === 'DEMO';
  return ['APPROVED', 'ACTIVE'].includes(String(template?.status || '').toUpperCase());
};
