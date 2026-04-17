export interface UploadRecord {
  id: string;
  upload_type: string;
  status: string;
  original_filename: string;
  file_size_bytes: number | null;
  metadata: Record<string, unknown> | null;
  uploader_email: string;
  uploader_name: string | null;
  created_at: string;
}
