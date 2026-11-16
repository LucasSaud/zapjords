import React from 'react';
import { FiCheckCircle, FiClock, FiXCircle, FiAlertCircle, FiSend } from 'react-icons/fi';

const STATUS_STYLES = {
  interaction: {
    container: 'bg-emerald-500/10 border-emerald-500/30',
    badge: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
    icon: FiCheckCircle,
    iconColor: 'text-emerald-400',
    title: 'Disparo Confirmado no Privado'
  },
  read: {
    container: 'bg-emerald-500/10 border-emerald-500/30',
    badge: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
    icon: FiCheckCircle,
    iconColor: 'text-emerald-400',
    title: 'Disparo Confirmado no Privado'
  },
  delivered: {
    container: 'bg-emerald-500/10 border-emerald-500/30',
    badge: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
    icon: FiCheckCircle,
    iconColor: 'text-emerald-400',
    title: 'Disparo Confirmado no Privado'
  },
  sent: {
    container: 'bg-blue-500/10 border-blue-500/25',
    badge: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
    icon: FiSend,
    iconColor: 'text-blue-400',
    title: 'Enviado à Meta'
  },
  queued: {
    container: 'bg-amber-500/10 border-amber-500/25',
    badge: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
    icon: FiClock,
    iconColor: 'text-amber-400',
    title: 'Agendado / Na Fila'
  },
  failed: {
    container: 'bg-red-500/10 border-red-500/25',
    badge: 'bg-red-500/20 text-red-300 border-red-500/30',
    icon: FiXCircle,
    iconColor: 'text-red-400',
    title: 'Falha no Disparo'
  },
  cancelled: {
    container: 'bg-gray-500/10 border-gray-500/25',
    badge: 'bg-gray-500/20 text-gray-300 border-gray-500/30',
    icon: FiAlertCircle,
    iconColor: 'text-gray-400',
    title: 'Disparo Cancelado'
  }
};

export default function HistoryWhatsappDeliveryStatus({ delivery }) {
  if (!delivery || !delivery.status) return null;

  const style = STATUS_STYLES[delivery.status] || STATUS_STYLES.queued;
  const Icon = style.icon;

  return (
    <div className={`mt-4 p-3.5 rounded-xl border ${style.container} relative z-10 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5`}>
      <div className="flex items-center gap-2.5">
        <Icon size={16} className={`${style.iconColor} shrink-0`} />
        <div>
          <div className="text-[10px] font-black uppercase tracking-widest text-gray-400">
            Entrega no Privado (WhatsApp)
          </div>
          <div className="text-xs font-bold text-gray-800 dark:text-gray-100 flex items-center gap-2 flex-wrap">
            <span>{delivery.label || style.title}</span>
            {delivery.template_name && (
              <span className="text-[10px] font-mono text-gray-400 bg-black/20 px-1.5 py-0.5 rounded">
                {delivery.template_name}
              </span>
            )}
          </div>
          {delivery.reason && (
            <div className="text-[11px] text-red-400 mt-0.5">{delivery.reason}</div>
          )}
        </div>
      </div>

      <span className={`px-2.5 py-1 rounded-lg text-[10px] font-black uppercase tracking-wider border shrink-0 self-start sm:self-center ${style.badge}`}>
        {delivery.delivered ? 'Chegou no Privado ✓✓' : style.title}
      </span>
    </div>
  );
}
