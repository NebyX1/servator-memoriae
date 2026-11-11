import { Suspense, lazy } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import Shell from '../components/layout/Shell';
import { Loading } from '../components/ui/Common';
import { useAuth } from '../features/auth/AuthProvider';
import type { Role } from '../types';

const Login = lazy(() => import('../features/auth/Login'));
const Wizard = lazy(() => import('../features/digitize/Wizard'));
const Documents = lazy(() => import('../features/documents/Documents'));
const Training = lazy(() => import('../features/training/Training'));
const Admin = lazy(() => import('../features/admin/Admin'));
const Settings = lazy(() => import('../features/settings/Settings'));

function Permission({ roles, children }: { roles: Role[]; children: JSX.Element }) {
  const { user, loading } = useAuth();
  if (loading) return <Loading texto="Comprobando permiso…" />;
  if (!user) return <Navigate to="/entrar" replace />;
  if (!roles.includes(user.rol)) {
    return (
      <div className="p-8">
        <div className="alert alert-warning max-w-xl">
          <span>No tienes permiso para ver esta sección. Tu rol es «{user.rol}».</span>
        </div>
      </div>
    );
  }
  return children;
}

function AuthenticatedShell() {
  const { user, loading } = useAuth();
  if (loading) return <Loading texto="Comprobando sesión…" />;
  if (!user) return <Navigate to="/entrar" replace />;
  return <Shell />;
}

export default function App() {
  return (
    <Suspense fallback={<Loading texto="Cargando archivo…" />}>
      <Routes>
        <Route path="/entrar" element={<Login />} />
        <Route element={<AuthenticatedShell />}>
          <Route index element={<Wizard />} />
          <Route path="documentos" element={<Documents />} />
          <Route path="configuracion" element={<Permission roles={['admin', 'superadmin']}><Settings /></Permission>} />
          <Route
            path="mejorar"
            element={
              <Permission roles={['reviewer', 'analyst', 'admin', 'superadmin']}>
                <Training />
              </Permission>
            }
          />
          <Route
            path="admin"
            element={
              <Permission roles={['admin', 'superadmin']}>
                <Admin />
              </Permission>
            }
          />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
