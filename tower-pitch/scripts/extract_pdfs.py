"""Export every PDF page as PNG (200 dpi) and every embedded image to public/assets/pdf/raw."""
import sys, pathlib, fitz

root = pathlib.Path(__file__).resolve().parent.parent
src = root / "input"
out = root / "public" / "assets" / "pdf" / "raw"
out.mkdir(parents=True, exist_ok=True)

for pdf in sorted(src.glob("*.pdf")):
    doc = fitz.open(pdf)
    stem = pdf.stem
    for pno, page in enumerate(doc, 1):
        page.get_pixmap(dpi=200).save(out / f"{stem}_p{pno:02d}.png")
        for i, img in enumerate(page.get_images(full=True), 1):
            xref = img[0]
            info = doc.extract_image(xref)
            if info["width"] < 400:
                continue
            (out / f"{stem}_p{pno:02d}_img{i}_{info['width']}x{info['height']}.{info['ext']}").write_bytes(info["image"])
    print(pdf.name, len(doc), "pages")
