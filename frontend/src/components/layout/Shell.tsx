import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { ScanLine, FolderOpen, GraduationCap, ShieldCheck, Settings2, LogOut, Eye } from 'lucide-react';
import { Brand } from '../ui/Common';
import { useAuth } from '../../features/auth/AuthProvider';

function linkCls({ isActive }: { isActive: boolean }) {
  return `flex items-center gap-2 rounded-md px-3 py-2 text-sm ${isActive ? 'bg-bosque-600 text-pergamino-50' : 'text-tinta-suave hover:bg-pergamino-100'}`;
}

export default function Shell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function salir() {
    await logout();
    navigate('/entrar');
  }

  return (
    <div className="flex min-h-screen bg-pergamino-50 text-tinta">
      <aside className="hidden w-64 flex-col gap-4 border-r border-pergamino-200 bg-pergamino-100 p-4 md:flex">
        <Brand />
        <nav className="flex flex-col gap-1">
          <p className="px-3 pt-2 text-xs uppercase tracking-wide text-tinta-clara">Trabajo</p>
          <NavLink to="/" end className={linkCls}>
            <ScanLine size={17} /> Digitalizar
          </NavLink>
          <NavLink to="/documentos" className={linkCls}>
            <FolderOpen size={17} /> Mis documentos
          </NavLink>
          <NavLink to="/mejorar" className={linkCls}>
            <GraduationCap size={17} /> Mejorar lectura
          </NavLink>
          <p className="px-3 pt-4 text-xs uppercase tracking-wide text-tinta-clara">Área secundaria</p>
          <NavLink to="/configuracion" className={linkCls}>
            <Settings2 size={17} /> Configuración
          </NavLink>
          <NavLink to="/admin" className={linkCls}>
            <ShieldCheck size={17} /> Admin
          </NavLink>
        </nav>
        <div className="mt-auto rounded-md bg-white/70 p-3 text-xs text-tinta-suave">
          <p className="font-semibold text-tinta">{user?.nombre ?? 'Sesión'}</p>
          {user?.local_test_mode ? <p>Archivo local</p> : <>
            <p>{user?.email} · {user?.rol}</p>
            <button className="btn btn-ghost btn-xs mt-2 gap-1" onClick={salir}>
              <LogOut size={14} /> Salir
            </button>
          </>}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-pergamino-200 bg-pergamino-50 px-4 py-3">
          <div className="md:hidden">
            <Brand compact />
          </div>
          <nav className="flex min-w-0 gap-1 overflow-x-auto text-sm md:hidden">
            <NavLink to="/" end className="btn btn-ghost btn-sm">
              Digitalizar
            </NavLink>
            <NavLink to="/documentos" className="btn btn-ghost btn-sm">
              Docs
            </NavLink>
            <NavLink to="/mejorar" className="btn btn-ghost btn-sm">
              Mejorar
            </NavLink>
            <NavLink to="/admin" className="btn btn-ghost btn-sm">
              Admin
            </NavLink>
            <NavLink to="/configuracion" className="btn btn-ghost btn-sm">
              Config
            </NavLink>
          </nav>
          <div className="ml-auto flex items-center gap-2 text-sm">
            {user?.local_test_mode ? <span className="badge badge-outline">Modo de prueba</span> : <>
              <span className="hidden sm:inline text-tinta-suave">{user?.email}</span>
              <span className="badge badge-outline">{user?.rol}</span>
            </>}
          </div>
        </header>

        {user?.preview_mode && (
          <div className="flex items-center gap-2 bg-dorado/20 px-4 py-2 text-sm text-tinta">
            <Eye size={16} />
            <span>
              <strong>Modo vista previa:</strong> estás viendo el archivo sin cambios definitivos. Pide a un
              curador que apruebe tus revisiones.
            </span>
          </div>
        )}

        <main className="min-w-0 flex-1 p-4 md:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
