/** RFC 4180 field quoting. */
export function csvField(value: unknown): string {
  if (value === null || value === undefined) return '';
  const text = typeof value === 'object' ? JSON.stringify(value) : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function toCsv(header: string[], rows: unknown[][]): string {
  return [header, ...rows].map((row) => row.map(csvField).join(',')).join('\r\n') + '\r\n';
}

/** Saves text as a file. A UTF-8 BOM lets Excel open Turkish characters correctly. */
export function downloadText(fileName: string, text: string, mime = 'text/csv;charset=utf-8', bom = true): void {
  const blob = new Blob([bom ? '﻿' : '', text], { type: mime });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
