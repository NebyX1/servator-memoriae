import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../lib/axios';
import { ErrorState, Loading } from '../../components/ui/Common';

type Engine = { text: string | null; status: string; error: string; device: string; model_version: string; elapsed_seconds?: number | null; fallback_reason?: string | null };
type Chunk = { kind: string; kraken: string; second: string; attention?: string | null };
type Ocr = { available: boolean; job_id: string; mode: 'paddleocr_vl' | 'dual' | 'historical'; engines: { kraken?: Engine; paddleocr_vl?: Engine; historical?: Engine };
  comparison: null | { chunks: Chunk[]; differences: number };
  review: null | { text: string; source: string; version: number; job_id: string; created_at: string } };

export default function OcrReview({ pageId, onAvailability }: { pageId: string; onAvailability: (available: boolean) => void }) {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ['page-ocr', pageId], queryFn: async () => (await api.get<Ocr>(`/pages/${pageId}/ocr`)).data });
  const [text, setText] = useState('');
  const [source, setSource] = useState('manual');
  const [choices, setChoices] = useState<Record<number, 'kraken' | 'second'>>({});
  const [base, setBase] = useState<'kraken' | 'second' | null>(null);
  const [difference, setDifference] = useState(0);
  const editor = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { setText(query.data?.review?.text ?? ''); setSource(query.data?.review?.source ?? 'manual'); setBase(null); setChoices({}); setDifference(0); }, [pageId, query.data?.review?.version]);
  useEffect(() => { onAvailability(query.data?.available === true); }, [onAvailability, query.data?.available]);
  const save = useMutation({ mutationFn: async () => api.post(`/pages/${pageId}/ocr/review`, { job_id: query.data!.job_id, text, source, version: query.data?.review?.version ?? 0 }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['page-ocr', pageId] }); }, });
  if (query.isLoading) return <Loading texto="Cargando lecturas…" />;
  if (query.isError) return <ErrorState titulo="No se pudieron cargar las lecturas" reintentar={() => query.refetch()} />;
  const data = query.data;
  if (!data?.available) return null;
  const secondKey = data.engines.paddleocr_vl ? 'paddleocr_vl' : 'historical';
  const secondLabel = secondKey === 'paddleocr_vl' ? 'PaddleOCR-VL' : 'Lectura histórica';
  const chunks = data.comparison?.chunks ?? [];
  const differences = chunks.map((c, i) => c.kind === 'equal' ? -1 : i).filter(i => i >= 0);
  const assemble = (selected: Record<number, 'kraken' | 'second'>, initial: 'kraken' | 'second') => chunks.map((chunk, index) => chunk[selected[index] ?? initial]).join('');
  const selectEngine = (engine: 'kraken' | 'second') => {
    const candidate = engine === 'kraken' ? data.engines.kraken : data.engines[secondKey];
    if (!candidate || candidate.status !== 'completed') return;
    setBase(engine); setChoices({}); setText(candidate.text ?? ''); setSource(engine === 'second' ? secondKey : 'kraken');
  };
  const choosePart = (index: number, engine: 'kraken' | 'second') => {
    if (!base) return;
    const selected = { ...choices, [index]: engine };
    setChoices(selected); setText(assemble(selected, base)); setSource('mixed');
  };
  const onManual = (value: string) => { setText(value); setSource('manual'); setBase(null); };
  const markIllegible = () => {
    const el = editor.current; const start = el?.selectionStart ?? text.length; const end = el?.selectionEnd ?? start;
    onManual(text.slice(0, start) + '[ilegible]' + text.slice(end));
    el?.focus();
  };
  return <div className="space-y-3 text-sm">
    <div><p className="eyebrow">REVISIÓN DE LA PÁGINA</p><h3 className="archivo-titulo mt-1 text-lg font-bold">{data.mode === 'dual' ? 'Comparar lecturas' : secondLabel}</h3>
      {data.comparison && <p className="mt-1 text-tinta-suave">Encontramos {data.comparison.differences} diferencias entre ambas lecturas. Una diferencia no significa necesariamente un error.</p>}
      {data.review && <p className="mt-1 text-bosque-700">Hay una revisión confirmada{data.review.job_id !== data.job_id ? ' de una lectura anterior' : ''}.</p>}
    </div>
    <div className="grid gap-2 sm:grid-cols-2">{(['kraken', 'second'] as const).map(key => {
      const result = key === 'kraken' ? data.engines.kraken : data.engines[secondKey]; if (!result) return null;
      return <div key={key} className="rounded-lg border border-pergamino-200 bg-pergamino-50 p-3"><div className="flex items-center justify-between gap-2"><strong>{key === 'kraken' ? 'Kraken' : secondLabel}</strong><button className="btn btn-ghost btn-xs" disabled={result.status !== 'completed'} onClick={() => selectEngine(key)}>Elegir lectura</button></div>
        {result.status !== 'completed' ? <p className="mt-2 text-error">No se pudo completar: {result.error}</p> : <><p className="mt-1 text-xs text-tinta-suave">Procesado en {result.device === 'cuda' ? 'GPU NVIDIA' : result.device === 'cpu' ? 'CPU' : 'dispositivo no registrado'}{result.fallback_reason ? ' (alternativa automática)' : ''}{result.elapsed_seconds != null ? ` · ${result.elapsed_seconds.toFixed(1)} s` : ''}</p><p className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap leading-6">{data.comparison ? chunks.map((chunk, i) => <span key={i} title={chunk.attention || undefined} className={chunk.kind === 'equal' ? '' : 'rounded bg-amber-200'}>{chunk[key]}</span>) : result.text}</p></>}
      </div>;
    })}</div>
    {differences.length > 0 && <div className="rounded-lg border border-pergamino-200 p-3"><div className="flex flex-wrap items-center gap-2"><strong>Diferencia {difference + 1} de {differences.length}</strong><button className="btn btn-ghost btn-xs ml-auto" disabled={difference === 0} onClick={() => setDifference(difference - 1)}>Anterior</button><button className="btn btn-ghost btn-xs" disabled={difference === differences.length - 1} onClick={() => setDifference(difference + 1)}>Siguiente</button></div>
      <p className="mt-2 text-tinta-suave">Elegí primero una lectura completa y después cambiá cada fragmento que necesites.</p>
      <p className="mt-2 font-semibold">{chunks[differences[difference]].kind === 'insert' ? `Texto presente solo en ${secondLabel}` : chunks[differences[difference]].kind === 'delete' ? 'Texto presente solo en Kraken' : 'Palabras diferentes'}</p>
      {chunks[differences[difference]].attention && <p className="mt-2 font-semibold text-amber-800">Revisá con atención: {chunks[differences[difference]].attention}. Es una señal orientativa, no una conclusión automática.</p>}
      <div className="mt-2 grid gap-2 sm:grid-cols-2">{(['kraken', 'second'] as const).map(engine => <button key={engine} className="rounded border border-pergamino-200 p-2 text-left hover:bg-pergamino-50 disabled:opacity-50" disabled={!base} onClick={() => choosePart(differences[difference], engine)}><strong>{engine === 'kraken' ? 'Kraken' : secondLabel}</strong><span className="mt-1 block whitespace-pre-wrap">{chunks[differences[difference]][engine] || '(sin texto)'}</span></button>)}</div>
    </div>}
    <label className="block font-semibold" htmlFor={`review-${pageId}`}>Texto para confirmar</label>
    <textarea id={`review-${pageId}`} ref={editor} className="textarea textarea-bordered w-full" rows={8} value={text} onChange={e => onManual(e.target.value)} placeholder="Elegí una lectura o escribí la transcripción revisada." />
    <div className="flex flex-wrap gap-2"><button className="btn btn-ghost btn-sm" onClick={markIllegible}>Marcar [ilegible]</button><button className="btn btn-primary btn-sm ml-auto" disabled={save.isPending || !text.trim()} onClick={() => save.mutate()}>{save.isPending ? 'Guardando…' : 'Confirmar transcripción'}</button></div>
    {save.isSuccess && <p role="status" className="text-bosque-700">Transcripción confirmada y conservada.</p>}
    {save.isError && <p role="alert" className="text-error">No se pudo guardar. Si otra persona revisó la página, actualizá antes de volver a intentarlo.</p>}
  </div>;
}
