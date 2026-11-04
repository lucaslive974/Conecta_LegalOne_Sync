import os

from source.document_generator import DocumentGenerator, sanitize_filename


def test_sanitize_filename():
    assert sanitize_filename("Processo: 123/456*?") == "Processo_ 123_456__"
    assert sanitize_filename("") == "SEM_NOME"
    assert len(sanitize_filename("A" * 200)) == 120


def test_generate_process_docx(tmp_path, sample_lawsuit_data):
    generator = DocumentGenerator(str(tmp_path))
    out_docx = tmp_path / "relatorio_teste.docx"

    result_path = generator.generate_process_docx(sample_lawsuit_data, str(out_docx))
    assert os.path.exists(result_path)
    assert os.path.getsize(result_path) > 1000


def test_convert_docx_to_pdf_not_found(tmp_path):
    generator = DocumentGenerator(str(tmp_path))
    res = generator.convert_docx_to_pdf(str(tmp_path / "inexistente.docx"))
    assert res is None


def test_convert_docx_to_pdf_mock_success(tmp_path, mocker):
    generator = DocumentGenerator(str(tmp_path))
    fake_docx = tmp_path / "doc.docx"
    fake_docx.write_text("dummy")

    fake_pdf = tmp_path / "doc.pdf"
    fake_pdf.write_text("dummy pdf")

    mock_run = mocker.MagicMock()
    mock_run.returncode = 0
    mocker.patch("subprocess.run", return_value=mock_run)

    res = generator.convert_docx_to_pdf(str(fake_docx))
    assert res == str(fake_pdf)
