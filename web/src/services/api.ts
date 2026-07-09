const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"; export async function generateImage(file: 
File) {
  const form = new FormData(); form.append("file", file); const response = await fetch(`${API_URL}/generate/image`, { 
    method: "POST", body: form,
  });
  return response.json();
}
export function downloadUrl(jobId: string) { return `${API_URL}/download/${jobId}`;
}
