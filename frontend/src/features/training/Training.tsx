import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ArrowRight, BookOpenCheck, GraduationCap, Info } from 'lucide-react';
import { api } from '../../lib/axios';
import { Loading, ErrorState } from '../../components/ui/Common';

type Example = { id: string; title: string; pages: number; reviewed_pages: number; lines: number };
type Examples = { training_available: boolean; items: Example[] };

export default function Training() {
  const examples = useQuery({
    queryKey: ['training-examples'],
    queryFn: async () => (await api.get<Examples>('/training/examples')).data,
  });
  const items = examples.data?.items ?? [];
  const lines = items.reduce((sum, item) => sum + item.lines, 0);
  const pages = items.reduce((sum, item) => sum + item.reviewed_pages, 0);

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-widest text-primary">Una herramienta opcional</p>
        <h1 className="archivo-titulo mt-2 flex items-center gap-3 text-3xl font-bold"><GraduationCap aria-hidden="true" /> Mejorar la lectura</h1>
        <p className="mt-2 max-w-2xl text-tinta-suave">Prepará ejemplos de tu caligrafía mientras revisás tus documentos. Podés transcribir y exportar sin entrenar un modelo.</p>
      </div>
      <div role="status" className="alert alert-info items-start">
        <Info className="mt-1 shrink-0" aria-hidden="true" />
        <div><h2 className="font-bold">El entrenamiento todavía no está disponible</h2>
          <p className="mt-1 text-sm">Las correcciones se guardan con tus documentos. El ajuste de un modelo y la medición de su calidad aún necesitan una implementación verificable; por ahora no se puede iniciar un entrenamiento.</p>
        </div>
      </div>
      <section className="papel rounded-xl p-6" aria-labelledby="preparacion-title">
        <h2 id="preparacion-title" className="archivo-titulo text-xl font-bold">Prepará tus ejemplos</h2>
        <ol className="mt-4 space-y-4 text-sm">
          <li><strong>1. Transcribí páginas.</strong> Abrí un documento con imágenes y pedí su transcripción.</li>
          <li><strong>2. Revisá cada renglón.</strong> Compará el texto con la imagen, corregilo si hace falta y marcá el renglón como confirmado o corregido.</li>
          <li><strong>3. Reuní varias páginas.</strong> Usá ejemplos de la escritura que querés reconocer. Una variedad de páginas ayudará a evaluar una futura mejora.</li>
        </ol>
        <Link className="btn btn-primary mt-5 gap-2" to="/documentos"><BookOpenCheck size={18} /> Ir a mis documentos <ArrowRight size={16} /></Link>
      </section>
      <section className="papel rounded-xl p-6" aria-labelledby="examples-title">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><h2 id="examples-title" className="archivo-titulo text-xl font-bold">Tus ejemplos revisados</h2>
            <p className="mt-1 text-sm text-tinta-suave">Se cuentan los renglones con texto marcados como confirmados o corregidos.</p></div>
          {examples.data && <div className="rounded-lg bg-base-200 px-4 py-2 text-sm"><strong>{lines}</strong> renglones · <strong>{pages}</strong> páginas</div>}
        </div>
        {examples.isLoading && <Loading texto="Contando ejemplos…" />}
        {examples.isError && <ErrorState titulo="No se pudieron cargar los ejemplos" reintentar={() => examples.refetch()} />}
        {examples.data && items.length === 0 && <p className="mt-5 text-sm text-tinta-suave">Todavía no hay documentos. Creá uno y agregá páginas para comenzar.</p>}
        {items.length > 0 && <div className="mt-4 overflow-x-auto"><table className="table w-full text-sm">
          <caption className="sr-only">Ejemplos revisados por documento</caption>
          <thead><tr><th>Documento</th><th>Páginas revisadas</th><th>Renglones revisados</th></tr></thead>
          <tbody>{items.map((item) => <tr key={item.id}><td>{item.title}</td><td>{item.reviewed_pages} de {item.pages}</td><td>{item.lines}</td></tr>)}</tbody>
        </table></div>}
      </section>
    </div>
  );
}
