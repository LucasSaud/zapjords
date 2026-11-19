import React, { useEffect, useState } from 'react';
import { toast } from 'react-hot-toast';
import { API_URL, BARBERSHOP_MODE } from '../../../../config';
import { fetchWithAuth } from '../../../../AuthContext';

export default function BarbershopContext({ conversationId, clientId }) {
  const [data, setData] = useState(null);
  const [kind, setKind] = useState('agendar');
  const [details, setDetails] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [saving, setSaving] = useState(false);
  const base = `${API_URL}/chat/conversations/${conversationId}/barbershop`;
  useEffect(() => {
    let active = true;
    setData(null); setDetails(''); setConfirmed(false);
    if (conversationId && clientId) {
      fetchWithAuth(base, {}, clientId).then(async res => {
        if (!res?.ok) throw new Error('Falha ao carregar contexto.');
        const body = await res.json();
        if (active) setData(body);
      }).catch(() => { if (active) toast.error('Não foi possível carregar o contexto AppBarber.'); });
    }
    return () => { active = false; };
  }, [base, clientId, conversationId]);

  const save = async (request = null) => {
    setSaving(true);
    try {
      const response = await fetchWithAuth(`${base}/requests`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ kind: request?.kind || kind, details: details.trim(),
          request_id: request?.id, status: request ? 'confirmed' : 'pending', crm_confirmed: confirmed }),
      }, clientId);
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || 'Não foi possível salvar.');
      setData(current => ({ ...current, requests: [...current.requests.filter(item => item.id !== body.id), body] }));
      setDetails(''); setConfirmed(false);
      toast.success(request ? 'Conclusão registrada. Confirme os detalhes ao cliente.' : 'Pedido registrado para a recepção.');
    } catch (error) { toast.error(error.message); }
    finally { setSaving(false); }
  };
  if (!data || (!data.enabled && !BARBERSHOP_MODE)) return null;
  const values = data.variables;
  const pending = data.requests.filter(item => item.status === 'pending');
  const date = values.appbarber_last_visit_date?.split('-').reverse().join('/');
  return (
    <section className="my-4 p-3 rounded-xl border border-gray-200 dark:border-gray-700 text-xs space-y-3" aria-label="Atendimento AppBarber">
      <div className="flex justify-between items-center gap-2">
        <h3 className="font-semibold text-sm">AppBarber</h3>
        <a href="https://sistema.appbarber.com.br/login.php" target="_blank" rel="noopener noreferrer" className="text-blue-600 underline">Abrir agenda</a>
      </div>
      <p className="text-gray-500">Base importada por planilha. Agenda atualizada pela recepção no AppBarber.</p>
      {data.ambiguous && <p className="text-amber-700">Mais de um contato usa este telefone. Confira a identidade no CRM.</p>}
      <dl className="space-y-1">
        <dt className="font-medium">{data.source.date_semantics === 'completed_visit' ? 'Último atendimento' : 'Último agendamento informado'}</dt><dd>{date || 'Não informado'}</dd>
        <dt className="font-medium">Serviço</dt><dd>{values.appbarber_last_service || 'Não informado'}</dd>
        <dt className="font-medium">Profissional</dt><dd>{values.appbarber_last_professional || 'Não informado'}</dd>
      </dl>
      {pending.map(item => <div key={item.id} className="border-t pt-2 space-y-2">
        <p className="font-semibold">{item.kind} · Pendente no AppBarber</p><p>{item.details}</p>
        <button type="button" disabled={saving || !confirmed || details.trim().length < 3} onClick={() => save(item)} className="text-blue-600 disabled:opacity-40 underline">Registrar conclusão no CRM</button>
      </div>)}
      <label className="block">Pedido
        <select aria-label="Tipo de solicitação" value={kind} onChange={e => setKind(e.target.value)} className="block w-full border rounded p-2 mt-1 bg-white dark:bg-gray-900">
          <option value="agendar">Agendar horário</option><option value="remarcar">Remarcar horário</option><option value="cancelar">Cancelar horário</option>
        </select>
      </label>
      <label className="block">Detalhes do pedido ou da conclusão
        <textarea aria-label="Detalhes da solicitação" value={details} maxLength={2000} onChange={e => setDetails(e.target.value)} placeholder="Serviço, profissional, dia, horário e resultado da consulta no CRM" className="w-full border rounded p-2 mt-1 bg-white dark:bg-gray-900" rows={3} />
      </label>
      {kind === 'remarcar' && <p className="text-gray-500">Registre o horário antigo e o novo, além do serviço e do profissional.</p>}
      {pending.length > 0 && <label className="flex gap-2"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />Conferi e concluí a operação na agenda do AppBarber.</label>}
      <button type="button" disabled={saving || details.trim().length < 3} onClick={() => save()} className="w-full rounded bg-blue-600 text-white p-2 disabled:opacity-40">{saving ? 'Salvando…' : 'Registrar novo pedido'}</button>
      {data.requests.some(item => item.status === 'confirmed') && <p className="text-green-700">{data.requests.filter(item => item.status === 'confirmed').length} solicitação(ões) concluída(s) manualmente no CRM.</p>}
      {data.requests.filter(item => item.status === 'confirmed').slice(-3).map(item => <div key={item.id} className="border-t border-gray-500/20 pt-2">
        <p className="font-semibold">Concluído · {item.kind}</p><p>{item.details}</p>
      </div>)}
    </section>
  );
}
