export type Role = 'analyst' | 'reviewer' | 'admin' | 'superadmin';
export const isAdminRole = (role: Role | undefined) => role === 'admin' || role === 'superadmin';

export interface ProfileInfo { has_photo: boolean; photo_locked: boolean; photo_url: string | null }
export interface SitePerson { name: string; role: string; photo_id: string | null; photo_url?: string | null }
export interface SiteBusiness { name: string; email: string; phone: string; address: string; last_updated: string }
export interface SiteContent { team: SitePerson[]; guides: SitePerson[]; business: SiteBusiness }
export type EnginePath = 'rule' | 'ml';

export interface Session { token: string; role: Role; full_name: string }
export interface User { id: number; email: string; full_name: string; role: Role; is_active: boolean; must_change_password?: boolean }
export interface TokenOut { access_token: string; token_type: string; role: Role; full_name: string; must_change_password?: boolean }

export interface Measurements {
  bulk_density: number;
  tapped_density?: number;
  angle_of_repose?: number;
  particle_size_um?: number;
  moisture_percent?: number;
  flow_rate_g_s?: number;
}

export interface ClassifyResult {
  path: EnginePath;
  predicted_class: string;
  poor_flow: boolean | null;
  acceptable: boolean | null;
  carr_index: number | null;
  hausner: number | null;
  hausner_class?: string | null;
  criteria_agree?: boolean | null;
  confidence: number | null;
  model_version: string | null;
  basis: string | null;
  caveats: string[] | null;
  prediction_id?: number;
}

export interface PredictionSummary {
  id: number;
  sample_id: number | null;
  sample_voided: boolean;
  path: EnginePath;
  predicted_class: string;
  poor_flow: boolean | null;
  acceptable: boolean | null;
  confidence: number | null;
  carr_index: number | null;
  hausner: number | null;
  model_version: string | null;
  reviewed: boolean;
  created_at: string;
}

export interface PredictionDetail extends PredictionSummary {
  user_id: number;
  inputs: Record<string, number | null>;
  caveats: string[] | null;
  basis: string | null;
  hausner_class: string | null;
  criteria_agree: boolean | null;
  reviewed_by_id: number | null;
  reviewed_at: string | null;
  review_comment: string | null;
}

export interface Sample extends Measurements {
  id: number;
  material_id: number;
  material_name: string;
  operator_id: number;
  batch_no: string;
  replicate_no: number;
  measured_at: string;
  method_ref: string | null;
  notes: string | null;
  is_voided: boolean;
  void_reason: string | null;
}

export interface SampleIn extends Measurements {
  material_name: string;
  material_type?: string;
  batch_no: string;
  replicate_no: number;
  method_ref?: string;
  notes?: string;
}

export interface Material { id: number; name: string; material_type: string | null }

export interface Tier {
  tier: string;
  features: string[];
  n_materials: number;
  n_rows?: number;
  lomo_accuracy: number;
  lomo_balanced_acc: number;
  lomo_sensitivity?: number;
  lomo_specificity?: number;
  majority_baseline: number;
  confusion_matrix?: number[][];
}

export interface ModelCard {
  exact_path: { when: string; method: string; accuracy: string };
  ml_tiers: Record<string, Tier>;
  training_ranges: Record<string, [number, number]>;
}

export interface AuditEntry {
  id: number;
  at: string;
  actor: string | null;
  action: string;
  entity: string | null;
  entity_id: number | null;
  detail: unknown;
  ip_address: string | null;
}

export interface PlanInfo {
  code: 'free' | 'pro' | 'lab';
  name: string;
  price_paise: number;
  monthly_limit: number | null;
  ml: boolean;
  features: string[];
}
export interface PlansResponse {
  currency: string;
  period_days: number;
  mode: 'disabled' | 'test' | 'live';
  key_id: string | null;
  plans: PlanInfo[];
}
export interface MyPlan {
  plan: PlanInfo['code'];
  plan_name: string;
  staff: boolean;
  monthly_limit: number | null;
  used_this_month: number;
  ml: boolean;
  current_period_end: string | null;
}
export interface OrderOut {
  order_id: string; amount: number; currency: string; key_id: string;
  plan: string; plan_name: string; name: string; email: string;
}
export interface RazorpayResponse { razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string }
export interface AdminOverview {
  users: Record<Role, number>;
  active_subscriptions: { pro: number; lab: number };
  revenue_paise: { live: number; test: number };
  payments_paid: number;
  results_this_month: number;
}
export interface AdminSubscription {
  user_id: number; email: string; full_name: string; plan: string;
  current_period_end: string; source: string; active: boolean;
}
export interface AdminPayment {
  id: number; email: string; plan: string; amount_paise: number; currency: string; mode: string;
  status: string; razorpay_order_id: string; razorpay_payment_id: string | null;
  created_at: string; paid_at: string | null;
}

export const rupees = (paise: number) =>
  `₹${(paise / 100).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;

const SESSION_KEY = 'powderflow.session';
const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? '';
let session: Session | null = readSession();
let onUnauthorized: () => void = () => undefined;

function readSession(): Session | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

export function getSession() { return session; }

export function setSession(next: Session | null) {
  session = next;
  try {
    if (next) sessionStorage.setItem(SESSION_KEY, JSON.stringify(next));
    else sessionStorage.removeItem(SESSION_KEY);
  } catch { /* the session still works in memory */ }
}

export function setUnauthorizedHandler(handler: () => void) { onUnauthorized = handler; }

export class ApiError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

function errorMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((item: { loc?: unknown[]; msg?: string }) => {
      const field = item.loc?.filter((part) => part !== 'body').join('.');
      const message = (item.msg ?? 'Invalid value').replace(/^Value error, /, '');
      return field ? `${field.replace(/_/g, ' ')}: ${message}` : message;
    }).join(' ');
  }
  return status >= 500 ? 'The server had a problem. Please try again.' : `Request failed (${status}).`;
}

async function request<T>(method: string, path: string, body?: unknown, auth = true): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (auth && session) headers.Authorization = `Bearer ${session.token}`;

  let response: Response;
  try {
    response = await fetch(BASE + path, {
      method, headers, body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError('Cannot reach the server. Check that the API is running.', 0);
  }
  const text = await response.text();
  let data: unknown = null;
  try { data = text ? JSON.parse(text) : null; } catch { /* non-JSON error page */ }
  if (!response.ok) {
    if (response.status === 401 && auth) onUnauthorized();
    throw new ApiError(errorMessage(data, response.status), response.status);
  }
  return data as T;
}

const IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
export const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

/** Upload an image as the raw request body; the server re-checks everything. */
async function uploadImage<T>(method: string, path: string, file: File): Promise<T> {
  if (!IMAGE_TYPES.includes(file.type)) throw new ApiError('Choose a JPEG, PNG or WebP image.', 422);
  if (file.size > MAX_IMAGE_BYTES) throw new ApiError('Images must be 5 MB or smaller.', 413);
  const headers: Record<string, string> = { 'Content-Type': file.type };
  if (session) headers.Authorization = `Bearer ${session.token}`;
  let response: Response;
  try {
    response = await fetch(BASE + path, { method, headers, body: file });
  } catch {
    throw new ApiError('Cannot reach the server. Check your connection.', 0);
  }
  const text = await response.text();
  let data: unknown = null;
  try { data = text ? JSON.parse(text) : null; } catch { /* ignore */ }
  if (!response.ok) {
    if (response.status === 401) onUnauthorized();
    throw new ApiError(errorMessage(data, response.status), response.status);
  }
  return data as T;
}

/** Private images need the bearer token, so they are fetched and shown from memory. */
export async function fetchPrivateImage(path: string): Promise<string | null> {
  if (!session) return null;
  const response = await fetch(BASE + path, { headers: { Authorization: `Bearer ${session.token}` } });
  if (!response.ok) return null;
  const blob = await response.blob();
  return blob.type === 'image/webp' ? URL.createObjectURL(blob) : null;
}

function query(params: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : '';
}

export const api = {
  login: (email: string, password: string) =>
    request<TokenOut>('POST', '/auth/login', { email, password }, false),
  register: (email: string, full_name: string, password: string) =>
    request<TokenOut>('POST', '/auth/register', { email, full_name, password }, false),
  me: () => request<User>('GET', '/auth/me'),

  plans: () => request<PlansResponse>('GET', '/billing/plans', undefined, false),
  myPlan: () => request<MyPlan>('GET', '/billing/me'),
  createOrder: (plan: 'pro' | 'lab') => request<OrderOut>('POST', '/billing/orders', { plan }),
  verifyPayment: (body: RazorpayResponse) =>
    request<{ ok: boolean; plan: string; plan_name: string; current_period_end: string | null }>(
      'POST', '/billing/verify', body),

  myProfile: () => request<ProfileInfo>('GET', '/profile/me'),
  uploadPhoto: (file: File) => uploadImage<ProfileInfo>('PUT', '/profile/me/photo', file),
  deletePhoto: () => request<ProfileInfo>('DELETE', '/profile/me/photo'),
  setPhotoLock: (photo_locked: boolean) => request<ProfileInfo>('PATCH', '/profile/me', { photo_locked }),
  removeUserPhoto: (userId: number) => request<{ ok: boolean }>('DELETE', `/admin/users/${userId}/photo`),

  siteContent: () => request<SiteContent>('GET', '/site/content', undefined, false),
  saveSiteContent: (body: SiteContent) => request<SiteContent>('PUT', '/site/content', body),
  uploadSitePhoto: (file: File) => uploadImage<{ id: string; url: string }>('POST', '/site/photos', file),

  adminOverview: () => request<AdminOverview>('GET', '/admin/overview'),
  adminSubscriptions: () => request<AdminSubscription[]>('GET', '/admin/subscriptions?limit=200'),
  adminPayments: (limit: number, offset: number) =>
    request<AdminPayment[]>('GET', `/admin/payments${query({ limit, offset })}`),
  setPlan: (userId: number, plan: string, days: number) =>
    request<{ plan: string }>('POST', `/admin/users/${userId}/plan`, { plan, days }),
  changePassword: (current_password: string, new_password: string) =>
    request<TokenOut>('POST', '/auth/change-password', { current_password, new_password }),

  classify: (body: Measurements) => request<ClassifyResult>('POST', '/classify', body),
  modelCard: () => request<ModelCard>('GET', '/model-card', undefined, false),

  materials: () => request<Material[]>('GET', '/materials?limit=500'),
  samples: (limit: number, offset: number, include_voided: boolean) =>
    request<Sample[]>('GET', `/samples${query({ limit, offset, include_voided })}`),
  createSample: (body: SampleIn) =>
    request<{ sample_id: number; material_id: number }>('POST', '/samples', body),
  classifySample: (id: number) => request<ClassifyResult>('POST', `/samples/${id}/classify`),
  voidSample: (id: number, reason: string) =>
    request<Sample>('POST', `/samples/${id}/void`, { reason }),

  predictions: (params: { limit: number; offset: number; path?: string; reviewed?: string }) =>
    request<PredictionSummary[]>('GET', `/predictions${query(params)}`),
  prediction: (id: number) => request<PredictionDetail>('GET', `/predictions/${id}`),
  review: (id: number, comment: string) =>
    request<{ ok: boolean }>('POST', `/predictions/${id}/review`, { comment }),

  users: () => request<User[]>('GET', '/users?limit=200'),
  createUser: (body: { email: string; full_name: string; password: string; role: Role }) =>
    request<User>('POST', '/users', body),
  updateUser: (id: number, body: Partial<Pick<User, 'role' | 'is_active' | 'full_name'>> & { password?: string }) =>
    request<User>('PATCH', `/users/${id}`, body),

  audit: (limit: number, offset: number, action?: string) =>
    request<AuditEntry[]>('GET', `/audit${query({ limit, offset, action })}`),
};
