import { useEffect, useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Search, ZoomIn, ZoomOut, Download, ChevronLeft, ChevronRight, Pencil } from 'lucide-react';
import { api } from '../../lib/axios';
import { Loading, ErrorState, Empty, Badge } from '../../components/ui/Common';
import OcrReview from './OcrReview';
type DocItem = { id: string; title: string; doc_type: string; pages: number };
type PageItem = { id: string; order: number; folio?: string | null; status: string };
type LineItem = { id: string; order: number; auto_text: string; revised_text: string | null; state: 'auto' | 'confirmed' | 'corrected' | 'illegible' | 'bad_cut' | 'skipped'; confidence: number | null; version: number };
type Paginated<T> = { items: T[] };

type DocDetail = DocItem & { pages: PageItem[] };

export default function Documents() {
  const qc = useQueryClient();
  const [q, setQ] = useState('');
  const [debounced, setDebounced] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 350);
    return () => clearTimeout(t);
  }, [q]);

  const docs = useQuery({
    queryKey: ['documents', debounced],
    queryFn: async () => {
      const { data } = await api.get<Paginated<DocItem> | DocItem[]>('/documents', { params: debounced ? { q: debounced } : {} });
      if (Array.isArray(data)) return data;
      return data.items;
    },
  });

  const items = useMemo(() => docs.data ?? [], [docs.data]);

  useEffect(() => {
    if (!selectedId && items.length > 0) setSelectedId(items[0].id);
  }, [items, selectedId]);

  return (
    <div className="mx-auto max-w-7xl">
      <h1 className="archivo-titulo text-3xl font-bold">Mis documentos</h1>
      <p className="mt-1 text-sm text-tinta-suave">Busca, revisa la imagen junto al texto y corrige renglón por renglón.</p>

      <div className="mt-4 flex items-center gap-2">
        <div className="relative w-full max-w-md">
          <Search size={16} className="absolute left-3 top-3 text-tinta-clara" />
          <input className="input input-bordered w-full pl-9" placeholder="Buscar por título…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <button className="btn btn-ghost btn-sm" onClick={() => { setQ(''); qc.invalidateQueries({ queryKey: ['documents'] }); }}>Limpiar</button>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[320px_1fr]">
        <div className="papel max-h-[70vh] overflow-auto rounded-xl p-2">
          {docs.isLoading && <Loading texto="Cargando documentos…" />}
          {docs.isError && <ErrorState titulo="No se pudo cargar la lista" reintentar={() => docs.refetch()} />}
          {!docs.isLoading && items.length === 0 && <Empty texto="No hay documentos. Digitaliza el primero." />}
          {items.map((d) => (
            <button
              key={d.id}
              onClick={() => setSelectedId(d.id)}
              className={`mb-1 w-full rounded-md p-3 text-left ${selectedId === d.id ? 'bg-bosque-600 text-pergamino-50' : 'hover:bg-pergamino-100'}`}
            >
              <p className="truncate text-sm font-semibold">{d.title}</p>
              <p className={`text-xs ${selectedId === d.id ? 'text-pergamino-200' : 'text-tinta-clara'}`}>{d.doc_type} · {d.pages} pág.</p>

            </button>
          ))}
        </div>

        <div className="min-w-0">
          {!selectedId ? (
            <Empty texto="Elige un documento de la lista." />
          ) : (
            <Viewer key={selectedId} documentId={selectedId} />
          )}
        </div>
      </div>
    </div>
  );
}

function Viewer({ documentId }: { documentId: string }) {
  const qc = useQueryClient();
  const [pageIdx, setPageIdx] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [activeLine, setActiveLine] = useState<string | null>(null);
  const [hasOcr, setHasOcr] = useState(false);
  const [exportState, setExportState] = useState('');

  const doc = useQuery({
    queryKey: ['document', documentId],
    queryFn: async () => (await api.get<DocDetail>(`/documents/${documentId}`)).data,
  });

  useEffect(() => setPageIdx(0), [documentId]);

  const pages = doc.data?.pages ?? [];
  const page = pages[pageIdx];

  const lines = useQuery({
    queryKey: ['lines', page?.id],
    queryFn: async () => (await api.get<{items: LineItem[]}>(`/pages/${page!.id}/lines`)).data.items,
    enabled: !!page?.id,
  });

  const saveFolio = useMutation({
    mutationFn: async (folio: string) => (await api.patch<PageItem>(`/pages/${page!.id}`, { folio })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['document', documentId] }),
  });


  async function exportar(formato: 'json' | 'pdf-lectura' | 'pdf-facsimil' | 'docx') {
    if (exportState) return;
    setExportState('Preparando descarga…');
    try {
    const { data } = await api.post<{ job_id: string }>(`/exports`, { document_id: documentId, format: formato });
    const jobId = data.job_id;
    // Espera simple y descarga
    for (let i = 0; i < 30; i++) {
      await new Promise((r) => setTimeout(r, 1500));
      try {
        const res = await api.get(`/exports/${jobId}/download`, { responseType: 'blob' });
        const url = URL.createObjectURL(res.data);
        const a = document.createElement('a');
        a.href = url;
        const nombre = (doc.data?.title || 'documento').replace(/[<>:"/\\|?*\x00-\x1f]/g, '_').replace(/[. ]+$/, '').trim().slice(0, 120) || 'documento';
        a.download = `${nombre}${formato === 'pdf-facsimil' ? '-facsimil' : ''}.${formato.startsWith('pdf-') ? 'pdf' : formato}`;
        a.click();
        // El navegador puede necesitar el objeto después de que termine el clic.
        setTimeout(() => URL.revokeObjectURL(url), 60_000);
        setExportState('');
        return;
      } catch {
        const job = await api.get<{status: string; error?: string}>(`/jobs/${jobId}`);
        if (job.data.status === 'FAILED' || job.data.status === 'CANCELLED') throw new Error(job.data.error || 'La exportación no pudo completarse');
      }
    }
    throw new Error('La exportación está demorando. Volvé a intentarlo en unos momentos.');
    } catch (e) { setExportState(''); alert(e instanceof Error ? e.message : 'No se pudo exportar el documento'); }
  }

  if (doc.isLoading) return <Loading texto="Abriendo documento…" />;
  if (doc.isError || !doc.data) return <ErrorState titulo="No se pudo abrir el documento" reintentar={() => doc.refetch()} />;
  if (!page) return <Empty texto="Este documento aún no tiene páginas." />;

  return (
    <div className="papel rounded-xl p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="archivo-titulo text-xl font-bold">{doc.data.title}</h2>

        <span className="ml-auto flex items-center gap-1">
          {exportState && <span role="status" className="text-xs">{exportState}</span>}
          <button disabled={!!exportState} className="btn btn-ghost btn-xs" onClick={() => exportar('json')}><Download size={14} /> JSON</button>
          <button disabled={!!exportState} className="btn btn-ghost btn-xs" onClick={() => exportar('pdf-lectura')}><Download size={14} /> PDF lectura</button>
          <button disabled={!!exportState} className="btn btn-ghost btn-xs" onClick={() => exportar('pdf-facsimil')}><Download size={14} /> PDF con imágenes</button>
          <button disabled={!!exportState} className="btn btn-ghost btn-xs" onClick={() => exportar('docx')}><Download size={14} /> Word</button>
        </span>
      </div>

      {/* Miniaturas paginadas */}
      <div className="visor-scroll mt-3 flex gap-2 overflow-x-auto pb-2">
        {pages.map((p, i) => (
          <button key={p.id} onClick={() => setPageIdx(i)} className={`shrink-0 rounded border-2 ${i === pageIdx ? 'border-bosque-600' : 'border-transparent'}`}>
            <img src={`/api/v1/pages/${p.id}/image?thumbnail=1`} alt={`Página ${(p.order + 1)}`} className="h-16 w-12 object-cover rounded" loading="lazy" />
            <p className="text-center text-[11px]">{p.folio || `p. ${(p.order + 1)}`}</p>
          </button>
        ))}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
        <button className="btn btn-ghost btn-xs" disabled={pageIdx === 0} onClick={() => setPageIdx((i) => i - 1)}><ChevronLeft size={14} /> Anterior</button>
        <span>Página {pageIdx + 1} de {pages.length} · Folio: <FolioEditor key={page.id} initial={page.folio ?? ''} onSave={(f) => saveFolio.mutate(f)} /></span>
        <button className="btn btn-ghost btn-xs" disabled={pageIdx >= pages.length - 1} onClick={() => setPageIdx((i) => i + 1)}>Siguiente <ChevronRight size={14} /></button>
        <span className="ml-auto flex items-center gap-1">
          <button className="btn btn-ghost btn-xs" onClick={() => setZoom((z) => Math.max(0.5, +(z - 0.25).toFixed(2)))}><ZoomOut size={14} /></button>
          <span className="text-xs">{Math.round(zoom * 100)}%</span>
          <button className="btn btn-ghost btn-xs" onClick={() => setZoom((z) => Math.min(3, +(z + 0.25).toFixed(2)))}><ZoomIn size={14} /></button>
        </span>
      </div>

      <div className="mt-3 grid gap-4 md:grid-cols-2">
        <div className="overflow-auto rounded-md border border-pergamino-200 bg-white p-2" style={{ maxHeight: 520 }}>
          <img
            src={`/api/v1/pages/${page.id}/image`}
            alt={`Página ${(page.order + 1)}`}
            style={{ width: `${zoom * 100}%` }}
            className="mx-auto max-w-none rounded"
          />
        </div>
        <div className="overflow-auto rounded-md border border-pergamino-200 bg-white p-2" style={{ maxHeight: 520 }}>
          <OcrReview key={page.id} pageId={page.id} onAvailability={setHasOcr} />
          {hasOcr && !!lines.data?.length && <p className="mt-5 border-t border-pergamino-200 pt-3 text-xs font-semibold text-tinta-suave">Renglones de Kraken conservados de una lectura anterior; sus correcciones siguen guardadas.</p>}
          {lines.isLoading && <Loading texto="Cargando renglones…" />}
          {lines.isError && <ErrorState titulo="No se pudieron cargar los renglones" reintentar={() => lines.refetch()} />}
          {(lines.data ?? []).map((l) => (
            <LineRow key={l.id} line={l} active={activeLine === l.id} onFocus={() => setActiveLine(l.id)} />
          ))}
          {!hasOcr && lines.data && lines.data.length === 0 && <Empty texto="Sin renglones transcritos todavía." />}
        </div>
      </div>
    </div>
  );
}

function FolioEditor({ initial, onSave }: { initial: string; onSave: (v: string) => void }) {
  const [v, setV] = useState(initial);
  const [edit, setEdit] = useState(false);
  useEffect(() => setV(initial), [initial]);
  if (!edit) {
    return (
      <span className="inline-flex items-center gap-1">
        <strong>{v || '—'}</strong>
        <button className="btn btn-ghost btn-xs" onClick={() => setEdit(true)}><Pencil size={12} /></button>
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1">
      <input className="input input-bordered input-xs w-24" value={v} onChange={(e) => setV(e.target.value)} />
      <button className="btn btn-primary btn-xs" onClick={() => { onSave(v); setEdit(false); }}>Guardar</button>
    </span>
  );
}

function LineRow({ line, active, onFocus }: { line: LineItem; active: boolean; onFocus: () => void }) {
  const qc = useQueryClient();
  const [texto, setTexto] = useState((line.revised_text ?? line.auto_text));
  const [estado, setEstado] = useState(line.state);
  const [edit, setEdit] = useState(false);
  useEffect(() => { setTexto((line.revised_text ?? line.auto_text)); setEstado(line.state); }, [line]);

  const save = useMutation({
    mutationFn: async () => (await api.patch<LineItem>(`/lines/${line.id}`, { revised_text: texto, state: estado, version: line.version })).data,
    onSuccess: () => {
      setEdit(false);
      qc.invalidateQueries({ queryKey: ['lines'] });
    },
  });

  return (
    <div
      onClick={onFocus}
      className={`mb-1 rounded p-2 text-sm ${active ? 'renglon-activo bg-white' : ''} ${estado === 'illegible' || estado === 'bad_cut' ? 'linea-dudosa' : estado === 'confirmed' || estado === 'corrected' ? 'linea-revisada bg-white' : 'bg-pergamino-50'}`}
    >
      <div className="flex items-center gap-2">
        <span className="text-xs text-tinta-clara">#{(line.order + 1)}</span>
        <Badge estado={estado} />
        {typeof line.confidence === 'number' && <span className="text-xs text-tinta-clara">{Math.round(line.confidence * 100)}%</span>}
        <button className="btn btn-ghost btn-xs ml-auto" onClick={() => setEdit((e) => !e)}><Pencil size={12} /> {edit ? 'Cerrar' : 'Editar'}</button>
      </div>
      {edit ? (
        <div className="mt-1 flex flex-col gap-1">
          <textarea className="textarea textarea-bordered textarea-sm" value={texto} onChange={(e) => setTexto(e.target.value)} rows={2} />
          <div className="flex items-center gap-1">
            <select className="select select-bordered select-xs" value={estado} onChange={(e) => setEstado(e.target.value as LineItem['state'])}>
              <option value="auto">Sin revisar</option>
              <option value="confirmed">Confirmada</option>
              <option value="corrected">Corregida</option>
              <option value="illegible">Ilegible</option>
              <option value="bad_cut">Recorte incorrecto</option>
              <option value="skipped">Omitida</option>
            </select>
            <button className="btn btn-primary btn-xs" disabled={save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Guardando…' : 'Guardar'}</button>
          </div>
          {save.isError && <p className="text-xs text-error">No se pudo guardar.</p>}
        </div>
      ) : (
        <p className="mt-1 whitespace-pre-wrap">{texto || <span className="italic text-tinta-clara">(vacío)</span>}</p>
      )}
    </div>
  );
}
