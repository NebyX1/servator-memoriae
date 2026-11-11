import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, Cpu, MonitorCog, RefreshCw, Sparkles, Zap } from 'lucide-react';
import { motion } from 'framer-motion';
import { api } from '../../lib/axios';
import { ErrorState, Loading } from '../../components/ui/Common';

type Device = 'auto' | 'cpu' | 'cuda';
type Mode = 'kraken' | 'paddleocr_vl' | 'dual';
type ProcessingStatus = {
  preferred: Device;
  effective: 'cpu' | 'cuda' | null;
  devices: { cpu: { available: boolean }; cuda: { available: boolean; name: string | null }; redis_ok: boolean };
  ocr_mode: Mode;
  paddle: { ready: boolean; device: 'cpu' | 'cuda' | null; expected_device: 'cpu' | 'cuda'; server_online: boolean; files_verified: boolean; fallback_reason?: string | null;
    preparation: null | { id: string; status: string; done: number; total: number; phase: string; error: string } };
};

const labels: Record<Device, string> = { auto: 'Automático', cpu: 'CPU', cuda: 'GPU NVIDIA' };
const modeLabels: Record<Mode, string> = { kraken: 'Kraken', paddleocr_vl: 'PaddleOCR-VL', dual: 'Análisis doble' };

export default function Settings() {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const status = useQuery({
    queryKey: ['processing-settings'],
    queryFn: async () => (await api.get<ProcessingStatus>('/settings/processing')).data,
    refetchInterval: 10_000,
  });
  const update = useMutation({
    mutationFn: async (selection: { device?: Device; ocr_mode?: Mode }) => (await api.put<ProcessingStatus>('/settings/processing', selection)).data,
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: ['processing-settings'] });
      setMessage(''); setError('');
    },
    onSuccess: data => {
      queryClient.setQueryData(['processing-settings'], data);
      setMessage('Preferencia guardada para las próximas transcripciones.');
    },
    onError: (cause: unknown) => {
      const response = cause as { response?: { data?: { error?: string } } };
      setError(response.response?.data?.error || 'No se pudo guardar la preferencia. Volvé a intentarlo.');
      void status.refetch();
    },
  });

  const data = status.data;
  const gpuAvailable = data?.devices.cuda.available ?? false;
  const choices: { value: Device; title: string; detail: string; icon: typeof Cpu; available: boolean }[] = [
    { value: 'auto', title: 'Automático', detail: 'Usa la GPU cuando esté disponible; si no, usa el procesador.', icon: Sparkles, available: true },
    { value: 'cpu', title: 'CPU', detail: 'Usa el procesador de esta computadora. Puede tardar más.', icon: Cpu, available: true },
    { value: 'cuda', title: 'GPU NVIDIA', detail: gpuAvailable ? `Disponible: ${data?.devices.cuda.name || 'NVIDIA'}.` : 'El componente de GPU todavía no está disponible.', icon: Zap, available: gpuAvailable },
  ];

  return <div className="mx-auto max-w-5xl">
    <div className="wizard-hero">
      <div><p className="eyebrow">TU ESPACIO DE TRABAJO</p><h1 className="archivo-titulo mt-2 text-4xl font-bold">Configuración</h1><p className="mt-3 max-w-xl text-sm leading-6 text-tinta-suave">Elegí cómo querés procesar tus documentos. Podés cambiarlo cuando lo necesites.</p></div>
      <div className="hero-mark" aria-hidden="true"><MonitorCog size={58} strokeWidth={1} /></div>
    </div>
    <section className="papel wizard-panel mt-6" aria-labelledby="processing-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><p className="eyebrow">LECTURA DE DOCUMENTOS</p><h2 id="processing-title" className="archivo-titulo mt-2 text-2xl font-bold">Motor de transcripción</h2><p className="mt-2 text-sm text-tinta-suave">Elegí cómo querés que Servator lea tus documentos históricos.</p></div>
        <button className="btn btn-ghost btn-sm gap-2" onClick={() => void status.refetch()} disabled={status.isFetching}><RefreshCw size={15} /> Actualizar estado</button>
      </div>
      {status.isLoading && <div className="mt-6"><Loading texto="Comprobando el equipo…" /></div>}
      {status.isError && <div className="mt-6"><ErrorState titulo="No se pudo comprobar el equipo" reintentar={() => status.refetch()} /></div>}
      {data && <>
        <div className="mt-6 rounded-xl border border-bosque-100 bg-bosque-50 p-4 text-sm text-tinta-suave">
          <p className="font-semibold text-bosque-700">Método actual: {modeLabels[data.ocr_mode]}</p>
          <p className="mt-1">Kraken: {data.devices.cpu.available || gpuAvailable ? 'componente disponible' : 'sin conexión'} · PaddleOCR-VL: {data.paddle.ready ? 'comprobado con una imagen' : !data.paddle.server_online ? 'servicio no disponible' : data.paddle.files_verified ? 'pendiente de comprobación' : 'sin preparar'} · GPU NVIDIA: {gpuAvailable ? 'disponible' : 'no disponible'}</p>
          {!data.devices.redis_ok ? <p className="mt-1 text-sello">No se pudo consultar el estado de los componentes de procesamiento.</p> : !data.devices.cpu.available && data.effective === 'cpu' ? <p className="mt-1 text-sello">El componente de CPU no responde en este momento.</p> : null}
        </div>
        <div className="mt-5 grid gap-3 md:grid-cols-3" role="group" aria-label="Motor de transcripción">{([
          { value: 'kraken' as Mode, title: 'Kraken', detail: 'Reconocimiento especializado de escritura manuscrita. Recomendado para documentos históricos.', features: 'CPU o GPU · Mejora personalizada en desarrollo' },
          { value: 'paddleocr_vl' as Mode, title: 'PaddleOCR-VL', detail: 'Modelo de inteligencia artificial especializado en lectura y comprensión de documentos.', features: 'Versión 1.6 · Local · Dispositivo automático' },
          { value: 'dual' as Mode, title: 'Análisis doble', detail: 'Kraken y PaddleOCR-VL leen el mismo documento para comparar resultados y detectar diferencias.', features: 'Dos propuestas · Comparación · Revisión asistida' },
        ]).map(choice => <motion.button whileHover={{ y: -2 }} whileTap={{ scale: 0.99 }} key={choice.value} type="button" aria-pressed={data.ocr_mode === choice.value} disabled={update.isPending} onClick={() => { if (data.ocr_mode !== choice.value) update.mutate({ ocr_mode: choice.value }); }} className={`choice min-h-48 ${data.ocr_mode === choice.value ? 'selected' : ''}`}><span className="flex w-full items-center justify-between"><Sparkles size={23}/>{data.ocr_mode === choice.value && <CheckCircle2 size={19}/>}</span><strong>{choice.title}</strong><span>{choice.detail}</span><span className="font-semibold">{choice.features}</span></motion.button>)}</div>
        {data.ocr_mode !== 'kraken' && <div className="mt-5 rounded-xl border border-pergamino-200 bg-pergamino-50 p-4 text-sm" role="status">
          {data.paddle.ready ? <p>PaddleOCR-VL comprobado en {data.paddle.device === 'cuda' ? 'GPU NVIDIA' : 'CPU'}. {data.ocr_mode === 'dual' && 'En análisis doble, Kraken usa CPU para reservar la GPU para PaddleOCR-VL.'}</p> : <p>Dispositivo detectado: {data.paddle.expected_device === 'cuda' ? 'GPU NVIDIA' : 'CPU'}. La primera preparación puede demorar; Kraken sigue disponible.</p>}
          {data.paddle.preparation && ['PENDING', 'QUEUED', 'RUNNING'].includes(data.paddle.preparation.status) && <div className="mt-2"><p>{data.paddle.preparation.phase}</p>{data.paddle.preparation.total > 1 && <><progress className="progress progress-success mt-2 w-full" value={data.paddle.preparation.done} max={data.paddle.preparation.total}/><p>{Math.floor(data.paddle.preparation.done / 1048576)} de {Math.ceil(data.paddle.preparation.total / 1048576)} MB</p></>}</div>}
          {data.paddle.preparation?.status === 'FAILED' && <div className="mt-2 text-error"><p>No se pudo preparar PaddleOCR-VL: {data.paddle.preparation.error}</p><button className="btn btn-ghost btn-sm mt-2" disabled={update.isPending} onClick={() => update.mutate({ ocr_mode: data.ocr_mode })}>Reintentar preparación</button></div>}
          {!data.paddle.ready && (!data.paddle.preparation || ['COMPLETED', 'CANCELLED'].includes(data.paddle.preparation.status)) && <button className="btn btn-ghost btn-sm mt-2" disabled={update.isPending} onClick={() => update.mutate({ ocr_mode: data.ocr_mode })}>Preparar y comprobar PaddleOCR-VL</button>}
          {data.paddle.ready && data.paddle.device === 'cpu' && <p className="mt-2 text-tinta-suave">En CPU, la lectura puede tardar considerablemente más.</p>}
          {data.paddle.fallback_reason && <p className="mt-2 text-tinta-suave">No se pudo preparar PaddleOCR-VL en GPU; se comprobó en CPU. Detalle: {data.paddle.fallback_reason}</p>}
        </div>}
        {data.ocr_mode === 'kraken' && <><h3 className="archivo-titulo mt-7 text-xl font-bold">Rendimiento de Kraken</h3><p className="mt-2 text-sm text-tinta-suave">Preferencia actual: {labels[data.preferred]}. {data.effective === 'cuda' ? 'Próximas lecturas: GPU NVIDIA.' : data.effective === 'cpu' ? 'Próximas lecturas: CPU.' : 'La GPU elegida no está disponible.'}</p>
        <div className="mt-5 grid gap-3 md:grid-cols-3" role="group" aria-label="Dispositivo de procesamiento">
          {choices.map(choice => {
            const Icon = choice.icon;
            const selected = data.preferred === choice.value;
            return <button key={choice.value} type="button" aria-pressed={selected}
              disabled={update.isPending || !choice.available}
              onClick={() => { if (!selected) update.mutate({ device: choice.value }); }}
              className={`choice min-h-40 ${selected ? 'selected' : ''} ${!choice.available ? 'cursor-not-allowed opacity-60' : ''}`}>
              <span className="flex w-full items-center justify-between"><Icon size={23} aria-hidden="true"/>{selected && <CheckCircle2 size={19} aria-hidden="true"/>}</span>
              <strong>{choice.title}</strong><span>{choice.detail}</span>
            </button>;
          })}
        </div>
        </>}
        {message && <p role="status" className="mt-4 text-sm text-bosque-700">{message}</p>}
        {error && <p role="alert" className="mt-4 text-sm text-error">{error}</p>}
        <p className="mt-5 text-sm text-tinta-suave">El cambio se guarda al elegir una opción y se aplica a las próximas transcripciones. Las que ya comenzaron continúan igual.</p>
        {data.ocr_mode === 'kraken' && !gpuAvailable && <details className="mt-5 rounded-lg border border-pergamino-200 bg-pergamino-50 p-4 text-sm text-tinta-suave">
          <summary className="cursor-pointer font-semibold text-tinta">Cómo preparar la GPU</summary>
          <p className="mt-3">Si tu equipo tiene una GPU NVIDIA compatible, activá su componente en Docker. La primera preparación puede demorar y necesita conexión a internet.</p>
          <p className="mt-3 font-semibold">Windows</p><code className="mt-1 block overflow-x-auto rounded bg-white p-2">.\scripts\bootstrap.ps1 -Device cuda</code>
          <p className="mt-3 font-semibold">Linux o macOS</p><code className="mt-1 block overflow-x-auto rounded bg-white p-2">bash scripts/bootstrap.sh --device cuda</code>
          <p className="mt-2">Después, volvé aquí y actualizá el estado. No hace falta una GPU para usar CPU.</p>
        </details>}
      </>}
    </section>
  </div>;
}
