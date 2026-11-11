import type { ReactNode } from 'react';
import { Archive, Loader2, AlertTriangle, Inbox, ScrollText } from 'lucide-react';

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <span className="grid h-9 w-9 place-items-center rounded-md bg-bosque-600 text-pergamino-50">
        <ScrollText size={20} />
      </span>
      {!compact && (
        <span className="archivo-titulo text-lg font-bold leading-tight">
          Servator Memoriae
          <span className="block text-xs font-sans font-normal text-tinta-clara">Archivo histórico</span>
        </span>
      )}
    </div>
  );
}

export function Loading({ texto = 'Cargando…' }: { texto?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 p-8 text-tinta-suave">
      <Loader2 className="animate-spin" size={20} />
      <span>{texto}</span>
    </div>
  );
}

export function ErrorState({ titulo = 'Algo salió mal', detalle, reintentar }: { titulo?: string; detalle?: string; reintentar?: () => void }) {
  return (
    <div className="papel rounded-lg p-6 text-center">
      <AlertTriangle className="mx-auto text-sello" size={28} />
      <h3 className="archivo-titulo mt-2 text-lg font-bold">{titulo}</h3>
      {detalle && <p className="mt-1 text-sm text-tinta-suave">{detalle}</p>}
      {reintentar && (
        <button className="btn btn-sm btn-primary mt-4" onClick={reintentar}>
          Reintentar
        </button>
      )}
    </div>
  );
}

export function Empty({ texto = 'Sin resultados', icono }: { texto?: string; icono?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-pergamino-300 bg-white/60 p-8 text-tinta-clara">
      {icono ?? <Inbox size={28} />}
      <p className="text-sm">{texto}</p>
    </div>
  );
}

const badgeStyles: Record<string, string> = {
  auto: 'badge-ghost',
  confirmed: 'badge-success',
  corrected: 'badge-info',
  illegible: 'badge-warning',
  bad_cut: 'badge-warning',
  skipped: 'badge-ghost',
  pendiente: 'badge-warning',
  revisada: 'badge-success',
  dudosa: 'badge-warning',
  corregida: 'badge-info',
  encolado: 'badge-ghost',
  procesando: 'badge-info',
  completado: 'badge-success',
  fallido: 'badge-error',
  cancelado: 'badge-ghost',
};

export function Badge({ estado }: { estado: string }) {
  const cls = badgeStyles[estado] ?? 'badge-ghost';
  const labels: Record<string, string> = { auto: 'Sin revisar', confirmed: 'Confirmada', corrected: 'Corregida', illegible: 'Ilegible', bad_cut: 'Recorte incorrecto', skipped: 'Omitida' };
  return <span className={`badge ${cls}`}>{labels[estado] ?? estado}</span>;
}

export function ArchiveMark() {
  return <Archive size={16} />;
}
