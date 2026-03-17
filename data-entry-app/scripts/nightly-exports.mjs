import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { createClient } from '@supabase/supabase-js';
import { google } from 'googleapis';
import { OAuth2Client } from 'google-auth-library';

const REQUIRED_ENV = [
  'SUPABASE_URL',
  'SUPABASE_SERVICE_ROLE_KEY',
];

for (const key of REQUIRED_ENV) {
  if (!process.env[key]) {
    throw new Error(`Missing required environment variable: ${key}`);
  }
}

const IST_TIMEZONE = 'Asia/Kolkata';
const EXPORT_CUTOFF_DATE = process.env.EXPORT_CUTOFF_DATE || '2026-03-02';
const OUTPUT_DIR = process.env.EXPORT_OUTPUT_DIR || './exports';
const SKIP_DRIVE_UPLOAD = process.env.SKIP_DRIVE_UPLOAD === 'true';
const GOOGLE_AUTH_MODE =
  process.env.GOOGLE_AUTH_MODE ||
  (process.env.GOOGLE_OAUTH_REFRESH_TOKEN ? 'oauth_user' : 'service_account');

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_ROLE_KEY,
  { auth: { persistSession: false } }
);

function getIstDateString(date = new Date()) {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: IST_TIMEZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date);
}

function getIstTimestamp(date = new Date()) {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: IST_TIMEZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).formatToParts(date);

  const part = Object.fromEntries(parts.map((p) => [p.type, p.value]));
  return `${part.year}-${part.month}-${part.day}_${part.hour}-${part.minute}`;
}

function asNumber(value) {
  if (value === null || value === undefined || value === '') return 0;
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function escapeCsv(value) {
  if (value === null || value === undefined) return '';
  const str = String(value);
  if (str.includes('"') || str.includes(',') || str.includes('\n')) {
    return `"${str.replaceAll('"', '""')}"`;
  }
  return str;
}

function readEnv(name) {
  const value = process.env[name];
  return typeof value === 'string' ? value.trim() : '';
}

function isMyDrivePath(targetPathRaw = '') {
  const normalizedPath = String(targetPathRaw).replace(/\\/g, '/').trim();
  return /^\/?My Drive(\/|$)/i.test(normalizedPath) || normalizedPath.includes('/My Drive/');
}

function writeCsv(filePath, headers, rows) {
  const lines = [headers.map(escapeCsv).join(',')];
  for (const row of rows) {
    lines.push(headers.map((h) => escapeCsv(row[h])).join(','));
  }
  fs.writeFileSync(filePath, `${lines.join('\n')}\n`, 'utf8');
}

async function fetchAllRows(table, select = '*', orderColumn = null) {
  const pageSize = 1000;
  const rows = [];
  let from = 0;

  while (true) {
    let query = supabase.from(table).select(select).range(from, from + pageSize - 1);
    if (orderColumn) {
      query = query.order(orderColumn, { ascending: true });
    }

    const { data, error } = await query;
    if (error) throw error;
    const chunk = data || [];
    rows.push(...chunk);

    if (chunk.length < pageSize) break;
    from += pageSize;
  }

  return rows;
}

async function buildMasterEntryExport(timestamp, articleMap, districtMap) {
  const districtEntries = await fetchAllRows(
    'district_beneficiary_entries',
    'application_number,district_id,article_id,quantity,total_amount,notes,created_at'
  );
  const publicEntries = await fetchAllRows(
    'public_beneficiary_entries',
    'application_number,name,article_id,quantity,total_amount,gender,aadhar_number,address,mobile,notes,created_at'
  );
  const institutionEntries = await fetchAllRows(
    'institutions_beneficiary_entries',
    'application_number,institution_name,institution_type,article_id,quantity,total_amount,address,mobile,notes,created_at'
  );

  const rows = [];

  for (const entry of districtEntries) {
    const article = articleMap.get(entry.article_id);
    const district = districtMap.get(entry.district_id);
    rows.push({
      'Application Number': entry.application_number || '',
      'District / Beneficiary Name': district?.district_name || '',
      'Requested Item': article?.article_name || '',
      'Quantity': asNumber(entry.quantity),
      'Cost Per Unit': article?.cost_per_unit ?? (asNumber(entry.quantity) > 0 ? asNumber(entry.total_amount) / asNumber(entry.quantity) : 0),
      'Total Value': asNumber(entry.total_amount),
      'Gender': '',
      'Aadhar Number': '',
      'Address': '',
      'Mobile': district?.mobile_number || '',
      'Beneficiary Type': 'District',
      'Item Type': article?.item_type || '',
      'Article Category': article?.category || '',
      'Super Category Article': article?.master_category || '',
      'Requested Item Tk': article?.article_name_tk || '',
      'Comments': entry.notes || '',
      'Created At': entry.created_at || '',
    });
  }

  for (const entry of publicEntries) {
    const article = articleMap.get(entry.article_id);
    rows.push({
      'Application Number': entry.application_number || '',
      'District / Beneficiary Name': entry.name || '',
      'Requested Item': article?.article_name || '',
      'Quantity': asNumber(entry.quantity),
      'Cost Per Unit': article?.cost_per_unit ?? (asNumber(entry.quantity) > 0 ? asNumber(entry.total_amount) / asNumber(entry.quantity) : 0),
      'Total Value': asNumber(entry.total_amount),
      'Gender': entry.gender || '',
      'Aadhar Number': entry.aadhar_number || '',
      'Address': entry.address || '',
      'Mobile': entry.mobile || '',
      'Beneficiary Type': 'Public',
      'Item Type': article?.item_type || '',
      'Article Category': article?.category || '',
      'Super Category Article': article?.master_category || '',
      'Requested Item Tk': article?.article_name_tk || '',
      'Comments': entry.notes || '',
      'Created At': entry.created_at || '',
    });
  }

  for (const entry of institutionEntries) {
    const article = articleMap.get(entry.article_id);
    rows.push({
      'Application Number': entry.application_number || '',
      'District / Beneficiary Name': entry.institution_name || '',
      'Requested Item': article?.article_name || '',
      'Quantity': asNumber(entry.quantity),
      'Cost Per Unit': article?.cost_per_unit ?? (asNumber(entry.quantity) > 0 ? asNumber(entry.total_amount) / asNumber(entry.quantity) : 0),
      'Total Value': asNumber(entry.total_amount),
      'Gender': '',
      'Aadhar Number': '',
      'Address': entry.address || '',
      'Mobile': entry.mobile || '',
      'Beneficiary Type': entry.institution_type === 'others' ? 'Others' : 'Institutions',
      'Item Type': article?.item_type || '',
      'Article Category': article?.category || '',
      'Super Category Article': article?.master_category || '',
      'Requested Item Tk': article?.article_name_tk || '',
      'Comments': entry.notes || '',
      'Created At': entry.created_at || '',
    });
  }

  rows.sort((a, b) => (b['Created At'] || '').localeCompare(a['Created At'] || ''));

  const headers = [
    'Application Number',
    'District / Beneficiary Name',
    'Requested Item',
    'Quantity',
    'Cost Per Unit',
    'Total Value',
    'Gender',
    'Aadhar Number',
    'Address',
    'Mobile',
    'Beneficiary Type',
    'Item Type',
    'Article Category',
    'Super Category Article',
    'Requested Item Tk',
    'Comments',
    'Created At',
  ];

  const filePath = path.join(OUTPUT_DIR, `master_entry_export_${timestamp}.csv`);
  writeCsv(filePath, headers, rows);
  return filePath;
}

async function buildFundRequestExport(timestamp) {
  const fundRequests = await fetchAllRows(
    'fund_request',
    'id,fund_request_number,fund_request_type,status,total_amount,aid_type,gst_number,supplier_name,purchase_order_number,notes,created_at'
  );
  const recipients = await fetchAllRows(
    'fund_request_recipients',
    'fund_request_id,beneficiary_type,recipient_name,fund_requested'
  );
  const articles = await fetchAllRows(
    'fund_request_articles',
    'fund_request_id,article_name,supplier_article_name,quantity,value'
  );

  const recipientsByFr = new Map();
  for (const r of recipients) {
    if (!recipientsByFr.has(r.fund_request_id)) recipientsByFr.set(r.fund_request_id, []);
    recipientsByFr.get(r.fund_request_id).push(r);
  }

  const articlesByFr = new Map();
  for (const a of articles) {
    if (!articlesByFr.has(a.fund_request_id)) articlesByFr.set(a.fund_request_id, []);
    articlesByFr.get(a.fund_request_id).push(a);
  }

  const rows = fundRequests.map((fr) => {
    const frRecipients = recipientsByFr.get(fr.id) || [];
    const frArticles = articlesByFr.get(fr.id) || [];
    return {
      'Fund Request Number': fr.fund_request_number || '',
      'Type': fr.fund_request_type === 'Article' ? 'Article' : (fr.aid_type || 'Aid'),
      'Status': fr.status || '',
      'Total Amount': asNumber(fr.total_amount),
      'Aid Type': fr.aid_type || '',
      'Supplier Name': fr.supplier_name || '',
      'GST Number': fr.gst_number || '',
      'Purchase Order Number': fr.purchase_order_number || '',
      'Notes': fr.notes || '',
      'Recipient Count': frRecipients.length,
      'Recipients': frRecipients.map((r) => `${r.recipient_name || ''} (${r.beneficiary_type || ''})`).join(' | '),
      'Article Names': frArticles.map((a) => a.supplier_article_name || a.article_name || '').join(' | '),
      'Article Quantity Total': frArticles.reduce((sum, a) => sum + asNumber(a.quantity), 0),
      'Article Value Total': frArticles.reduce((sum, a) => sum + asNumber(a.value), 0),
      'Created At': fr.created_at || '',
    };
  });

  rows.sort((a, b) => (b['Created At'] || '').localeCompare(a['Created At'] || ''));

  const headers = [
    'Fund Request Number',
    'Type',
    'Status',
    'Total Amount',
    'Aid Type',
    'Supplier Name',
    'GST Number',
    'Purchase Order Number',
    'Notes',
    'Recipient Count',
    'Recipients',
    'Article Names',
    'Article Quantity Total',
    'Article Value Total',
    'Created At',
  ];

  const filePath = path.join(OUTPUT_DIR, `fund_request_export_${timestamp}.csv`);
  writeCsv(filePath, headers, rows);
  return filePath;
}

async function buildOrderManagementExport(timestamp, articleMap) {
  const districtEntries = await fetchAllRows('district_beneficiary_entries', 'article_id,quantity');
  const publicEntries = await fetchAllRows('public_beneficiary_entries', 'article_id,quantity');
  const institutionEntries = await fetchAllRows('institutions_beneficiary_entries', 'article_id,quantity');
  const orders = await fetchAllRows('order_entries', 'article_id,quantity_ordered,status');

  const byArticle = new Map();
  const ensure = (articleId) => {
    if (!byArticle.has(articleId)) {
      byArticle.set(articleId, {
        district: 0,
        public: 0,
        institutions: 0,
        ordered: 0,
      });
    }
    return byArticle.get(articleId);
  };

  for (const row of districtEntries) ensure(row.article_id).district += asNumber(row.quantity);
  for (const row of publicEntries) ensure(row.article_id).public += asNumber(row.quantity);
  for (const row of institutionEntries) ensure(row.article_id).institutions += asNumber(row.quantity);
  for (const row of orders) {
    if (row.status !== 'cancelled') ensure(row.article_id).ordered += asNumber(row.quantity_ordered);
  }

  const rows = [];
  for (const [articleId, agg] of byArticle.entries()) {
    const article = articleMap.get(articleId);
    const totalNeeded = agg.district + agg.public + agg.institutions;
    if (totalNeeded === 0 && agg.ordered === 0) continue;

    rows.push({
      'Article Name': article?.article_name || articleId,
      'Item Type': article?.item_type || '',
      'Total Quantity Needed': totalNeeded,
      'Quantity Ordered': agg.ordered,
      'Quantity Pending': Math.max(0, totalNeeded - agg.ordered),
      'District': agg.district,
      'Public': agg.public,
      'Institutions': agg.institutions,
    });
  }

  rows.sort((a, b) => String(a['Article Name']).localeCompare(String(b['Article Name'])));

  const headers = [
    'Article Name',
    'Item Type',
    'Total Quantity Needed',
    'Quantity Ordered',
    'Quantity Pending',
    'District',
    'Public',
    'Institutions',
  ];

  const filePath = path.join(OUTPUT_DIR, `order_management_export_${timestamp}.csv`);
  writeCsv(filePath, headers, rows);
  return filePath;
}

async function buildArticleManagementExport(timestamp) {
  const articles = await fetchAllRows(
    'articles',
    'article_name,cost_per_unit,item_type,category,master_category,is_active,created_at,combo'
  );

  const rows = articles
    .filter((a) => !a.combo)
    .map((a) => ({
      'Article Name': a.article_name || '',
      'Cost Per Unit': asNumber(a.cost_per_unit),
      'Item Type': a.item_type || '',
      'Category': a.category || '',
      'Master Category': a.master_category || '',
      'Status': a.is_active ? 'Active' : 'Inactive',
      'Created At': a.created_at || '',
    }))
    .sort((a, b) => (b['Created At'] || '').localeCompare(a['Created At'] || ''));

  const headers = [
    'Article Name',
    'Cost Per Unit',
    'Item Type',
    'Category',
    'Master Category',
    'Status',
    'Created At',
  ];

  const filePath = path.join(OUTPUT_DIR, `article_management_export_${timestamp}.csv`);
  writeCsv(filePath, headers, rows);
  return filePath;
}

async function getDriveClient() {
  const mode = GOOGLE_AUTH_MODE;

  const buildServiceAccountClient = async () => {
    const serviceAccountJson = readEnv('GOOGLE_SERVICE_ACCOUNT_JSON');
    if (!serviceAccountJson) {
      throw new Error('Missing GOOGLE_SERVICE_ACCOUNT_JSON for service_account auth mode');
    }

    const credentials = JSON.parse(serviceAccountJson);
    const auth = new google.auth.GoogleAuth({
      credentials,
      scopes: ['https://www.googleapis.com/auth/drive'],
    });
    return google.drive({ version: 'v3', auth });
  };

  const buildOAuthClient = async () => {
    const clientId = readEnv('GOOGLE_OAUTH_CLIENT_ID');
    const clientSecret = readEnv('GOOGLE_OAUTH_CLIENT_SECRET');
    const refreshToken = readEnv('GOOGLE_OAUTH_REFRESH_TOKEN');
    if (!clientId || !clientSecret || !refreshToken) {
      throw new Error(
        'Missing OAuth env vars: GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, GOOGLE_OAUTH_REFRESH_TOKEN'
      );
    }

    const oauth2Client = new OAuth2Client({
      clientId,
      clientSecret,
    });
    oauth2Client.setCredentials({ refresh_token: refreshToken });

    try {
      await oauth2Client.getAccessToken();
    } catch (error) {
      const message = String(error?.message || error || '');
      if (message.includes('invalid_grant') || message.includes('Token has been expired or revoked')) {
        throw new Error(
          'Google OAuth refresh token is invalid/expired. Re-generate GOOGLE_OAUTH_REFRESH_TOKEN in Google Cloud and update GitHub secret.'
        );
      }
      throw error;
    }

    return google.drive({ version: 'v3', auth: oauth2Client });
  };

  if (mode === 'oauth_user') {
    try {
      return await buildOAuthClient();
    } catch (error) {
      const hasServiceAccount = !!readEnv('GOOGLE_SERVICE_ACCOUNT_JSON');
      if (!hasServiceAccount) throw error;
      console.warn(
        `OAuth user auth failed (${String(error?.message || error)}). Falling back to service account auth.`
      );
      return buildServiceAccountClient();
    }
  }

  return buildServiceAccountClient();
}

async function ensureDriveFolderPath(drive, targetPathRaw) {
  let normalizedPath = targetPathRaw
    .replace(/\\/g, '/')
    .replace(/^\/+|\/+$/g, '')
    .trim();

  const myDriveMarker = '/My Drive/';
  if (normalizedPath.includes(myDriveMarker)) {
    normalizedPath = normalizedPath.split(myDriveMarker)[1] || '';
  } else {
    normalizedPath = normalizedPath.replace(/^My Drive\/?/i, '');
  }

  if (!normalizedPath) return 'root';

  const segments = normalizedPath.split('/').filter(Boolean);
  let parentId = 'root';

  for (const segment of segments) {
    const escaped = segment.replace(/'/g, "\\'");
    const findRes = await drive.files.list({
      q: `'${parentId}' in parents and mimeType='application/vnd.google-apps.folder' and name='${escaped}' and trashed=false`,
      fields: 'files(id,name)',
      pageSize: 10,
      supportsAllDrives: true,
      includeItemsFromAllDrives: true,
    });

    if (findRes.data.files && findRes.data.files.length > 0) {
      parentId = findRes.data.files[0].id;
      continue;
    }

    const createRes = await drive.files.create({
      requestBody: {
        name: segment,
        mimeType: 'application/vnd.google-apps.folder',
        parents: [parentId],
      },
      fields: 'id',
      supportsAllDrives: true,
    });
    parentId = createRes.data.id;
  }

  return parentId;
}

async function uploadToDrive(drive, folderId, localFilePath) {
  const fileName = path.basename(localFilePath);
  await drive.files.create({
    requestBody: {
      name: fileName,
      parents: [folderId],
    },
    media: {
      mimeType: 'text/csv',
      body: fs.createReadStream(localFilePath),
    },
    fields: 'id,name',
    supportsAllDrives: true,
  });
  console.log(`Uploaded: ${fileName}`);
}

async function main() {
  const todayIst = getIstDateString();
  if (todayIst > EXPORT_CUTOFF_DATE) {
    console.log(`Skipping export because IST date ${todayIst} is after cutoff ${EXPORT_CUTOFF_DATE}.`);
    return;
  }

  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  const timestamp = getIstTimestamp();

  const articles = await fetchAllRows(
    'articles',
    'id,article_name,article_name_tk,cost_per_unit,item_type,category,master_category,is_active,combo'
  );
  const districts = await fetchAllRows(
    'district_master',
    'id,district_name,mobile_number,allotted_budget,is_active'
  );

  const articleMap = new Map(articles.map((a) => [a.id, a]));
  const districtMap = new Map(districts.map((d) => [d.id, d]));

  const outputFiles = [];
  outputFiles.push(await buildMasterEntryExport(timestamp, articleMap, districtMap));
  outputFiles.push(await buildFundRequestExport(timestamp));
  outputFiles.push(await buildOrderManagementExport(timestamp, articleMap));
  outputFiles.push(await buildArticleManagementExport(timestamp));

  if (SKIP_DRIVE_UPLOAD) {
    console.log(`SKIP_DRIVE_UPLOAD=true. Created local files only: ${outputFiles.join(', ')}`);
    return;
  }

  const targetFolderId = readEnv('GOOGLE_DRIVE_TARGET_FOLDER_ID');
  const targetPath = readEnv('GOOGLE_DRIVE_TARGET_PATH');

  if (!targetFolderId && !targetPath) {
    throw new Error('Missing target destination. Set GOOGLE_DRIVE_TARGET_FOLDER_ID or GOOGLE_DRIVE_TARGET_PATH');
  }

  if (GOOGLE_AUTH_MODE === 'service_account' && !targetFolderId && isMyDrivePath(targetPath)) {
    throw new Error(
      'Service-account mode cannot upload to My Drive paths. Use a Shared Drive folder ID via GOOGLE_DRIVE_TARGET_FOLDER_ID, or switch to oauth_user.'
    );
  }

  const drive = await getDriveClient();
  const folderId = targetFolderId || (await ensureDriveFolderPath(drive, targetPath));
  for (const filePath of outputFiles) {
    await uploadToDrive(drive, folderId, filePath);
  }

  console.log(`Finished exports. Files: ${outputFiles.length}`);
}

main().catch((error) => {
  console.error('Nightly export job failed:', error);
  process.exit(1);
});
