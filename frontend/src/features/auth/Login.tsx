import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { useNavigate, Navigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Brand } from '../../components/ui/Common';
import { useAuth } from './AuthProvider';
import { api, ensureCsrf } from '../../lib/axios';

const schema = z.object({
  email: z.string().trim().regex(/^[^\s@]+@[^\s@]+$/, 'Correo no válido'),
  password: z.string().min(1, 'Escribe tu contraseña'),
});

type Form = z.infer<typeof schema>;

export default function Login() {
  const { user, login, refresh } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState('');
  const [first, setFirst] = useState(false);
  const { register, handleSubmit, formState } = useForm<Form>({ resolver: zodResolver(schema) });

  if (user) return <Navigate to="/" replace />;

  async function onSubmit(v: Form) {
    setError('');
    try {
      await login(v.email, v.password);
      navigate('/', { replace: true });
    } catch (e: unknown) {
      const status = (e as { response?: { status?: number } })?.response?.status;
      if (status === 404 || status === 401) {
        // Puede ser primera instalación: intenta registro inicial
        try {
          await ensureCsrf();
          await api.post('/auth/register_first', { email: v.email, password: v.password, nombre: v.email });
          await refresh();
          navigate('/', { replace: true });
          return;
        } catch {
          setFirst(true);
        }
      }
      setError('No se pudo entrar. Revisa el correo y la contraseña.');
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-pergamino-100 p-4">
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="papel w-full max-w-md rounded-xl p-8">
        <Brand />
        <h1 className="archivo-titulo mt-4 text-2xl font-bold">Entrar al archivo</h1>
        <p className="mt-1 text-sm text-tinta-suave">Accede con tu cuenta para digitalizar y revisar documentos.</p>
        {first && (
          <div className="alert alert-info mt-4 text-sm">
            Si esta es la primera cuenta del archivo, se creará como administradora.
          </div>
        )}
        <form onSubmit={handleSubmit(onSubmit)} className="mt-6 flex flex-col gap-3">
          <label className="form-control">
            <span className="label-text">Correo</span>
            <input className="input input-bordered" type="email" autoComplete="username" {...register('email')} />
            {formState.errors.email && <span className="text-xs text-error">{formState.errors.email.message}</span>}
          </label>
          <label className="form-control">
            <span className="label-text">Contraseña</span>
            <input className="input input-bordered" type="password" autoComplete="current-password" {...register('password')} />
            {formState.errors.password && <span className="text-xs text-error">{formState.errors.password.message}</span>}
          </label>
          {error && <p className="text-sm text-error">{error}</p>}
          <button className="btn btn-primary mt-2" disabled={formState.isSubmitting}>
            {formState.isSubmitting ? 'Entrando…' : 'Entrar'}
          </button>
        </form>
      </motion.div>
    </div>
  );
}
