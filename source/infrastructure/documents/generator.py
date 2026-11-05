import logging
import os
import re
import subprocess
from datetime import datetime
from typing import Any

import docx
from docx.document import Document as DocxDocument
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
from docx.shared import Inches, Pt, RGBColor

from source.domain.cnj import parse_cnj
from source.domain.models import Lawsuit, Party, Progress

logger = logging.getLogger(__name__)

# Apple-style monochromatic palette
COLOR_BLACK = RGBColor(29, 29, 31)  # #1D1D1F
COLOR_DARK = RGBColor(66, 66, 69)  # #424245
COLOR_MUTED = RGBColor(134, 134, 139)  # #86868B
HEX_SURFACE = "F5F5F7"  # #F5F5F7 (Cinza neutro suave)
HEX_BORDER = "E5E5EA"  # #E5E5EA (Borda sutil)
HEX_BLACK = "1D1D1F"  # #1D1D1F


def sanitize_filename(name: str) -> str:
    """Sanitize names for files and directories."""
    if not name:
        return "SEM_NOME"
    clean = re.sub(r'[<>:"/\\|?*\n\r\t]', "_", name).strip()
    return clean[:120] if len(clean) > 120 else clean


def set_cell_background(cell, fill_hex: str):
    """Set the background color of a table cell."""
    tcPr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    tcPr.append(shd)


def set_cell_margins(cell, top=100, bottom=100, left=140, right=140):
    """Set internal margins of a table cell."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(
        f"<w:tcMar {nsdecls('w')}>"
        f'<w:top w:w="{top}" w:type="dxa"/>'
        f'<w:bottom w:w="{bottom}" w:type="dxa"/>'
        f'<w:left w:w="{left}" w:type="dxa"/>'
        f'<w:right w:w="{right}" w:type="dxa"/>'
        f"</w:tcMar>"
    )
    tcPr.append(tcMar)


def set_table_borders(table, color=HEX_BORDER, sz="4"):
    """Apply soft, clean borders to a table."""
    tblPr = table._tbl.tblPr
    borders = parse_xml(
        f"<w:tblBorders {nsdecls('w')}>"
        f'<w:top w:val="single" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'<w:bottom w:val="single" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'<w:insideH w:val="single" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'<w:insideV w:val="none"/>'
        f'<w:left w:val="none"/>'
        f'<w:right w:val="none"/>'
        f"</w:tblBorders>"
    )
    tblPr.append(borders)


class DocumentGenerator:
    """Generate structured DOCX documents and convert to PDF following a clean minimalist Apple design."""

    def __init__(self, temp_dir: str):
        self.temp_dir = temp_dir
        os.makedirs(temp_dir, exist_ok=True)

    @staticmethod
    def _setup_document_margins(doc: DocxDocument, margin_inches: float = 0.8) -> None:
        """Configure page margins across document sections."""
        for section in doc.sections:
            section.top_margin = Inches(margin_inches)
            section.bottom_margin = Inches(margin_inches)
            section.left_margin = Inches(margin_inches)
            section.right_margin = Inches(margin_inches)

    @staticmethod
    def _add_document_header(doc: DocxDocument, pasta: str, cnj: str, cnj_info: Any) -> None:
        """Add Apple-style minimalist header eyebrow, title, subtitle, and divider."""
        p_header = doc.add_paragraph()
        p_header.paragraph_format.space_before = Pt(0)
        p_header.paragraph_format.space_after = Pt(2)
        run_eyebrow = p_header.add_run("CONECTA LEGALONE • RELATÓRIO PROCESSUAL")
        run_eyebrow.font.name = "Segoe UI"
        run_eyebrow.font.size = Pt(8.5)
        run_eyebrow.font.bold = True
        run_eyebrow.font.color.rgb = COLOR_MUTED

        p_title = doc.add_paragraph()
        p_title.paragraph_format.space_before = Pt(0)
        p_title.paragraph_format.space_after = Pt(4)
        run_title = p_title.add_run(f"Processo: {cnj}")
        run_title.font.name = "Segoe UI"
        run_title.font.size = Pt(17)
        run_title.font.bold = True
        run_title.font.color.rgb = COLOR_BLACK

        # Subtitle: Folder + Tribunal / Year + Issue timestamp
        p_sub = doc.add_paragraph()
        p_sub.paragraph_format.space_before = Pt(0)
        p_sub.paragraph_format.space_after = Pt(12)
        is_valid = getattr(cnj_info, "is_valid", cnj_info.get("is_valid") if isinstance(cnj_info, dict) else False)
        sigla = getattr(
            cnj_info, "tribunal_sigla", cnj_info.get("tribunal_sigla") if isinstance(cnj_info, dict) else ""
        )
        ano = getattr(cnj_info, "ano", cnj_info.get("ano") if isinstance(cnj_info, dict) else "")

        if is_valid:
            sub_meta = (
                f"Pasta: {pasta}  •  {sigla} ({ano})  •  Emitido em: {datetime.now().strftime('%d/%m/%Y às %H:%M')}"
            )
        else:
            sub_meta = f"Pasta: {pasta}  •  Emitido em: {datetime.now().strftime('%d/%m/%Y às %H:%M')}"
        run_sub = p_sub.add_run(sub_meta)
        run_sub.font.name = "Segoe UI"
        run_sub.font.size = Pt(9.5)
        run_sub.font.color.rgb = COLOR_MUTED

        # Subtle divider
        p_hr = doc.add_paragraph()
        p_hr.paragraph_format.space_before = Pt(0)
        p_hr.paragraph_format.space_after = Pt(10)
        p_hr_border = parse_xml(
            f'<w:pBdr {nsdecls("w")}><w:bottom w:val="single" w:sz="6" w:space="1" w:color="{HEX_BORDER}"/></w:pBdr>'
        )
        p_hr._p.get_or_add_pPr().append(p_hr_border)

    @staticmethod
    def _add_general_data_section(
        doc: DocxDocument,
        proc: Any,
        cnj: str,
        cnj_info: Any,
    ) -> None:
        """Add '1. Dados Gerais do Processo' section with key metadata table."""
        h1 = doc.add_heading("1. Dados Gerais do Processo", level=2)
        h1.paragraph_format.space_before = Pt(8)
        h1.paragraph_format.space_after = Pt(6)
        for r in h1.runs:
            r.font.name = "Segoe UI"
            r.font.size = Pt(11.5)
            r.font.bold = True
            r.font.color.rgb = COLOR_BLACK

        if isinstance(proc, Lawsuit):
            p_id_str = str(proc.id)
            pasta = proc.pasta or "N/A"
            valor = proc.valor_causa
            status_nome = proc.status_nome
            dt_atualizacao = proc.dt_hr_ultima_atualizacao or "N/A"
        else:
            p_id_str = str(proc.get("id") or "N/A")
            pasta = proc.get("pasta") or "N/A"
            valor = proc.get("valorCausa")
            status_info = proc.get("status") or {}
            status_nome = (
                str(status_info.get("nome") or "Não informado")
                if isinstance(status_info, dict)
                else str(status_info or "Não informado")
            )
            dt_atualizacao = proc.get("dtHrUltimaAtualizacaoDc") or proc.get("dtHrUltimaAtualizacao") or "N/A"

        valor_str = (
            f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if valor else "Não informado"
        )

        is_valid = getattr(cnj_info, "is_valid", cnj_info.get("is_valid") if isinstance(cnj_info, dict) else False)
        sigla = getattr(
            cnj_info, "tribunal_sigla", cnj_info.get("tribunal_sigla") if isinstance(cnj_info, dict) else "N/A"
        )
        nome_trib = getattr(
            cnj_info, "tribunal_nome", cnj_info.get("tribunal_nome") if isinstance(cnj_info, dict) else "Não informado"
        )
        ramo = getattr(cnj_info, "ramo", cnj_info.get("ramo") if isinstance(cnj_info, dict) else "N/A")
        ano = getattr(cnj_info, "ano", cnj_info.get("ano") if isinstance(cnj_info, dict) else "N/A")
        origem_cod = getattr(
            cnj_info, "origem_codigo", cnj_info.get("origem_codigo") if isinstance(cnj_info, dict) else "N/A"
        )

        tribunal_display = f"{sigla} - {nome_trib}" if is_valid else nome_trib

        meta_fields = [
            ("Número CNJ", cnj, "ID Conecta", p_id_str),
            ("Tribunal Competente", tribunal_display, "Esfera / Ramo", ramo),
            ("Ano de Distribuição", ano, "Status", status_nome),
            ("Valor da Causa", valor_str, "Pasta", pasta),
            (
                "Cód. Comarca / Foro",
                origem_cod,
                "Última Atualização",
                str(dt_atualizacao),
            ),
        ]

        table_meta = doc.add_table(rows=len(meta_fields), cols=4)
        table_meta.alignment = WD_TABLE_ALIGNMENT.CENTER
        table_meta.autofit = False
        set_table_borders(table_meta, color=HEX_BORDER)

        col_widths = [Inches(1.5), Inches(2.0), Inches(1.5), Inches(2.0)]
        for row in table_meta.rows:
            for idx, width in enumerate(col_widths):
                row.cells[idx].width = width

        for r_idx, (k1, v1, k2, v2) in enumerate(meta_fields):
            row = table_meta.rows[r_idx]
            c0, c1, c2, c3 = row.cells[0], row.cells[1], row.cells[2], row.cells[3]
            for c in (c0, c1, c2, c3):
                set_cell_margins(c, top=80, bottom=80, left=100, right=100)

            # Label 1
            set_cell_background(c0, HEX_SURFACE)
            p = c0.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            run = p.add_run(k1)
            run.font.name = "Segoe UI"
            run.font.size = Pt(8.5)
            run.font.bold = True
            run.font.color.rgb = COLOR_MUTED

            # Value 1
            p = c1.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            run = p.add_run(v1)
            run.font.name = "Segoe UI"
            run.font.size = Pt(9)
            run.font.color.rgb = COLOR_BLACK

            # Label 2
            set_cell_background(c2, HEX_SURFACE)
            p = c2.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            run = p.add_run(k2)
            run.font.name = "Segoe UI"
            run.font.size = Pt(8.5)
            run.font.bold = True
            run.font.color.rgb = COLOR_MUTED

            # Value 2
            p = c3.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            run = p.add_run(v2)
            run.font.name = "Segoe UI"
            run.font.size = Pt(9)
            run.font.color.rgb = COLOR_BLACK

    @staticmethod
    def _add_parties_section(doc: DocxDocument, contatos: list[Any]) -> None:
        """Add '2. Polos Processuais e Partes' section with parties table."""
        doc.add_paragraph().paragraph_format.space_after = Pt(4)
        h2 = doc.add_heading("2. Polos Processuais e Partes", level=2)
        h2.paragraph_format.space_before = Pt(12)
        h2.paragraph_format.space_after = Pt(6)
        for r in h2.runs:
            r.font.name = "Segoe UI"
            r.font.size = Pt(11.5)
            r.font.bold = True
            r.font.color.rgb = COLOR_BLACK

        if not contatos:
            p_none = doc.add_paragraph("Nenhuma parte ou contato vinculado registrado.")
            p_none.runs[0].font.italic = True
            p_none.runs[0].font.size = Pt(9)
            p_none.runs[0].font.color.rgb = COLOR_MUTED
            return

        table_cont = doc.add_table(rows=len(contatos) + 1, cols=3)
        table_cont.alignment = WD_TABLE_ALIGNMENT.CENTER
        table_cont.autofit = False
        set_table_borders(table_cont, color=HEX_BORDER)

        col_w = [Inches(1.8), Inches(3.6), Inches(1.6)]
        for row in table_cont.rows:
            for idx, width in enumerate(col_w):
                row.cells[idx].width = width

        # Header
        hdr = table_cont.rows[0]
        for idx, title in enumerate(["Posição / Polo", "Nome da Parte / Razão Social", "Documento / Detalhes"]):
            cell = hdr.cells[idx]
            set_cell_background(cell, HEX_SURFACE)
            set_cell_margins(cell, top=100, bottom=100, left=100, right=100)
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            run = p.add_run(title)
            run.font.name = "Segoe UI"
            run.font.size = Pt(8.5)
            run.font.bold = True
            run.font.color.rgb = COLOR_MUTED

        for idx, c in enumerate(contatos, start=1):
            row = table_cont.rows[idx]
            if isinstance(c, Party):
                pos = c.posicao or "Interessado"
                nome = c.nome or "Não informado"
                doc_cpf_cnpj = "Principal" if c.is_main_party else "-"
            else:
                pos = (c.get("posicaoEnvolvido") or {}).get("descricao", "Interessado")
                agn = c.get("agnContato") or {}
                nome = agn.get("nome", "Não informado")
                doc_cpf_cnpj = agn.get("cpfCnpj") or ("Principal" if c.get("isPrincipal") else "-")

            c0, c1, c2 = row.cells[0], row.cells[1], row.cells[2]
            for cell in (c0, c1, c2):
                set_cell_margins(cell, top=80, bottom=80, left=100, right=100)

            # Posicao
            p0 = c0.paragraphs[0]
            p0.paragraph_format.space_after = Pt(0)
            r0 = p0.add_run(pos)
            r0.font.name = "Segoe UI"
            r0.font.size = Pt(8.5)
            r0.font.bold = True
            r0.font.color.rgb = COLOR_DARK

            # Nome
            p1 = c1.paragraphs[0]
            p1.paragraph_format.space_after = Pt(0)
            r1 = p1.add_run(nome)
            r1.font.name = "Segoe UI"
            r1.font.size = Pt(9)
            r1.font.color.rgb = COLOR_BLACK

            # Documento / Detalhe
            p2 = c2.paragraphs[0]
            p2.paragraph_format.space_after = Pt(0)
            r2 = p2.add_run(doc_cpf_cnpj)
            r2.font.name = "Segoe UI"
            r2.font.size = Pt(8.5)
            r2.font.color.rgb = COLOR_MUTED

    @staticmethod
    def _add_progress_section(doc: DocxDocument, andamentos: list[Any]) -> None:
        """Add '3. Andamentos e Publicações' timeline and blockquote entries."""
        doc.add_paragraph().paragraph_format.space_after = Pt(4)
        h3 = doc.add_heading(f"3. Andamentos e Publicações ({len(andamentos)})", level=2)
        h3.paragraph_format.space_before = Pt(14)
        h3.paragraph_format.space_after = Pt(6)
        for r in h3.runs:
            r.font.name = "Segoe UI"
            r.font.size = Pt(11.5)
            r.font.bold = True
            r.font.color.rgb = COLOR_BLACK

        if not andamentos:
            p_none = doc.add_paragraph("Nenhum andamento ou publicação registrado para este processo até o momento.")
            p_none.runs[0].font.italic = True
            p_none.runs[0].font.size = Pt(9)
            p_none.runs[0].font.color.rgb = COLOR_MUTED
            return

        for idx, andam in enumerate(andamentos, 1):
            if isinstance(andam, Progress):
                data = andam.data
                hora = andam.hora
                origem_full = f"{andam.origem} • {andam.caderno}" if andam.caderno else andam.origem
                desc = andam.descricao
            else:
                data = andam.get("strData") or (andam.get("dtHrAndamento") or "")[:10]
                hora = andam.get("strHora") or ""
                origem = andam.get("source") or (
                    "Diário Oficial" if andam.get("tipoOrigem") == 1 else "Sistema Judicial"
                )
                caderno = andam.get("nomeCaderno")
                origem_full = f"{origem} • {caderno}" if caderno else origem
                desc = (andam.get("descricao") or "").strip()

            p_item = doc.add_paragraph()
            p_item.paragraph_format.space_before = Pt(8)
            p_item.paragraph_format.space_after = Pt(2)
            p_item.paragraph_format.keep_with_next = True

            # Minimalist numbered index
            run_num = p_item.add_run(f"#{idx} ")
            run_num.font.name = "Segoe UI"
            run_num.font.size = Pt(9)
            run_num.font.bold = True
            run_num.font.color.rgb = COLOR_MUTED

            run_dt = p_item.add_run(f"[{data} {hora}] ")
            run_dt.font.name = "Segoe UI"
            run_dt.font.size = Pt(9)
            run_dt.font.bold = True
            run_dt.font.color.rgb = COLOR_BLACK

            run_orig = p_item.add_run(f"— {origem_full}")
            run_orig.font.name = "Segoe UI"
            run_orig.font.size = Pt(8.5)
            run_orig.font.color.rgb = COLOR_MUTED

            # Update blockquote box with matte left border
            p_desc = doc.add_paragraph()
            p_desc.paragraph_format.left_indent = Inches(0.2)
            p_desc.paragraph_format.space_before = Pt(0)
            p_desc.paragraph_format.space_after = Pt(6)

            pBdr = parse_xml(
                f'<w:pBdr {nsdecls("w")}><w:left w:val="single" w:sz="14" w:space="8" w:color="{HEX_BLACK}"/></w:pBdr>'
            )
            p_desc._p.get_or_add_pPr().append(pBdr)

            run_txt = p_desc.add_run(desc if desc else "(Sem descrição registrada)")
            run_txt.font.name = "Segoe UI"
            run_txt.font.size = Pt(8.5)
            run_txt.font.color.rgb = COLOR_DARK

    @staticmethod
    def _add_document_footer(doc: DocxDocument) -> None:
        """Add confidentiality notice and timestamp to section footer."""
        footer = doc.sections[0].footer
        p_ft = footer.paragraphs[0]
        p_ft.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        run_ft = p_ft.add_run(
            f"Conecta LegalOne • Documento Confidencial • {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        )
        run_ft.font.name = "Segoe UI"
        run_ft.font.size = Pt(7.5)
        run_ft.font.color.rgb = COLOR_MUTED

    def generate_process_docx(self, proc: Lawsuit | dict[str, Any], output_path: str) -> str:
        """Create a lawsuit report in minimalist DOCX format."""
        doc = docx.Document()
        self._setup_document_margins(doc)

        if isinstance(proc, Lawsuit):
            cnj = proc.cnj
            pasta = proc.pasta or "N/A"
            cnj_info = proc.cnj_info
            contatos = proc.partes
            andamentos = proc.andamentos
        else:
            cnj = proc.get("numeroCNJ") or f"ID_{proc.get('id')}"
            pasta = proc.get("pasta") or "N/A"
            cnj_info = parse_cnj(cnj)
            contatos = proc.get("contatos") or []
            andamentos = proc.get("recentProgresses") or proc.get("progresses") or []

        # 1. Header with title and metadata
        self._add_document_header(doc, pasta=pasta, cnj=cnj, cnj_info=cnj_info)

        # 2. General lawsuit data table
        self._add_general_data_section(doc, proc=proc, cnj=cnj, cnj_info=cnj_info)

        # 3. Parties and stakeholders table
        self._add_parties_section(doc, contatos)

        # 4. Updates and publications timeline
        self._add_progress_section(doc, andamentos)

        # 5. Confidential footer
        self._add_document_footer(doc)

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        doc.save(output_path)
        logger.debug("DOCX gerado em: %s", output_path)
        return output_path

    def convert_docx_to_pdf(self, docx_path: str, out_dir: str | None = None) -> str | None:
        """
        Convert a DOCX file to PDF using LibreOffice headless.
        Returns the generated PDF file path or None on failure.
        """
        if not os.path.exists(docx_path):
            logger.error("Arquivo DOCX não encontrado para conversão: %s", docx_path)
            return None

        target_dir = out_dir or os.path.dirname(docx_path)
        os.makedirs(target_dir, exist_ok=True)

        cmd = ["soffice", "--headless", "--convert-to", "pdf", "--outdir", target_dir, docx_path]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if res.returncode != 0:
                logger.warning("LibreOffice retornou código %s: %s", res.returncode, res.stderr)
                return None

            base_name = os.path.splitext(os.path.basename(docx_path))[0]
            pdf_path = os.path.join(target_dir, f"{base_name}.pdf")
            if os.path.exists(pdf_path):
                logger.debug("PDF gerado com sucesso: %s", pdf_path)
                return pdf_path
            else:
                logger.warning("PDF não foi localizado após comando do LibreOffice em: %s", pdf_path)
                return None
        except Exception as e:
            logger.error("Falha ao converter DOCX para PDF via LibreOffice: %s", e)
            return None

    def render_process_documents(self, proc: Lawsuit | dict[str, Any], base_name: str) -> tuple[str, str | None]:
        """Render both DOCX and PDF in temporary folder and return (docx_path, pdf_path)."""
        safe_name = sanitize_filename(base_name)
        docx_path = os.path.join(self.temp_dir, f"{safe_name}.docx")
        self.generate_process_docx(proc, docx_path)
        pdf_path = self.convert_docx_to_pdf(docx_path, self.temp_dir)
        return docx_path, pdf_path
