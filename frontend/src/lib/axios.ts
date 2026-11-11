import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';

function newRequestId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  return `${Date.now()}-${Math.floor(Math.random() * 1e9)}`;
}

export const api = axios.create({
  baseURL: '/api/v1',
  withCredentials: true,
  timeout: 30000,
});

// Flask-WTF entrega el token firmado en JSON y lo vincula a la sesión.
// Compartir la petición evita carreras entre varias escrituras simultáneas.
let csrfToken: string | null = null;
let csrfRequest: Promise<string> | null = null;

export async function ensureCsrf(force = false): Promise<string> {
  if (!force && csrfToken) return csrfToken;
  if (!csrfRequest) {
    csrfRequest = api.get<{ csrfToken: string }>('/auth/csrf').then(({ data }) => {
      if (!data.csrfToken) throw new Error('No se pudo preparar la sesión. Volvé a intentarlo.');
      csrfToken = data.csrfToken;
      return csrfToken;
    }).finally(() => { csrfRequest = null; });
  }
  return csrfRequest;
}

type RetryConfig = InternalAxiosRequestConfig & { csrfRetried?: boolean };

api.interceptors.request.use(async (config) => {
  config.headers.set('X-Request-ID', newRequestId());
  const method = (config.method ?? 'get').toLowerCase();
  if (!['get', 'head', 'options', 'trace'].includes(method)) {
    config.headers.set('X-CSRFToken', await ensureCsrf());
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<{ code?: string }>) => {
    const config = error.config as RetryConfig | undefined;
    // Solo reintentar cuando Flask-WTF rechazó la solicitud antes de ejecutarla.
    // Esto recupera tokens vencidos o una sesión reemplazada en otra pestaña.
    if (config && !config.csrfRetried && error.response?.status === 400 && error.response.data?.code === 'csrf_invalid') {
      config.csrfRetried = true;
      await ensureCsrf(true);
      return api.request(config);
    }
    if (error.response?.status === 401 && typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('session-expired'));
    }
    return Promise.reject(error);
  },
);
