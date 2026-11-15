"""
Kỹ năng chạy được: TÓM LƯỢC NHANH NỘI DUNG MỘT THƯ MỤC (thay cho nhiều lượt read_file_content).
Từ khóa: thư mục, tài liệu, tóm tắt, pdf, word, docx, txt, md, slide, chapter, chương, đọc, tệp, folder, digest

Cách dùng:  run_skill('folder_digest', '{"folder": "D:\\\\KTMT", "max_files": 6, "chars_per_file": 900}')
Tham số JSON: folder (bắt buộc) · max_files (mặc định 6) · chars_per_file (mặc định 900) · pattern (mặc định "*")
Kết quả: với mỗi tệp (sắp xếp theo tên): tên, dung lượng, và phần đầu nội dung (PDF: các trang đầu; .docx: các đoạn đầu).
"""
import json
import sys
from pathlib import Path

TEXT_EXT = {".txt", ".md", ".py", ".json", ".csv", ".log", ".html", ".xml"}


def read_head(path: Path, limit: int) -> str:
    ext = path.suffix.lower()
    try:
        if ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            out = []
            for page in reader.pages[:6]:
                out.append((page.extract_text() or "").strip())
                if sum(map(len, out)) >= limit:
                    break
            return "\n".join(out)[:limit]
        if ext == ".docx":
            import docx
            paras = [p.text for p in docx.Document(str(path)).paragraphs if p.text.strip()]
            return "\n".join(paras)[:limit]
        if ext in TEXT_EXT:
            return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except Exception as e:
        return f"(không đọc được: {e})"
    return "(định dạng không hỗ trợ trích chữ)"


def main():
    args = json.loads(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] else {}
    folder = Path(str(args.get("folder", "")).strip().strip('"'))
    if not folder.is_dir():
        print(f"Lỗi: không tìm thấy thư mục '{folder}'")
        sys.exit(1)
    max_files = int(args.get("max_files", 6))
    limit = int(args.get("chars_per_file", 900))
    files = sorted(p for p in folder.glob(args.get("pattern", "*")) if p.is_file())
    print(f"Thư mục: {folder} ({len(files)} tệp, hiển thị {min(len(files), max_files)})")
    for p in files[:max_files]:
        print(f"\n### {p.name} ({p.stat().st_size // 1024} KB)")
        print(read_head(p, limit))
    if len(files) > max_files:
        print("\nTệp còn lại: " + ", ".join(p.name for p in files[max_files:max_files + 20]))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
