import { useState, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ArrowLeft, ArrowRight, BookOpen, FileText, UploadCloud, Trash2, MoveUp, MoveDown, CheckCircle2 } from 'lucide-react';
import { api } from '../../lib/axios';
import { Loading, ErrorState } from '../../components/ui/Common';

type Collection = { id: string; title: string };
type Job = { status: string; phase: string; done: number; total: number; error?: string; device?: 'cpu' | 'cuda' };
type Processing = { preferred: 'auto' | 'cpu' | 'cuda'; effective: 'cpu' | 'cuda' | null; ocr_mode: 'kraken' | 'paddleocr_vl' | 'dual'; paddle: { ready: boolean; device: 'cpu' | 'cuda' | null } };
type Scan = { id: string; file: File; done: boolean; error?: string; progress: number };
const steps = ['Organizar', 'Agregar archivos', 'Revisar y comenzar', 'Progreso'];
const message = (error: any) => error?.response?.data?.error || error?.message || 'Ocurrió un error inesperado';

export default function Wizard() {
  const qc = useQueryClient();
  const [step, setStep] = useState(0);
  const [mode, setMode] = useState<'document' | 'collection'>('document');
  const [title, setTitle] = useState('');
  const [collectionId, setCollectionId] = useState('');
  const [collectionTitle, setCollectionTitle] = useState('');
  const [scans, setScans] = useState<Scan[]>([]);
  const [docId, setDocId] = useState<string | null>(null);
  const [createdCollection, setCreatedCollection] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const collections = useQuery({ queryKey: ['collections'], queryFn: async () => (await api.get<{items: Collection[]}>('/collections')).data.items });
  const processing = useQuery({ queryKey: ['processing-settings'], queryFn: async () => (await api.get<Processing>('/settings/processing')).data, enabled: step === 2 });
  const job = useQuery({ queryKey: ['job', jobId], queryFn: async () => (await api.get<Job>(`/jobs/${jobId}`)).data,
    enabled: !!jobId, refetchInterval: q => ['COMPLETED', 'FAILED', 'CANCELLED'].includes((q.state.data as Job | undefined)?.status || '') ? false : 2000 });
  const retry = useMutation({
    mutationFn: async () => api.post(`/jobs/${jobId}/retry`),
    onSuccess: () => { setError(''); qc.invalidateQueries({ queryKey: ['job', jobId] }); },
    onError: e => setError(message(e)),
  });
  function addFiles(files: FileList | File[]) {
    const valid = Array.from(files).filter(f => /\.(jpe?g|png|tiff?|pdf)$/i.test(f.name));
    if (valid.length !== files.length) setError('Algunos archivos no son compatibles. Elegí JPG, PNG, TIFF o PDF.'); else setError('');
    setScans(s => [...s, ...valid.map(file => ({ id: `${Date.now()}-${Math.random().toString(36).slice(2)}`, file, done: false, progress: 0 }))]);
    if (inputRef.current) inputRef.current.value = '';
  }
  function move(index: number, direction: number) {
    setScans(items => { const next = [...items]; const target = index + direction; if (target < 0 || target >= next.length) return items; [next[index], next[target]] = [next[target], next[index]]; return next; });
  }
  async function start() {
    if (busy) return;
    setBusy(true); setError('');
    try {
      let col = mode === 'collection' ? createdCollection : collectionId;
      if (mode === 'collection' && !col) {
        col = (await api.post<{id: string}>('/collections', { title: collectionTitle.trim() })).data.id;
        setCreatedCollection(col); qc.invalidateQueries({ queryKey: ['collections'] });
      }
      let id = docId;
      if (!id) {
        id = (await api.post<{id: string}>('/documents', { title: title.trim(), doc_type: 'libro', collection_id: col || null })).data.id;
        setDocId(id); qc.invalidateQueries({ queryKey: ['documents'] });
      }
      let failed = false;
      for (const scan of scans) {
        if (scan.done) continue;
        setScans(items => items.map(s => s.id === scan.id ? { ...s, error: undefined } : s));
        try {
          const form = new FormData(); form.append('file', scan.file);
          const res = await api.post<{added: unknown[]; duplicates: unknown[]; errors: {error: string}[]}>(`/documents/${id}/upload`, form, {
            timeout: 0, onUploadProgress: e => setScans(items => items.map(s => s.id === scan.id ? { ...s, progress: e.total ? Math.round(e.loaded / e.total * 100) : 0 } : s))
          });
          if (res.data.errors.length) throw new Error(res.data.errors.map(e => e.error).join('; '));
          if (!res.data.added.length && !res.data.duplicates.length) throw new Error('No se pudo importar el archivo');
          setScans(items => items.map(s => s.id === scan.id ? { ...s, done: true, progress: 100 } : s));
        } catch (e) { failed = true; setScans(items => items.map(s => s.id === scan.id ? { ...s, error: message(e) } : s)); break; }
      }
      if (failed) { setError('Algunos archivos no se pudieron importar. Revisá el detalle y volvé a intentar. Los archivos guardados no se subirán otra vez.'); return; }
      const result = await api.post<{job_id: string}>('/jobs/transcribe', { document_id: id });
      setJobId(result.data.job_id); setStep(3);
    } catch (e) { setError(message(e)); } finally { setBusy(false); }
  }
  function reset() { setStep(0); setTitle(''); setCollectionTitle(''); setCollectionId(''); setScans([]); setDocId(null); setCreatedCollection(null); setJobId(null); setError(''); }
  const done = job.data?.done || 0, total = job.data?.total || 0;
  const method = processing.data;
  const processingLabel = !method ? 'Según configuración' : method.ocr_mode === 'kraken'
    ? `Kraken · ${method.effective === 'cuda' ? 'GPU NVIDIA' : method.effective === 'cpu' ? 'CPU' : 'GPU no disponible'}`
    : `${method.ocr_mode === 'dual' ? 'Análisis doble' : 'PaddleOCR-VL'} · ${method.paddle.ready ? (method.paddle.device === 'cuda' ? 'GPU NVIDIA' : 'CPU') : 'preparación pendiente'}`;
  const status: Record<string, string> = { PENDING: 'En espera', QUEUED: 'En espera', STARTED: 'En proceso', RUNNING: 'En proceso', COMPLETED: 'Transcripción terminada', FAILED: 'No se pudo completar', CANCELLED: 'Cancelado' };
  return <div className="mx-auto max-w-5xl">
    <div className="wizard-hero"><div><p className="eyebrow">TU ARCHIVO, MÁS CERCA</p><h1 className="archivo-titulo mt-2 text-4xl font-bold">Dar vida a tus documentos</h1><p className="mt-3 max-w-xl text-sm leading-6 text-tinta-suave">Reuní tus páginas, dejá que el lector las transcriba y revisá el resultado a tu ritmo.</p></div><div className="hero-mark" aria-hidden="true"><BookOpen size={62} strokeWidth={1} /></div></div>
    <ol className="wizard-steps" aria-label="Pasos de digitalización">{steps.map((s, i) => <li key={s} className={i === step ? 'current' : i < step ? 'complete' : ''}><span>{i + 1}</span>{s}</li>)}</ol>
    <div className="papel wizard-panel">
      {step === 0 && <div><p className="eyebrow">PASO 01 · EMPEZAR</p><h2 className="archivo-titulo mt-2 text-2xl font-bold">¿Qué querés organizar?</h2><p className="mt-1 text-sm text-tinta-suave">Una colección reúne varios documentos. Podrás agregar más documentos después.</p>
        <div className="choice-grid mt-5"><button type="button" className={`choice ${mode === 'document' ? 'selected' : ''}`} onClick={() => setMode('document')}><FileText size={24}/><strong>Un documento</strong><span>Una carta, expediente o libro con una o varias páginas.</span></button><button type="button" className={`choice ${mode === 'collection' ? 'selected' : ''}`} onClick={() => setMode('collection')}><BookOpen size={24}/><strong>Una colección</strong><span>Creá una colección y agregá su primer documento.</span></button></div>
        <div className="mt-6 grid gap-4 sm:grid-cols-2">{mode === 'collection' ? <label className="form-control gap-2"><span className="label-text font-semibold">Nombre de la colección</span><input className="input input-bordered" value={collectionTitle} onChange={e => setCollectionTitle(e.target.value)} placeholder="Ej. Archivo de la familia" /></label> : <label className="form-control gap-2"><span className="label-text font-semibold">Colección existente (opcional)</span><select className="select select-bordered" value={collectionId} onChange={e => setCollectionId(e.target.value)}><option value="">Sin colección</option>{collections.data?.map(c => <option key={c.id} value={c.id}>{c.title}</option>)}</select>{collections.isError && <span className="text-xs text-error">No se pudieron cargar las colecciones. <button className="underline" onClick={() => collections.refetch()}>Reintentar</button></span>}</label>}<label className="form-control gap-2"><span className="label-text font-semibold">Nombre del documento</span><input className="input input-bordered" value={title} onChange={e => setTitle(e.target.value)} placeholder="Ej. Cartas de 1923" /></label></div></div>}
      {step === 1 && <div><p className="eyebrow">PASO 02 · TUS PÁGINAS</p><h2 className="archivo-titulo mt-2 text-2xl font-bold">Agregá los escaneos</h2><p className="mt-1 text-sm text-tinta-suave">Elegí uno o varios archivos. Los PDF y TIFF de varias páginas se separan automáticamente.</p><div className="upload-zone mt-5" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); addFiles(e.dataTransfer.files); }}><UploadCloud size={30}/><strong>Arrastrá tus archivos aquí</strong><span>JPG, PNG, TIFF o PDF · hasta 512 MB por archivo</span><button className="btn btn-primary btn-sm mt-2" onClick={() => inputRef.current?.click()}>Elegir archivos</button><input ref={inputRef} type="file" accept=".jpg,.jpeg,.png,.tif,.tiff,.pdf" multiple className="hidden" onChange={e => e.target.files && addFiles(e.target.files)}/></div><div className="mt-4 space-y-2">{scans.map((s, i) => <div key={s.id} className="scan-row"><span className="scan-number">{i + 1}</span><div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold">{s.file.name}</p><p className="text-xs text-tinta-suave">{(s.file.size / 1024 / 1024).toFixed(1)} MB {s.done && '· Guardado'}</p>{s.error && <p className="text-xs text-error">{s.error}</p>}{busy && !s.done && s.progress > 0 && <progress className="progress progress-primary w-full" value={s.progress} max={100}/>}</div><button className="btn btn-ghost btn-xs" disabled={!!docId || i === 0} onClick={() => move(i,-1)} aria-label="Mover arriba"><MoveUp size={16}/></button><button className="btn btn-ghost btn-xs" disabled={!!docId || i === scans.length-1} onClick={() => move(i,1)} aria-label="Mover abajo"><MoveDown size={16}/></button><button className="btn btn-ghost btn-xs" disabled={s.done} onClick={() => setScans(a => a.filter(x => x.id !== s.id))} aria-label="Quitar archivo"><Trash2 size={16}/></button></div>)}</div><p className="mt-3 text-xs text-tinta-suave">{docId ? 'Los archivos guardados conservan su orden. Podés quitar los que fallaron o agregar otros.' : 'Ordená los archivos antes de continuar. Las páginas dentro de cada archivo conservarán su orden.'}</p></div>}
      {step === 2 && <div><p className="eyebrow">PASO 03 · CONFIRMACIÓN</p><h2 className="archivo-titulo mt-2 text-2xl font-bold">Todo listo para comenzar</h2><p className="mt-2 text-sm text-tinta-suave">Primero guardaremos los archivos y luego comenzará la lectura. Podés seguir su progreso aquí.</p><dl className="summary-list mt-5"><div><dt>Documento</dt><dd>{title}</dd></div><div><dt>Colección</dt><dd>{mode === 'collection' ? collectionTitle : collections.data?.find(c => c.id === collectionId)?.title || 'Sin colección'}</dd></div><div><dt>Archivos</dt><dd>{scans.length}</dd></div><div><dt>Procesamiento</dt><dd>{processingLabel}</dd></div></dl>{busy && <Loading texto="Guardando archivos e iniciando la lectura…"/>}{scans.filter(s => s.error).map(s => <p key={s.id} className="mt-2 text-sm text-error">{s.file.name}: {s.error}</p>)}</div>}
      {step === 3 && <div className="py-5 text-center"><CheckCircle2 className="mx-auto text-bosque-600" size={42}/><h2 className="archivo-titulo mt-4 text-2xl font-bold">{job.data ? status[job.data.status] || job.data.status : 'Preparando la lectura'}</h2>{job.isError && <ErrorState titulo="No se pudo consultar el progreso" reintentar={() => job.refetch()}/>}<p className="mt-2 text-sm text-tinta-suave">{job.data?.phase || 'El trabajo continúa aunque salgas de esta pantalla.'}</p>{job.data?.device && <p className="mt-1 text-xs text-tinta-clara">Procesamiento: {job.data.device === 'cuda' ? 'GPU NVIDIA' : 'CPU'}</p>}{job.data && <div className="mx-auto mt-4 max-w-md"><progress className="progress progress-primary w-full" value={done} max={total || 1}/><p className="text-sm">{done} de {total} páginas procesadas</p>{job.data.error && <p className="mt-2 text-sm text-error">{job.data.error}</p>}</div>}<div className="mt-6 flex justify-center gap-2">{job.data?.status === 'FAILED' && <button className="btn btn-primary" disabled={retry.isPending} onClick={() => retry.mutate()}>{retry.isPending ? 'Reintentando…' : 'Reintentar lectura'}</button>}<Link to="/documentos" className="btn btn-primary">Abrir mis documentos</Link><button className="btn btn-ghost" onClick={reset}>Digitalizar otro</button></div></div>}
      {error && <div role="alert" className="alert alert-error mt-4 text-sm">{error}</div>}
      {step < 3 && <div className="mt-8 flex justify-between border-t border-pergamino-200 pt-5"><button className="btn btn-ghost" disabled={step === 0 || busy || (step === 1 && !!docId)} onClick={() => { setError(''); setStep(step - 1); }}><ArrowLeft size={16}/> Atrás</button>{step < 2 ? <button className="btn btn-primary" disabled={step === 0 ? !title.trim() || (mode === 'collection' && !collectionTitle.trim()) : !scans.length} onClick={() => { setError(''); setStep(step + 1); }}>Continuar <ArrowRight size={16}/></button> : <button className="btn btn-primary" disabled={busy} onClick={start}>{busy ? 'Guardando…' : docId ? 'Reintentar y comenzar' : 'Guardar y transcribir'} <ArrowRight size={16}/></button>}</div>}
    </div></div>;
}
