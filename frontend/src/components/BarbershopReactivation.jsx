import React, { useEffect, useRef, useState } from 'react';
import { toast } from 'react-hot-toast';
import { API_URL } from '../config';
import { fetchWithAuth } from '../AuthContext';

export default function BarbershopReactivation({ clientId, onSelect, templateVariables = [] }) {
  const [days, setDays] = useState(30);
  const [service, setService] = useState('');
  const [professional, setProfessional] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [reviewed, setReviewed] = useState(false);
  const [mapping, setMapping] = useState({});
  const version = useRef(0);
  useEffect(() => { version.current += 1; setData(null); setReviewed(false); setLoading(false); }, [clientId, days, service, professional]);

  const preview = async () => {
    const requestVersion = ++version.current;
    setLoading(true); setData(null); setReviewed(false);
    try {
      const params = new URLSearchParams({ minimum_days: days, service, professional });
      const response = await fetchWithAuth(`${API_URL}/barbershop/reactivation?${params}`, {}, clientId);
      const result = await response.json();
      if (requestVersion !== version.current) return;
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Confira os filtros informados.');
      setData(result);
      toast.success(`${result.total} cliente(s) para revisão.`);
    } catch (error) { if (requestVersion === version.current) toast.error(error.message); }
    finally { if (requestVersion === version.current) setLoading(false); }
  };
  return <section className="mb-6 p-5 rounded-2xl border border-blue-500/30 bg-blue-500/5 space-y-4" aria-label="Recuperação de clientes AppBarber">
    <h2 className="text-lg font-bold">Recuperação de clientes · AppBarber</h2>
    <p className="text-sm text-gray-500 dark:text-gray-400">Selecione clientes pela data do último atendimento realizado. A planilha não informa horários futuros; confira a agenda antes da campanha.</p>
    <div className="flex flex-wrap gap-3 items-end">
      <label className="text-sm">Dias sem atendimento<input type="number" min="1" max="3650" value={days} onChange={e => setDays(e.target.value)} className="block w-40 rounded-lg border p-2 bg-white dark:bg-gray-900" /></label>
      <label className="text-sm">Serviço<input value={service} onChange={e => setService(e.target.value)} placeholder="Todos" className="block rounded-lg border p-2 bg-white dark:bg-gray-900" /></label>
      <label className="text-sm">Profissional<input value={professional} onChange={e => setProfessional(e.target.value)} placeholder="Todos" className="block rounded-lg border p-2 bg-white dark:bg-gray-900" /></label>
      <button type="button" onClick={preview} disabled={loading || !clientId || days < 1 || days > 3650} className="bg-blue-600 text-white rounded-lg px-4 py-2 disabled:opacity-40">{loading ? 'Consultando…' : 'Revisar público'}</button>
    </div>
    {data && <div className="space-y-3 text-sm">
      <p className="font-semibold">{data.total} cliente(s) no público · {Object.values(data.excluded).reduce((a, b) => a + b, 0)} excluído(s)</p>
      {Object.keys(data.excluded).length > 0 && <p className="text-gray-500">{Object.entries(data.excluded).map(([key, count]) => `${key.replaceAll('_', ' ')}: ${count}`).join(' · ')}</p>}
      <div className="overflow-x-auto max-h-64"><table className="w-full text-left"><thead><tr><th>Cliente</th><th>Dias</th><th>Último serviço</th><th>Profissional</th></tr></thead><tbody>
        {data.contacts.slice(0, 50).map(item => <tr key={item.phone} className="border-t border-gray-500/20"><td className="py-2">{item.name}<span className="block text-xs text-gray-500">{item.phone}</span></td><td>{item.days_inactive}</td><td>{item.variables.appbarber_last_service || 'Não informado'}</td><td>{item.variables.appbarber_last_professional || 'Não informado'}</td></tr>)}
      </tbody></table></div>
      {data.total > 50 && <p>Amostra dos primeiros 50; confira a lista completa na etapa de destinatários.</p>}
      {onSelect ? <>
        {templateVariables.map(variable => <label key={variable.key} className="block">{variable.label || variable.key}
          <select aria-label={`Mapear ${variable.key}`} value={mapping[variable.key] || ''} onChange={event => setMapping(current => ({ ...current, [variable.key]: event.target.value }))} className="block rounded-lg border p-2 bg-white dark:bg-gray-900">
            <option value="">Usar valor configurado no template</option><option value="name">Nome completo</option><option value="first_name">Primeiro nome</option><option value="appbarber_last_service">Último serviço</option><option value="appbarber_last_professional">Profissional</option><option value="appbarber_last_visit_date">Último atendimento</option>
          </select>
        </label>)}
        <label className="flex gap-2"><input type="checkbox" checked={reviewed} onChange={e => setReviewed(e.target.checked)} />Conferi a agenda futura no AppBarber e a permissão para contatar estes clientes.</label>
        <button type="button" disabled={!reviewed || data.total === 0} onClick={() => {
          const contacts = data.contacts.map(item => ({ ...item, ...(Object.keys(mapping).length ? { vars: Object.fromEntries(templateVariables.filter(variable => mapping[variable.key]).map(variable => {
            const field = mapping[variable.key];
            return [variable.key, field === 'name' ? item.name : field === 'first_name' ? item.name.split(' ')[0] : field === 'appbarber_last_visit_date' ? item.variables[field]?.split('-').reverse().join('/') : item.variables[field]];
          })) } : {}) }));
          onSelect(contacts); toast.success('Público carregado. Revise os destinatários e as variáveis do template.');
        }} className="rounded-lg bg-blue-600 text-white px-4 py-2 disabled:opacity-40">Usar nesta campanha</button>
      </> : <p>Em Disparo em Massa, escolha o template e use este mesmo filtro na etapa de destinatários.</p>}
    </div>}
  </section>;
}
