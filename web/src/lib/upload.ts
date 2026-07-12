const ALLOWED = new Set(["image/png", "image/jpeg", "image/webp"]);
export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;

export function validateUpload(file: File): string | null {
  if (!ALLOWED.has(file.type)) return "Use uma imagem PNG, JPG ou WEBP.";
  if (file.size <= 0) return "A imagem está vazia.";
  if (file.size > MAX_UPLOAD_BYTES) return "A imagem deve ter no máximo 20 MB.";
  return null;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
