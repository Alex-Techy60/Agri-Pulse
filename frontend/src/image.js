// A phone camera photo is 3-12 MB; the server accepts about 5 MB and a diagnosis needs far less. Shrink it in the browser first.
const MAX_SIDE = 1024;
const QUALITY = 0.85;

/** Resolves {b64, previewUrl, name}. b64 is raw base64 (no "data:" prefix), JPEG, longest side at most 1024 px. Rejects if the image cannot be decoded. */
export async function prepareImage(file) {
  const bmp = await createImageBitmap(file, { imageOrientation: "from-image" }); // honours the camera's rotation flag
  const k = Math.min(1, MAX_SIDE / Math.max(bmp.width, bmp.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bmp.width * k);
  canvas.height = Math.round(bmp.height * k);
  canvas.getContext("2d").drawImage(bmp, 0, 0, canvas.width, canvas.height);
  bmp.close?.();
  const blob = await new Promise((ok, bad) => canvas.toBlob((b) => (b ? ok(b) : bad(new Error("encode failed"))), "image/jpeg", QUALITY));
  const b64 = await new Promise((ok, bad) => {
    const fr = new FileReader();
    fr.onload = () => ok(String(fr.result).split(",")[1]);
    fr.onerror = bad;
    fr.readAsDataURL(blob);
  });
  return { b64, previewUrl: URL.createObjectURL(blob), name: file.name };
}
