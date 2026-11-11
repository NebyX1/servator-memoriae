import { createContext, useContext, useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { api, ensureCsrf } from '../../lib/axios';
import type { User } from '../../types';

interface AuthCtx {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

type ApiUser = { id: string; email: string; role: string; local_test_mode?: boolean };
function toUser(user: ApiUser): User {
  return { id: user.id, email: user.email, nombre: user.local_test_mode ? 'Modo de prueba' : user.email,
    rol: user.role as User['rol'], preview_mode: false, local_test_mode: !!user.local_test_mode };
}

const Ctx = createContext<AuthCtx>({ user: null, loading: true, login: async () => {}, logout: async () => {}, refresh: async () => {} });

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const userRef = useRef<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [sessionExpired, setSessionExpired] = useState(false);
  const [password, setPassword] = useState('');
  const [restoreError, setRestoreError] = useState('');
  const [restoring, setRestoring] = useState(false);

  const updateUser = useCallback((next: User | null) => {
    userRef.current = next;
    setUser(next);
  }, []);

  const refresh = useCallback(async () => {
    try {
      const { data } = await api.get<{ user: ApiUser | null }>('/auth/me');
      updateUser(data.user ? toUser(data.user) : null);
    } catch {
      updateUser(null);
    } finally {
      setLoading(false);
    }
  }, [updateUser]);

  useEffect(() => {
    void ensureCsrf().catch(() => {}).finally(refresh);
    // La pantalla sigue montada para conservar los archivos seleccionados.
    const onExpired = () => { if (userRef.current) setSessionExpired(true); };
    window.addEventListener('session-expired', onExpired);
    return () => window.removeEventListener('session-expired', onExpired);
  }, [refresh]);

  const login = useCallback(async (email: string, passwordValue: string) => {
    await ensureCsrf();
    await api.post('/auth/login', { email, password: passwordValue });
    await refresh();
  }, [refresh]);

  const logout = useCallback(async () => {
    try {
      await api.post('/auth/logout');
    } finally {
      updateUser(null);
      setSessionExpired(false);
      setPassword('');
    }
  }, [updateUser]);

  async function restoreSession(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!user || restoring) return;
    setRestoring(true);
    setRestoreError('');
    try {
      await ensureCsrf(true);
      const { data } = await api.post<{ user: ApiUser }>('/auth/login', { email: user.email, password });
      updateUser(toUser(data.user));
      setPassword('');
      setSessionExpired(false);
    } catch (error: unknown) {
      const status = (error as { response?: { status?: number } }).response?.status;
      setRestoreError(status === 401 || status === 403
        ? 'No pudimos iniciar sesión. Revisá tu contraseña.'
        : 'No pudimos conectar con el archivo. Intentá nuevamente.');
    } finally {
      setRestoring(false);
    }
  }

  return <Ctx.Provider value={{ user, loading, login, logout, refresh }}>
    {children}
    {sessionExpired && user && <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4" role="presentation">
      <section className="papel w-full max-w-md rounded-xl p-7 shadow-xl" role="dialog" aria-modal="true" aria-labelledby="session-expired-title">
        <h2 id="session-expired-title" className="archivo-titulo text-2xl font-bold">Volvé a entrar</h2>
        <p className="mt-2 text-sm text-tinta-suave">Tu sesión terminó. Conservamos esta pantalla y los archivos seleccionados mientras ingresás nuevamente. Después podés reintentar la acción.</p>
        <form className="mt-5 flex flex-col gap-4" onSubmit={restoreSession}>
          <p className="text-sm font-semibold">{user.email}</p>
          <label className="form-control gap-2">
            <span className="label-text">Contraseña</span>
            <input className="input input-bordered" type="password" autoComplete="current-password" autoFocus required value={password} onChange={event => setPassword(event.target.value)} />
          </label>
          {restoreError && <p className="text-sm text-error" role="alert">{restoreError}</p>}
          <button className="btn btn-primary" type="submit" disabled={restoring}>{restoring ? 'Entrando…' : 'Continuar'}</button>
        </form>
      </section>
    </div>}
  </Ctx.Provider>;
}

export function useAuth() {
  return useContext(Ctx);
}
