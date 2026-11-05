import os

import docx

from source.cnj_parser import parse_cnj
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


def test_document_sections_modular(tmp_path):
    generator = DocumentGenerator(str(tmp_path))
    doc = docx.Document()

    # 1. Setup margins
    generator._setup_document_margins(doc, margin_inches=0.8)
    assert doc.sections[0].top_margin.inches == 0.8

    # 2. Header
    cnj_info = parse_cnj("5003140-58.2023.8.13.0439")
    generator._add_document_header(doc, pasta="P-100", cnj="5003140-58.2023.8.13.0439", cnj_info=cnj_info)
    assert any("5003140-58.2023.8.13.0439" in p.text for p in doc.paragraphs)

    # Header with invalid CNJ
    invalid_info = parse_cnj("invalid")
    generator._add_document_header(doc, pasta="P-200", cnj="invalid", cnj_info=invalid_info)

    # 3. General data section
    proc = {
        "id": 10,
        "pasta": "PASTA_A",
        "valorCausa": 50000.0,
        "status": {"nome": "Ativo"},
        "dtHrUltimaAtualizacaoDc": "2026-03-01",
    }
    generator._add_general_data_section(doc, proc, "5003140-58.2023.8.13.0439", cnj_info)
    assert len(doc.tables) >= 1

    # 4. Parties section - with parties and empty
    generator._add_parties_section(doc, [{"agnContato": {"nome": "Empresa"}, "isPrincipal": True}])
    generator._add_parties_section(doc, [])

    # 5. Progress section - with items and empty
    generator._add_progress_section(doc, [{"strData": "01/01/2026", "descricao": "Movimento"}])
    generator._add_progress_section(doc, [])

    # 6. Footer
    generator._add_document_footer(doc)
    footer_text = doc.sections[0].footer.paragraphs[0].text
    assert "Documento Confidencial" in footer_text


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


def test_render_process_documents(tmp_path, sample_lawsuit_data, mocker):
    generator = DocumentGenerator(str(tmp_path))

    fake_pdf = tmp_path / "base_test.pdf"
    fake_pdf.write_text("pdf dummy")
    mocker.patch.object(generator, "convert_docx_to_pdf", return_value=str(fake_pdf))

    docx_path, pdf_path = generator.render_process_documents(sample_lawsuit_data, base_name="base_test")
    assert os.path.exists(docx_path)
    assert pdf_path == str(fake_pdf)
