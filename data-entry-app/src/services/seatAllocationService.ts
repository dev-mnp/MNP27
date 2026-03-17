import { supabase, withTimeoutAndRetry } from '../lib/supabase';

export interface SeatAllocationRow {
  id: string;
  session_name: string;
  source_file_name: string | null;
  application_number: string;
  beneficiary_name: string;
  district: string;
  requested_item: string;
  quantity: number;
  waiting_hall_quantity: number;
  token_quantity: number;
  beneficiary_type: string | null;
  item_type: string | null;
  comments: string | null;
  master_row?: Record<string, any> | null;
  master_headers?: string[] | null;
  sort_order: number | null;
  created_by: string | null;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface SeatAllocationUploadRow {
  application_number: string;
  beneficiary_name: string;
  district: string;
  requested_item: string;
  quantity: number;
  waiting_hall_quantity: number;
  token_quantity: number;
  beneficiary_type?: string;
  item_type?: string;
  comments?: string;
  master_row?: Record<string, any>;
  master_headers?: string[];
  sort_order?: number;
}

export interface SeatAllocationSequenceUpdateRow {
  id: string;
  master_row: Record<string, any>;
  master_headers: string[];
}

export const fetchSeatAllocationSessions = async (): Promise<string[]> => {
  const rows = await withTimeoutAndRetry(async () => {
    const { data, error } = await supabase
      .from('seat_allocation')
      .select('session_name, updated_at')
      .order('updated_at', { ascending: false });

    if (error) throw error;
    return data;
  }, 1, 15000);

  const orderedUniqueSessions = new Map<string, true>();
  for (const row of rows || []) {
    if (row.session_name && !orderedUniqueSessions.has(row.session_name)) {
      orderedUniqueSessions.set(row.session_name, true);
    }
  }

  return Array.from(orderedUniqueSessions.keys());
};

export const fetchSeatAllocationRows = async (sessionName: string): Promise<SeatAllocationRow[]> => {
  if (!sessionName.trim()) return [];

  const rows = await withTimeoutAndRetry(async () => {
    const { data, error } = await supabase
      .from('seat_allocation')
      .select('*')
      .eq('session_name', sessionName.trim())
      .order('sort_order', { ascending: true, nullsFirst: false })
      .order('district', { ascending: true })
      .order('requested_item', { ascending: true })
      .order('application_number', { ascending: true });

    if (error) throw error;
    return data;
  }, 1, 20000);

  return (rows || []) as SeatAllocationRow[];
};

export const replaceSeatAllocationSessionRows = async (
  sessionName: string,
  sourceFileName: string,
  rows: SeatAllocationUploadRow[],
  _userId?: string
): Promise<SeatAllocationRow[]> => {
  const normalizedSession = sessionName.trim();
  if (!normalizedSession) {
    throw new Error('Session name is required.');
  }

  await withTimeoutAndRetry(async () => {
    const { error } = await supabase
      .from('seat_allocation')
      .delete()
      .eq('session_name', normalizedSession);

    if (error) throw error;
    return true;
  }, 1, 20000);

  if (rows.length === 0) {
    return [];
  }

  const payload = rows.map((row, index) => ({
    session_name: normalizedSession,
    source_file_name: sourceFileName,
    application_number: row.application_number,
    beneficiary_name: row.beneficiary_name,
    district: row.district,
    requested_item: row.requested_item,
    quantity: row.quantity,
    waiting_hall_quantity: row.waiting_hall_quantity,
    token_quantity: row.token_quantity,
    beneficiary_type: row.beneficiary_type ?? null,
    item_type: row.item_type ?? null,
    comments: row.comments ?? null,
    master_row: row.master_row ?? {},
    master_headers: row.master_headers ?? [],
    sort_order: row.sort_order ?? index + 1,
    created_by: null,
    updated_by: null,
  }));

  const batchSize = 500;
  for (let i = 0; i < payload.length; i += batchSize) {
    const batch = payload.slice(i, i + batchSize);
    await withTimeoutAndRetry(async () => {
      const { error } = await supabase.from('seat_allocation').insert(batch);
      if (error) throw error;
      return true;
    }, 1, 30000);
  }

  return fetchSeatAllocationRows(normalizedSession);
};

export const updateSeatAllocationRowQuantities = async (
  id: string,
  waitingHallQuantity: number,
  tokenQuantity: number,
  _userId?: string
): Promise<void> => {
  await withTimeoutAndRetry(async () => {
    const { error } = await supabase
      .from('seat_allocation')
      .update({
        waiting_hall_quantity: waitingHallQuantity,
        token_quantity: tokenQuantity,
        updated_by: null,
      })
      .eq('id', id);

    if (error) throw error;
    return true;
  }, 1, 10000);
};

export const updateSeatAllocationSequenceData = async (
  rows: SeatAllocationSequenceUpdateRow[]
): Promise<void> => {
  if (!rows.length) return;

  const batchSize = 100;
  for (let i = 0; i < rows.length; i += batchSize) {
    const batch = rows.slice(i, i + batchSize);
    await withTimeoutAndRetry(async () => {
      const results = await Promise.all(
        batch.map((row) =>
          supabase
            .from('seat_allocation')
            .update({
              master_row: row.master_row,
              master_headers: row.master_headers,
              updated_by: null,
            })
            .eq('id', row.id)
        )
      );

      const failed = results.find((result) => result.error);
      if (failed?.error) throw failed.error;
      return true;
    }, 1, 30000);
  }
};
