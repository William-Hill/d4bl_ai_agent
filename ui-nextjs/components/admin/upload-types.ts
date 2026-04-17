export interface UploadRecord {
  id: string;
  upload_type: string;
  status: string;
  original_filename: string | null;
  file_size_bytes: number | null;
  metadata: Record<string, unknown> | null;
  uploader_email: string | null;
  uploader_name: string | null;
  reviewer_notes: string | null;
  created_at: string;
}
