import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Cpu, DownloadCloud, Power, Ban, RotateCcw, Activity } from 'lucide-react';
import { api } from '../../lib/axios';
import { Loading, ErrorState, Empty, Badge } from '../../components/ui/Common';
import type { ModelInfo, ReaderStatus, JobItem } from '../../types';

export default function Admin() {
  const qc = useQueryClient();

  const models = useQuery({
    queryKey: ['models'],
    queryFn: async () => (await api.get<ModelInfo[]>('/models')).data,
  });

  const status = useQuery({
    queryKey: ['reader-status'],
    queryFn: async () => (await api.get<ReaderStatus>('/reader/status')).data,
    refetchInterval: 10000,
  });

  const downloadBase = useMutation({
    mutationFn: async () => (await api.post<JobItem>('/models/download-base', {})).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['models'] }),
  });

  const activate = useMutation({
    mutationFn: async (id: string) => (await api.post(`/models/${id}/activate`, {})).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['models'] });
      qc.invalidateQueries({ queryKey: ['reader-status'] });
    },
  });

  const cancelJob = useMutation({
    mutationFn: async (id: string) => (await api.post(`/jobs/${id}/cancel`, {})).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-jobs'] }),
  });

  const retryJob = useMutation({
    mutationFn: async (id: string) => (await api.post(`/jobs/${id}/retry`, {})).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-jobs'] }),
  });

  return (
    <div className="mx-auto max-w-6xl">
      <h1 className="archivo-titulo text-3xl font-bold">Administración</h1>
      <p className="mt-1 text-sm text-tinta-suave">Modelos de lectura, diagnóstico del motor y trabajos del sistema.</p>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <section className="papel rounded-xl p-4">
          <h2 className="flex items-center gap-2 font-bold"><Cpu size={18} /> Modelos</h2>
          <button className="btn btn-primary btn-sm mt-2 gap-1" disabled={downloadBase.isPending} onClick={() => downloadBase.mutate()}>
            <DownloadCloud size={15} /> {downloadBase.isPending ? 'Descargando…' : 'Descargar modelo base'}
          </button>
          {downloadBase.data && <p className="mt-1 text-xs">Trabajo: {downloadBase.data.id} · {downloadBase.data.estado}</p>}
          <div className="mt-3">
            {models.isLoading && <Loading texto="Cargando modelos…" />}
            {models.isError && <ErrorState titulo="No se pudieron cargar los modelos" reintentar={() => models.refetch()} />}
            {(models.data ?? []).length === 0 && !models.isLoading && <Empty texto="No hay modelos registrados." />}
            {(models.data ?? []).map((m) => (
              <div key={m.id} className="mb-2 flex items-center gap-2 rounded-md border border-pergamino-200 bg-white p-2 text-sm">
                <div>
                  <p className="font-semibold">{m.nombre} <span className="text-tinta-clara">v{m.version}</span></p>
                  <p className="text-xs text-tinta-suave">{m.activo ? '● activo' : 'inactivo'}{typeof m.cer === 'number' ? ` · CER ${m.cer.toFixed(3)}` : ''}</p>
                </div>
                {!m.activo && (
                  <button className="btn btn-ghost btn-xs ml-auto gap-1" disabled={activate.isPending} onClick={() => activate.mutate(m.id)}>
                    <Power size={13} /> Activar
                  </button>
                )}
                {m.activo && <span className="badge badge-success ml-auto">en uso</span>}
              </div>
            ))}
          </div>
        </section>

        <section className="papel rounded-xl p-4">
          <h2 className="flex items-center gap-2 font-bold"><Activity size={18} /> Diagnóstico del lector</h2>
          {status.isLoading && <Loading texto="Consultando motor…" />}
          {status.isError && <ErrorState titulo="Sin respuesta del motor" reintentar={() => status.refetch()} />}
          {status.data && (
            <dl className="mt-2 grid grid-cols-2 gap-2 text-sm">
              <div className="rounded bg-white p-2"><dt className="text-tinta-clara">Motor</dt><dd className="font-semibold">{status.data.motor}</dd></div>
              <div className="rounded bg-white p-2"><dt className="text-tinta-clara">Modelo activo</dt><dd className="font-semibold">{status.data.modelo_activo ?? '—'}</dd></div>
              <div className="rounded bg-white p-2"><dt className="text-tinta-clara">GPU (CUDA)</dt><dd className="font-semibold">{status.data.cuda ? 'Sí' : 'No'}</dd></div>
              <div className="rounded bg-white p-2"><dt className="text-tinta-clara">En cola</dt><dd className="font-semibold">{status.data.cola}</dd></div>
            </dl>
          )}
          <JobsPanel onCancel={(id) => cancelJob.mutate(id)} onRetry={(id) => retryJob.mutate(id)} />
        </section>
      </div>
    </div>
  );
}

function JobsPanel({ onCancel, onRetry }: { onCancel: (id: string) => void; onRetry: (id: string) => void }) {
  const jobs = useQuery({
    queryKey: ['admin-jobs'],
    queryFn: async () => {
      // Reutiliza la lista de documentos para descubrir trabajos recientes vía eventos;
      // si el backend expone /jobs/:id, consultamos trabajos conocidos desde documentos.
      // Como no hay endpoint de listado, mostramos trabajos seguidos en esta sesión.
      const raw = sessionStorage.getItem('admin-jobs-seen');
      const ids: string[] = raw ? JSON.parse(raw) : [];
      const out: JobItem[] = [];
      for (const id of ids.slice(-10)) {
        try {
          const { data } = await api.get<JobItem>(`/jobs/${id}`);
          out.push(data);
        } catch {
          /* ignora */
        }
      }
      return out;
    },
  });

  const events = useQuery({
    queryKey: ['admin-job-events'],
    queryFn: async () => {
      const raw = sessionStorage.getItem('admin-jobs-seen');
      const ids: string[] = raw ? JSON.parse(raw) : [];
      if (!ids.length) return [] as { job: string; events: unknown[] }[];
      const last = ids[ids.length - 1];
      try {
        const { data } = await api.get(`/jobs/${last}/events`);
        return [{ job: last, events: Array.isArray(data) ? data : [] }];
      } catch {
        return [];
      }
    },
    refetchInterval: 5000,
  });

  if (jobs.isLoading) return <Loading texto="Buscando trabajos…" />;
  return (
    <div className="mt-4">
      <h3 className="text-sm font-bold">Trabajos recientes (esta sesión)</h3>
      {(jobs.data ?? []).length === 0 && <p className="mt-1 text-xs text-tinta-suave">Aquí aparecerán los trabajos que lances (transcripciones, descargas, mejoras). Su identificador se guarda en esta pestaña.</p>}
      {(jobs.data ?? []).map((j) => (
        <div key={j.id} className="mb-1 flex items-center gap-2 rounded border border-pergamino-200 bg-white p-2 text-xs">
          <span className="truncate font-mono">{j.id.slice(0, 8)}… · {j.tipo}</span>
          <Badge estado={j.estado} />
          <span>{j.progreso}%</span>
          <span className="ml-auto flex gap-1">
            <button className="btn btn-ghost btn-xs gap-1" onClick={() => onCancel(j.id)}><Ban size={12} /> Cancelar</button>
            <button className="btn btn-ghost btn-xs gap-1" onClick={() => onRetry(j.id)}><RotateCcw size={12} /> Reintentar</button>
          </span>
        </div>
      ))}
      {(events.data ?? []).map((e) => (
        <details key={e.job} className="mt-2 text-xs">
          <summary className="cursor-pointer text-tinta-suave">Eventos de {String(e.job).slice(0, 8)}…</summary>
          <pre className="mt-1 max-h-32 overflow-auto rounded bg-tinta p-2 text-[11px] text-pergamino-100">{JSON.stringify(e.events, null, 2)}</pre>
        </details>
      ))}
    </div>
  );
}
