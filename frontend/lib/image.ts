/** Prepare a user image before upload: shrink big camera photos in the browser when it can decode them.
 *  Formats the browser can't decode (e.g. HEIC in Chrome) are sent unchanged; the server converts them. */

const MAX_SIDE = 2400;
const SHRINK_ABOVE_BYTES = 3 * 1024 * 1024;
const HEIC = /\.(heic|heif)$/i;

export function looksLikeImage(file: File): boolean {
  return file.type.startsWith("image/") || HEIC.test(file.name) || /\.(avif|tiff?|bmp|gif|webp|png|jpe?g)$/i.test(file.name);
}

export type Prepared = { file: File; previewUrl: string | null };

export async function prepareImage(file: File): Promise<Prepared> {
  let bitmap: ImageBitmap | null = null;
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch {
    return { file, previewUrl: null }; // can't decode here: let the server handle it
  }
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
  const needsWork = scale < 1 || file.size > SHRINK_ABOVE_BYTES || HEIC.test(file.name);
  if (!needsWork) {
    bitmap.close();
    return { file, previewUrl: URL.createObjectURL(file) };
  }
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  const blob: Blob | null = await new Promise((r) => canvas.toBlob(r, "image/jpeg", 0.92));
  if (!blob) return { file, previewUrl: null };
  const out = new File([blob], file.name.replace(/\.[^.]+$/, "") + ".jpg", { type: "image/jpeg" });
  return { file: out, previewUrl: URL.createObjectURL(out) };
}
