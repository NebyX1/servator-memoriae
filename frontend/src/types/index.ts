export type Role = 'viewer' | 'reviewer' | 'analyst' | 'admin' | 'superadmin';

export interface User {
  id: string;
  email: string;
  nombre: string;
  rol: Role;
  preview_mode: boolean;
  local_test_mode?: boolean;
}

export interface Collection {
  id: string;
  nombre: string;
  descripcion?: string;
  created_at: string;
}

export interface DocItem {
  id: string;
  titulo: string;
  tipo: string;
  estado: string;
  collection_id?: string | null;
  paginas: number;
  progreso?: number;
  created_at: string;
  updated_at: string;
}

export interface PageItem {
  id: string;
  document_id: string;
  numero: number;
  folio?: string | null;
  rotacion: number;
  width: number;
  height: number;
  image_url?: string;
  estado: string;
}

export interface LineItem {
  id: string;
  page_id: string;
  numero: number;
  texto: string;
  estado: 'pendiente' | 'revisada' | 'dudosa' | 'corregida';
  confianza?: number;
  bbox?: [number, number, number, number];
}

export interface JobItem {
  id: string;
  tipo: string;
  estado: 'encolado' | 'procesando' | 'completado' | 'fallido' | 'cancelado';
  progreso: number;
  mensaje?: string;
  document_id?: string | null;
  created_at: string;
}

export interface ModelInfo {
  id: string;
  nombre: string;
  version: string;
  activo: boolean;
  cer?: number | null;
  created_at: string;
}

export interface ReaderStatus {
  motor: string;
  modelo_activo?: string | null;
  cuda: boolean;
  cola: number;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
