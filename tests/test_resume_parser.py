import pytest

from resume_parser import ResumeInputError, extract_resume_text
from tests.conftest import RESUME, make_docx, make_pdf


def test_pdf_ok():
    assert "Flask" in extract_resume_text("cv.PDF", make_pdf("Python developer\nFlask and MongoDB"))


def test_docx_ok_including_tables():
    text = extract_resume_text("cv.docx", make_docx("Python developer", table_cell="Skills: Kubernetes"))
    assert "Python developer" in text and "Kubernetes" in text


@pytest.mark.parametrize("name", ["cv.txt", "cv.exe", "cv", "cv.pdf.exe"])
def test_unsupported_extensions(name):
    with pytest.raises(ResumeInputError, match="Unsupported"):
        extract_resume_text(name, b"data")


def test_empty_file():
    with pytest.raises(ResumeInputError, match="empty"):
        extract_resume_text("cv.pdf", b"")


def test_fake_pdf_and_docx_content_rejected():
    with pytest.raises(ResumeInputError, match="not a real PDF"):
        extract_resume_text("cv.pdf", b"MZ\x90 not a pdf")
    with pytest.raises(ResumeInputError, match="not a real DOCX"):
        extract_resume_text("cv.docx", b"plain text")


def test_corrupt_pdf_and_docx():
    with pytest.raises(ResumeInputError, match="Unable to read"):
        extract_resume_text("cv.pdf", b"%PDF-1.4\ngarbage garbage")
    import io, zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("hello.txt", "hi")
    with pytest.raises(ResumeInputError, match="not a valid DOCX"):
        extract_resume_text("cv.docx", buf.getvalue())


def test_empty_text_pdf():
    with pytest.raises(ResumeInputError, match="No text"):
        extract_resume_text("cv.pdf", make_pdf(""))
