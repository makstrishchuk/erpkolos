#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF парсер для Lieferschein
Извлекает данные из PDF файлов Lieferschein
"""

import re
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

try:
    import pdfplumber
    PDF_LIBRARY = 'pdfplumber'
except ImportError:
    try:
        import PyPDF2
        PDF_LIBRARY = 'PyPDF2'
    except ImportError:
        PDF_LIBRARY = None
        logger.warning("No PDF library found. Install pdfplumber or PyPDF2")


class LieferscheinPDFParser:
    """Парсер PDF файлов Lieferschein"""

    def __init__(self):
        self.library = PDF_LIBRARY

    def extract_text_pdfplumber(self, pdf_path: Path) -> str:
        """Извлечение текста с помощью pdfplumber"""
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text() + "\n"
        return text

    def extract_text_pypdf2(self, pdf_path: Path) -> str:
        """Извлечение текста с помощью PyPDF2"""
        text = ""
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                text += page.extract_text() + "\n"
        return text

    def extract_text(self, pdf_path: Path) -> str:
        """Извлечение текста из PDF"""
        if self.library == 'pdfplumber':
            return self.extract_text_pdfplumber(pdf_path)
        elif self.library == 'PyPDF2':
            return self.extract_text_pypdf2(pdf_path)
        else:
            raise Exception("No PDF library available. Install pdfplumber or PyPDF2")

    def parse_lieferschein(self, pdf_path: Path) -> dict:
        """
        Парсинг Lieferschein PDF файла (рабочая версия из arbeitet)

        Returns:
            dict: {
                'lieferschein_nummer': str (или 'nummer' для совместимости),
                'datum': str,
                'kunde': str,
                'adresse': str,
                'kunden_nr': str,
                'artikel': [
                    {'nummer': str, 'name': str, 'menge': int},
                    ...
                ]
            }
        """
        try:
            result = {'artikel': []}

            # Используем pdfplumber для точного извлечения
            if self.library != 'pdfplumber':
                raise Exception("pdfplumber required for Lieferschein parsing. Install: pip install pdfplumber")

            with pdfplumber.open(pdf_path) as pdf:
                # ИСПРАВЛЕНИЕ: Извлекаем текст с сохранением переносов строк между страницами
                full_text = "\n".join(p.extract_text(x_tolerance=2) or "" for p in pdf.pages)

                # Извлекаем номер Lieferschein
                nr_match = re.search(r'Lieferschein-Nr\.:\s*(\d+)', full_text)
                result['nummer'] = nr_match.group(1) if nr_match else None
                result['lieferschein_nummer'] = result['nummer']  # Для совместимости

                # Извлекаем Datum
                datum_match = re.search(r'Datum:?\s*(\d{2}\.\d{2}\.\d{4})', full_text)
                result['datum'] = datum_match.group(1) if datum_match else ''

                # Извлекаем Kunden-Nr
                kunden_match = re.search(r'Kunden-Nr\.?:?\s*(\d+)', full_text, re.IGNORECASE)
                result['kunden_nr'] = kunden_match.group(1) if kunden_match else ''

                # Извлекаем адрес из области страницы (как в рабочей версии)
                p0 = pdf.pages[0]
                w, h = p0.width, p0.height

                # Вырезаем область с адресом (15-35% по высоте, левая половина)
                address_crop = p0.crop((0, h*0.15, w*0.5, h*0.35))
                address_text = address_crop.extract_text()

                if address_text:
                    lines = [line.strip() for line in address_text.strip().split('\n') if line.strip()]
                    if len(lines) >= 4:
                        result['kunde'] = lines[1]  # Вторая строка - клиент
                        result['adresse'] = f"{lines[2]}, {lines[3]}"
                    elif len(lines) >= 2:
                        result['kunde'] = lines[1]
                        result['adresse'] = lines[2] if len(lines) > 2 else ''

                # ИСПРАВЛЕНИЕ: Парсим артикулы с улучшенным паттерном
                # Формат: <номер строки> <количество> Stk. <артикул> <описание>
                # Используем более гибкий паттерн, который работает с переносами страниц
                artikel_pattern = r'(\d+)\s+Stk\.\s+(\d{5})\s+(.+?)(?=\n\d+\s+Stk\.|\nSeite|\Z)'

                matches = list(re.finditer(artikel_pattern, full_text, re.MULTILINE | re.DOTALL))
                logger.debug(f"Found {len(matches)} artikel matches in PDF")

                for match in matches:
                    artikel = {
                        'nummer': match.group(2),      # Артикул (5 цифр)
                        'name': match.group(3).strip().replace('\n', ' '), # Описание (убираем переносы)
                        'menge': int(match.group(1))   # Количество
                    }
                    result['artikel'].append(artikel)
                    logger.debug(f"Parsed artikel: {artikel}")

            logger.info(f"Parsed Lieferschein {result.get('nummer', 'unknown')}: {len(result['artikel'])} artikel")
            return result

        except Exception as e:
            logger.error(f"Error parsing PDF {pdf_path}: {e}")
            raise


def test_parser():
    """Тестирование парсера"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python pdf_parser.py <path_to_pdf>")
        sys.exit(1)

    pdf_path = Path(sys.argv[1])
    if not pdf_path.exists():
        print(f"File not found: {pdf_path}")
        sys.exit(1)

    parser = LieferscheinPDFParser()
    result = parser.parse_lieferschein(pdf_path)

    print("\n=== Parsed Lieferschein ===")
    print(f"Lieferschein-Nr: {result['lieferschein_nummer']}")
    print(f"Datum: {result['datum']}")
    print(f"Kunde: {result['kunde']}")
    print(f"Adresse: {result['adresse']}")
    print(f"Kunden-Nr: {result['kunden_nr']}")
    print(f"\nArtikel ({len(result['artikel'])}):")
    for art in result['artikel']:
        print(f"  {art['pos']}. {art['anzahl']}x {art['artikelnr']} - {art['bezeichnung']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    test_parser()
