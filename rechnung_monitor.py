#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import time
import shutil
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
import re

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    import pikepdf
    from lxml import etree
except ImportError:
    pikepdf = None
    etree = None

logger = logging.getLogger(__name__)

class RechnungMonitor:
    def __init__(self, watch_folder: Path, output_folder: Path, ftp_config=None, db=None, sessions=None):
        self.watch_folder = watch_folder
        self.output_folder = output_folder
        self.ftp_config = ftp_config
        self.db = db
        self.sessions = sessions
        
        self.watch_folder.mkdir(parents=True, exist_ok=True)
        self.output_folder.mkdir(parents=True, exist_ok=True)
        
        self.processed_files = set()
        self._scan_count = 0

    def start(self):
        """Запуск мониторинга (инициализация)"""
        logger.info(f"Rechnung monitor started on {self.watch_folder}")

    def scan(self):
        """Сканирование папки на новые файлы"""
        self._scan_count += 1
        results = []
        try:
            # SMB directory cache workaround: force Windows to re-read network directory
            # Without this, glob() may return stale cached results on network drives
            try:
                os.listdir(str(self.watch_folder))
            except OSError as e:
                logger.warning(f"Rechnung watch folder not accessible: {e}")
                return results

            pdf_files = list(self.watch_folder.glob("*.pdf"))

            # Heartbeat logging every 20 scans (~5 min at 15s interval)
            if self._scan_count % 20 == 0:
                logger.info(f"Rechnung monitor heartbeat: scan #{self._scan_count}, "
                           f"folder={self.watch_folder}, "
                           f"pdf_files={len(pdf_files)}, "
                           f"processed={len(self.processed_files)}")

            for file_path in pdf_files:
                if file_path.name in self.processed_files:
                    continue

                # Проверяем что файл полностью записан (размер стабилен)
                try:
                    size1 = file_path.stat().st_size
                    time.sleep(0.5)
                    size2 = file_path.stat().st_size
                    if size1 != size2 or size1 == 0:
                        logger.debug(f"File still being written: {file_path.name}")
                        continue  # Пропускаем, подберём на следующем цикле
                except OSError:
                    continue

                logger.info(f"New Rechnung detected: {file_path.name}")
                result = self.process_file(file_path)
                if result:
                    results.append(result)

            if pdf_files and not results and self._scan_count % 20 == 0:
                unprocessed = [f.name for f in pdf_files if f.name not in self.processed_files]
                if unprocessed:
                    logger.info(f"Rechnung unprocessed files in folder: {unprocessed[:5]}")

        except Exception as e:
            logger.error(f"Error scanning rechnung folder: {e}")

        return results

    def process_file(self, file_path: Path):
        """
        Обработка счета (Rechnung):
        1. Извлекает данные из текста и XML
        2. Находит Lieferschein в тексте
        3. Добавляет Lieferschein в XML
        4. Сохраняет PDF с обновленным XML
        5. Ищет соответствующий заказ в БД (умный поиск)
        6. Обновляет статус invoice в заказе
        """
        try:
            logger.info(f"Processing invoice: {file_path.name}")

            # 1. Извлекаем данные из текста PDF
            data = self.extract_data(file_path)

            if not data:
                logger.warning(f"Could not extract data from {file_path.name}")
                return None

            rechnung_nr = data.get('rechnung_nr', 'unknown')
            lieferschein_nr = data.get('lieferschein_nr')
            kunden_nr = data.get('kunden_nr')
            invoice_date = data.get('datum')
            invoice_items = data.get('items', [])

            # 2. Извлекаем встроенный XML из PDF
            xml_content, xml_name = self.extract_xml_from_pdf(file_path)

            if xml_content:
                logger.info(f"XML found in PDF: {xml_name}")

                # Извлекаем данные из XML (приоритет над текстом)
                xml_data = self.extract_data_from_xml(xml_content)

                # Дополняем данные из XML (если не нашли в тексте)
                if rechnung_nr == 'unknown':
                    xml_rechnung = self.get_rechnung_number_from_xml(xml_content)
                    if xml_rechnung:
                        rechnung_nr = xml_rechnung
                        logger.info(f"Rechnung number from XML: {rechnung_nr}")

                # Используем данные из XML как приоритетные
                if xml_data.get('kunde') and not data.get('kunde'):
                    data['kunde'] = xml_data['kunde']
                    logger.info(f"Customer name from XML: {data['kunde']}")

                if xml_data.get('kunden_nr') and not kunden_nr:
                    kunden_nr = xml_data['kunden_nr']
                    data['kunden_nr'] = kunden_nr
                    logger.info(f"Customer number from XML: {kunden_nr}")

                if xml_data.get('datum') and not invoice_date:
                    invoice_date = xml_data['datum']
                    data['datum'] = invoice_date
                    logger.info(f"Invoice date from XML: {invoice_date}")

                if xml_data.get('items') and len(xml_data['items']) > len(invoice_items):
                    invoice_items = xml_data['items']
                    data['items'] = invoice_items
                    logger.info(f"Items from XML: {len(invoice_items)} items")

                # Обновляем переменные после дополнения из XML
                kunden_nr = data.get('kunden_nr')
                invoice_date = data.get('datum')
                invoice_items = data.get('items', [])

                # 3. Добавляем Lieferschein в XML (если нашли)
                if lieferschein_nr:
                    logger.info(f"Adding Lieferschein {lieferschein_nr} to XML")
                    modified_xml = self.add_lieferschein_to_xml(xml_content, lieferschein_nr)
                else:
                    logger.warning("Lieferschein not found, XML will not be modified")
                    modified_xml = xml_content

                # 4. Создаём новый файл с обновленным XML
                final_name = f"{rechnung_nr}_{lieferschein_nr}.pdf" if lieferschein_nr else f"{rechnung_nr}.pdf"
                target_path = self.output_folder / final_name

                # Сохраняем PDF с модифицированным XML
                if self.update_pdf_with_xml(file_path, modified_xml, target_path):
                    logger.info(f"PDF saved with updated XML: {final_name}")

                    # Сохраняем XML отдельно (для проверки)
                    xml_path = self.output_folder / f"{rechnung_nr}_{lieferschein_nr}.xml" if lieferschein_nr else self.output_folder / f"{rechnung_nr}.xml"
                    xml_path.write_text(modified_xml, encoding='utf-8')
                    logger.info(f"XML saved separately: {xml_path.name}")
                else:
                    logger.error("Failed to update PDF with XML")
                    # Fallback: просто копируем файл
                    shutil.copy2(file_path, target_path)

            else:
                # Нет XML - просто перемещаем файл
                logger.warning("No embedded XML found, moving file as-is")
                final_name = f"{rechnung_nr}_{lieferschein_nr}.pdf" if lieferschein_nr else f"{rechnung_nr}.pdf"
                target_path = self.output_folder / final_name
                shutil.copy2(file_path, target_path)

            # 5. УМНЫЙ ПОИСК ЗАКАЗА В БД
            matched_order_ids = []
            kunde_name = data.get('kunde', '')

            if kunden_nr and invoice_date and invoice_items:
                logger.info(f"Searching for matching orders: client={kunden_nr} ({kunde_name}), date={invoice_date}, items={len(invoice_items)}")

                # Если есть Lieferschein - ищем один заказ
                # Если нет Lieferschein - ищем ВСЕ подходящие заказы (товар идёт на склад)
                if lieferschein_nr:
                    matched = self.find_matching_order(kunden_nr, kunde_name, invoice_date, invoice_items, match_threshold=0.8)
                    if matched:
                        matched_order_ids = [matched]
                else:
                    # Без Lieferschein - ищем ВСЕ заказы для этого клиента/даты
                    matched_order_ids = self.find_all_matching_orders(kunden_nr, kunde_name, invoice_date, invoice_items, match_threshold=0.5)
                    logger.info(f"Found {len(matched_order_ids)} orders for invoice without Lieferschein")

                if matched_order_ids:
                    logger.info(f"✓ Invoice matched to orders: {matched_order_ids}")

                    # 6. Обновляем статус invoice во ВСЕХ найденных заказах
                    if self.db:
                        for matched_order_id in matched_order_ids:
                            try:
                                # Обновляем поле invoice_status
                                self.db.update_order(matched_order_id, {
                                    'invoice_status': f'✅ {rechnung_nr}',
                                    'invoice_file': final_name
                                })
                                logger.info(f"Order {matched_order_id} updated with invoice info")

                                # Broadcast отправляется из rechnung_monitor_loop в server_unified.py
                                # НЕ дублируем здесь — иначе двойные уведомления

                            except Exception as e:
                                logger.error(f"Failed to update order {matched_order_id}: {e}")

                        logger.info(f"Invoice DB updates done for {len(matched_order_ids)} orders")
                else:
                    logger.warning(f"No matching order found for invoice {rechnung_nr}")
            else:
                logger.warning("Insufficient data for order matching (missing client/date/items)")

            # 7. Удаляем исходный файл
            try:
                file_path.unlink()
                logger.info(f"Source file removed: {file_path.name}")
            except Exception as e:
                logger.warning(f"Could not remove source file: {e}")

            self.processed_files.add(file_path.name)

            data['success'] = True
            data['matched_orders'] = matched_order_ids  # Список всех найденных заказов
            data['matched_order'] = matched_order_ids[0] if matched_order_ids else None  # Для обратной совместимости
            data['output_file'] = final_name
            return data

        except Exception as e:
            logger.error(f"Error processing rechnung {file_path.name}: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def extract_data(self, pdf_path):
        """Извлечение данных из PDF (сначала пробуем XML, потом текст)"""
        data = {
            'rechnung_nr': None,
            'auftrag_nr': None,
            'lieferschein_nr': None,
            'kunde': None,
            'kunden_nr': None,
            'datum': None,
            'items': []
        }

        # ПОПЫТКА 1: Встроенный XML (ZUGFeRD / XRechnung) - Самый надежный
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for attachment in pdf.objects.get('embedded_files', []):
                    # Ищем XML файлы вложений
                    # Примечание: pdfplumber не всегда дает прямой доступ к байтам вложений
                    # Для простоты пропустим сложный разбор байтов, если это сложно
                    pass
        except: pass

        # ПОПЫТКА 2: Парсинг текста
        try:
            with pdfplumber.open(pdf_path) as pdf:
                text = ""
                for page in pdf.pages:
                    text += page.extract_text() + "\n"

                # DEBUG: Выводим первые 500 символов для отладки
                logger.debug(f"PDF text preview ({pdf_path.name}):\n{text[:500]}")

                # Парсинг регулярками

                # Номер счета (Rechnung Nr. 2003...)
                # Пробуем несколько вариантов:
                # 1. В тексте PDF
                m_rech = re.search(r'Rechnung\s+(?:Nr\.?|Nummer)?\s*:?\s*(\d+)', text, re.IGNORECASE)
                if m_rech:
                    data['rechnung_nr'] = m_rech.group(1)
                    logger.debug(f"Found Rechnung Nr in text: {data['rechnung_nr']}")

                # 2. Из имени файла как fallback
                if not data['rechnung_nr']:
                    m_filename = re.search(r'Rechnung\s+(?:Nr\.?)?\s*(\d+)', pdf_path.name, re.IGNORECASE)
                    if m_filename:
                        data['rechnung_nr'] = m_filename.group(1)
                        logger.debug(f"Found Rechnung Nr in filename: {data['rechnung_nr']}")
                    else:
                        logger.warning(f"Could not find 'Rechnung Nr' in text or filename")

                # Номер заказа (Auftrag Nr. 2003...)
                # Ищем "Auftrag" или "Bestellung"
                m_auftrag = re.search(r'(?:Auftrag|Bestellung)(?:s)?(?:-Nr\.?|Nr\.?)?\s*[:.]?\s*(\d+)', text, re.IGNORECASE)
                if m_auftrag:
                    data['auftrag_nr'] = m_auftrag.group(1)
                    logger.debug(f"Found Auftrag Nr: {data['auftrag_nr']}")

                # Номер клиента (Kunden-Nr)
                m_kunden = re.search(r'Kunden(?:-Nr\.?|Nr\.?)?\s*[:.]?\s*(\d+)', text, re.IGNORECASE)
                if m_kunden:
                    data['kunden_nr'] = m_kunden.group(1)
                    logger.debug(f"Found Kunden Nr: {data['kunden_nr']}")

                # Имя клиента - НЕ ИЗВЛЕКАЕМ ИЗ ТЕКСТА, ТОЛЬКО ИЗ XML
                # Текст PDF часто содержит неправильную структуру, лучше брать из XML
                # (Эта логика оставлена закомментированной для справки)
                # m_kunde_name = re.search(r'(?:Rechnung an|Kunde|Rechnungsadresse)[\s:]*\n*([^\n]{3,})', text, re.IGNORECASE)
                # if m_kunde_name:
                #     kunde_raw = m_kunde_name.group(1).strip()
                #     kunde_clean = kunde_raw.split('\n')[0].strip()
                #     kunde_clean = re.sub(r'^[\d\s\-\.]+', '', kunde_clean).strip()
                #     if kunde_clean:
                #         data['kunde'] = kunde_clean
                #         logger.debug(f"Found Kunde name: {data['kunde']}")

                # Lieferschein - ВАЖНО для добавления в XML!
                m_ls = re.search(r'(?:Lieferschein|Lief\.?)(?:-Nr\.?|Nr\.?)?\s*[:.]?\s*(\d+)', text, re.IGNORECASE)
                if m_ls:
                    data['lieferschein_nr'] = m_ls.group(1)
                    logger.debug(f"Found Lieferschein Nr: {data['lieferschein_nr']}")
                else:
                    logger.warning(f"Lieferschein number not found in PDF")

                # Дата
                m_date = re.search(r'(\d{2}\.\d{2}\.\d{4})', text)
                if m_date: data['datum'] = m_date.group(1)

                # Поиск товаров (Упрощенно: Ищем строки с Артикулами)
                # Пример строки: 1  05500  Napoleon Torte  10 Stk
                lines = text.split('\n')
                for line in lines:
                    # Ищем паттерн: Число (Поз) + Пробел + Артикул (0XXXX)
                    m_item = re.match(r'^\s*\d+\s+(\d{5})\s+(.+?)\s+(\d+(?:,\d+)?)\s*(?:Stk|kg)', line)
                    if m_item:
                        art_nr = m_item.group(1)
                        name = m_item.group(2).strip()
                        qty_str = m_item.group(3).replace(',', '.')
                        try: qty = float(qty_str)
                        except: qty = 0
                        
                        data['items'].append({
                            'art_nr': art_nr,
                            'name': name,
                            'qty': qty
                        })

        except Exception as e:
            logger.error(f"Text parsing error: {e}")

        # Если нашли хотя бы номер счета, считаем успехом
        if data['rechnung_nr']:
            return data
        return None

    def extract_xml_from_pdf(self, pdf_path):
        """Извлечение встроенного XML из PDF (ZUGFeRD/XRechnung)"""
        if not pikepdf:
            logger.warning("pikepdf not installed, cannot extract XML")
            return None, None

        try:
            with pikepdf.open(pdf_path) as pdf:
                if '/Names' in pdf.Root and '/EmbeddedFiles' in pdf.Root.Names:
                    names = pdf.Root.Names.EmbeddedFiles.Names
                    for i in range(0, len(names), 2):
                        if 'xml' in str(names[i]).lower():
                            xml_bytes = names[i + 1].EF.F.read_bytes()
                            xml_content = xml_bytes.decode('utf-8')
                            xml_name = str(names[i])
                            logger.info(f"XML extracted from PDF: {xml_name}")
                            return xml_content, xml_name
            logger.warning("No embedded XML found in PDF")
            return None, None
        except Exception as e:
            logger.error(f"Error extracting XML from PDF: {e}")
            return None, None

    def get_rechnung_number_from_xml(self, xml_content):
        """Извлечь номер счета из XML"""
        if not etree:
            return None

        try:
            root = etree.fromstring(xml_content.encode('utf-8'))
            ns = {
                'rsm': 'urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100',
                'ram': 'urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100'
            }
            invoice_id = root.find('./rsm:ExchangedDocument/ram:ID', ns)
            if invoice_id is not None:
                return invoice_id.text
            return None
        except Exception as e:
            logger.error(f"Error parsing XML for Rechnung number: {e}")
            return None

    def extract_data_from_xml(self, xml_content):
        """
        Извлечь полные данные из XML (ZUGFeRD/XRechnung):
        - Номер клиента
        - Имя клиента
        - Дату счета
        - Товары
        """
        if not etree:
            return {}

        try:
            root = etree.fromstring(xml_content.encode('utf-8'))
            ns = {
                'rsm': 'urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100',
                'ram': 'urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100',
                'udt': 'urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100'
            }

            data = {}

            # 1. Имя клиента (BuyerTradeParty)
            buyer_name = root.find('.//ram:BuyerTradeParty/ram:Name', ns)
            if buyer_name is not None:
                data['kunde'] = buyer_name.text
                logger.debug(f"XML: Found customer name: {data['kunde']}")

            # 2. Номер клиента (BuyerReference или из ID)
            buyer_ref = root.find('.//ram:BuyerReference', ns)
            if buyer_ref is not None:
                data['kunden_nr'] = buyer_ref.text
                logger.debug(f"XML: Found customer number: {data['kunden_nr']}")

            # 3. Дата счета
            issue_date = root.find('.//rsm:ExchangedDocument/ram:IssueDateTime/udt:DateTimeString', ns)
            if issue_date is not None:
                # Формат может быть YYYYMMDD или YYYY-MM-DD
                date_str = issue_date.text
                if len(date_str) == 8:  # YYYYMMDD
                    from datetime import datetime
                    data['datum'] = datetime.strptime(date_str, "%Y%m%d").strftime("%d.%m.%Y")
                else:
                    data['datum'] = date_str
                logger.debug(f"XML: Found date: {data['datum']}")

            # 4. Товары (LineItems)
            items = []
            line_items = root.findall('.//ram:IncludedSupplyChainTradeLineItem', ns)
            for idx, item in enumerate(line_items, 1):
                # Артикул
                art_nr_elem = item.find('.//ram:SpecifiedTradeProduct/ram:Name', ns)
                art_nr = art_nr_elem.text if art_nr_elem is not None else ''

                # Название
                name_elem = item.find('.//ram:SpecifiedTradeProduct/ram:Description', ns)
                name = name_elem.text if name_elem is not None else ''

                # Количество
                qty_elem = item.find('.//ram:SpecifiedLineTradeDelivery/ram:BilledQuantity', ns)
                qty = float(qty_elem.text) if qty_elem is not None else 0

                if art_nr and qty > 0:
                    items.append({
                        'art_nr': art_nr.strip(),
                        'name': name.strip(),
                        'qty': qty
                    })

            data['items'] = items
            logger.debug(f"XML: Found {len(items)} items")

            return data

        except Exception as e:
            logger.error(f"Error extracting data from XML: {e}", exc_info=True)
            return {}

    def add_lieferschein_to_xml(self, xml_content, lieferschein_nr):
        """Добавить номер Lieferschein в XML"""
        if not etree:
            logger.warning("lxml not installed, cannot modify XML")
            return xml_content

        try:
            parser = etree.XMLParser(remove_blank_text=True)
            root = etree.fromstring(xml_content.encode('utf-8'), parser)
            ns = {'ram': 'urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100'}

            trade_agreement = root.find('.//ram:ApplicableHeaderTradeAgreement', ns)
            if trade_agreement is not None:
                # Проверяем, нет ли уже DespatchAdviceReferencedDocument
                existing = trade_agreement.find('.//ram:DespatchAdviceReferencedDocument', ns)
                if existing is None:
                    # Создаём новый элемент
                    despatch_advice = etree.Element(f"{{{ns['ram']}}}DespatchAdviceReferencedDocument")
                    etree.SubElement(despatch_advice, f"{{{ns['ram']}}}IssuerAssignedID").text = lieferschein_nr

                    # Вставляем после SellerOrderReferencedDocument (если есть)
                    seller_order = trade_agreement.find('.//ram:SellerOrderReferencedDocument', ns)
                    if seller_order is not None:
                        seller_order.addnext(despatch_advice)
                    else:
                        trade_agreement.insert(0, despatch_advice)

                    logger.info(f"Lieferschein {lieferschein_nr} added to XML")
                else:
                    logger.info("Lieferschein already exists in XML")

            return etree.tostring(root, encoding='UTF-8', xml_declaration=True, pretty_print=True).decode('utf-8')
        except Exception as e:
            logger.error(f"Error modifying XML: {e}")
            return xml_content

    def update_pdf_with_xml(self, pdf_path, new_xml_content, output_path):
        """Обновить PDF с модифицированным XML"""
        if not pikepdf:
            logger.warning("pikepdf not installed, cannot update PDF")
            return False

        try:
            with pikepdf.open(pdf_path) as pdf:
                if '/Names' in pdf.Root and '/EmbeddedFiles' in pdf.Root.Names:
                    names = pdf.Root.Names.EmbeddedFiles.Names
                    for i in range(0, len(names), 2):
                        if 'xml' in str(names[i]).lower():
                            # Заменяем содержимое XML
                            names[i+1].EF.F = pikepdf.Stream(pdf, new_xml_content.encode('utf-8'))
                            logger.info("XML updated in PDF")
                            break
                pdf.save(output_path)
            logger.info(f"PDF saved: {output_path}")
            return True
        except Exception as e:
            logger.error(f"Error updating PDF: {e}")
            return False

    def find_matching_order(self, kunden_nr, kunde_name_from_invoice, invoice_date, invoice_items, match_threshold=0.8):
        """
        Умный поиск заказа по:
        1. Берем Kunden-Nr из счета
        2. Ищем клиента в нашей БД (client_routes) по этому номеру
        3. Получаем ПОЛНОЕ имя клиента из НАШЕЙ базы
        4. Ищем заказы по номеру клиента И дате ±3 дня
        5. Сверяем товары (артикулы + количество)

        Args:
            kunden_nr: Номер клиента из счета (например 10640)
            kunde_name_from_invoice: Имя из счета (НЕ используется - может быть Monolith West, Ost, Süd и т.д.)
            invoice_date: Дата счета в формате DD.MM.YYYY или YYYY-MM-DD
            invoice_items: Список товаров из счета [{'art_nr': '...', 'qty': ...}, ...]
            match_threshold: Порог совпадения товаров (по умолчанию 0.8 = 80%)

        Returns:
            order_id или None
        """
        if not self.db:
            logger.warning("No database connection, cannot find matching order")
            return None

        try:
            from datetime import datetime, timedelta

            # Нормализуем номер клиента (убираем ведущие нули)
            kunden_nr_clean = str(kunden_nr).strip()
            kunden_nr_normalized = str(int(kunden_nr_clean)) if kunden_nr_clean.isdigit() else kunden_nr_clean

            # ВАЖНО: Получаем НАСТОЯЩЕЕ имя клиента из НАШЕЙ базы client_routes
            # (не из счета, т.к. там может быть Monolith West/Ost/Süd)
            with self.db.safe_connection() as conn:
                cursor = conn.cursor()

                # Ищем клиента в client_routes
                cursor.execute("""
                    SELECT client_id, client_name FROM client_routes
                    WHERE client_id = ? OR client_id = ?
                    LIMIT 1
                """, (kunden_nr_clean, kunden_nr_normalized))

                client_row = cursor.fetchone()

                if client_row:
                    client_name_from_db = client_row['client_name']
                    logger.info(f"Found client in DB: {kunden_nr} -> '{client_name_from_db}'")
                else:
                    # Если клиента нет в client_routes, используем номер для поиска заказов
                    client_name_from_db = None
                    logger.warning(f"Client {kunden_nr} not found in client_routes, will search orders by number only")

                # Парсим дату счета (может быть в разных форматах)
                try:
                    # Пробуем DD.MM.YYYY (формат из PDF)
                    invoice_dt = datetime.strptime(invoice_date, "%d.%m.%Y")
                except:
                    try:
                        # Пробуем YYYY-MM-DD
                        invoice_dt = datetime.strptime(invoice_date, "%Y-%m-%d")
                    except:
                        logger.warning(f"Invalid invoice date format: {invoice_date}")
                        return None

                # Диапазон поиска: ±3 дня от даты счета
                date_from = (invoice_dt - timedelta(days=3)).strftime("%Y-%m-%d")
                date_to = (invoice_dt + timedelta(days=3)).strftime("%Y-%m-%d")

                # Ищем заказы по НОМЕРУ клиента и ДАТЕ СОЗДАНИЯ
                # Дата хранится внутри JSON: order_data.date
                cursor.execute("""
                    SELECT order_id, order_data, json_extract(order_data, '$.date') as order_date FROM orders
                    WHERE (json_extract(order_data, '$.kunden_nr') = ?
                           OR json_extract(order_data, '$.kunden_nr') = ?)
                    AND json_extract(order_data, '$.date') BETWEEN ? AND ?
                    ORDER BY json_extract(order_data, '$.date') DESC
                """, (kunden_nr_clean, kunden_nr_normalized, date_from, date_to))

                candidates = cursor.fetchall()

            if not candidates:
                logger.info(f"No orders found for client {kunden_nr} ('{client_name_from_db}') in date range {date_from} to {date_to}")
                return None

            logger.info(f"Found {len(candidates)} candidate orders for client {kunden_nr} ('{client_name_from_db}')")

            # Сравниваем ТОЛЬКО товары (имя клиента НЕ учитываем!)
            best_match = None
            best_score = 0

            for order_id, order_data_str, order_date in candidates:
                import json
                order_data = json.loads(order_data_str)
                order_items = order_data.get('artikel', [])

                # Вычисляем совпадение товаров (артикулы + количество)
                items_score = self._calculate_items_match(invoice_items, order_items)

                logger.debug(f"Order {order_id} ({order_date}): items_match={items_score:.2%}")

                if items_score > best_score:
                    best_score = items_score
                    best_match = order_id

            # Проверяем порог (ТОЛЬКО товары, без имени!)
            if best_score >= match_threshold:
                logger.info(f"✓ Match found: Order {best_match} (items score: {best_score:.2%})")
                return best_match
            else:
                logger.warning(f"No order matches threshold {match_threshold:.0%}. Best: {best_match} ({best_score:.2%})")
                return None

        except Exception as e:
            logger.error(f"Error finding matching order: {e}", exc_info=True)
            return None

    def find_all_matching_orders(self, kunden_nr, kunde_name_from_invoice, invoice_date, invoice_items, match_threshold=0.5):
        """
        Поиск ВСЕХ заказов для счёта без Lieferschein.
        Используется когда товар идёт напрямую на склад (несколько заказов в одном счёте).

        Returns:
            list of order_ids
        """
        if not self.db:
            return []

        try:
            from datetime import datetime, timedelta

            kunden_nr_clean = str(kunden_nr).strip()
            kunden_nr_normalized = str(int(kunden_nr_clean)) if kunden_nr_clean.isdigit() else kunden_nr_clean

            with self.db.safe_connection() as conn:
                cursor = conn.cursor()

                # Парсим дату счета
                try:
                    invoice_dt = datetime.strptime(invoice_date, "%d.%m.%Y")
                except:
                    try:
                        invoice_dt = datetime.strptime(invoice_date, "%Y-%m-%d")
                    except:
                        return []

                # Диапазон поиска: ±3 дня от даты счета
                date_from = (invoice_dt - timedelta(days=3)).strftime("%Y-%m-%d")
                date_to = (invoice_dt + timedelta(days=3)).strftime("%Y-%m-%d")

                # Ищем ВСЕ заказы по номеру клиента и дате
                cursor.execute("""
                    SELECT order_id, order_data FROM orders
                    WHERE (json_extract(order_data, '$.kunden_nr') = ?
                           OR json_extract(order_data, '$.kunden_nr') = ?)
                    AND json_extract(order_data, '$.date') BETWEEN ? AND ?
                """, (kunden_nr_clean, kunden_nr_normalized, date_from, date_to))

                candidates = cursor.fetchall()

            if not candidates:
                logger.info(f"No orders found for client {kunden_nr} in date range {date_from} to {date_to}")
                return []

            # Возвращаем ВСЕ заказы с минимальным совпадением товаров
            matched_orders = []
            for order_id, order_data_str in candidates:
                import json
                order_data = json.loads(order_data_str)
                order_items = order_data.get('artikel', [])

                # Проверяем есть ли хоть какое-то совпадение товаров
                items_score = self._calculate_items_match(invoice_items, order_items)

                if items_score >= match_threshold:
                    matched_orders.append(order_id)
                    logger.debug(f"Order {order_id} matched with score {items_score:.2%}")

            logger.info(f"Found {len(matched_orders)} matching orders for invoice (threshold {match_threshold:.0%})")
            return matched_orders

        except Exception as e:
            logger.error(f"Error finding all matching orders: {e}", exc_info=True)
            return []

    def _calculate_items_match(self, invoice_items, order_items):
        """
        Вычислить процент совпадения товаров

        Логика:
        - Сравниваем артикулы и количества
        - Совпадение = артикул есть в обоих списках И количество близко (±10%)
        - Возвращаем: (совпавшие позиции) / (всего позиций в счете)
        """
        if not invoice_items or not order_items:
            return 0.0

        # Создаём словари для быстрого поиска
        order_map = {}
        for item in order_items:
            art_nr = str(item.get('artikel_nr', item.get('nummer', ''))).strip()
            qty = float(item.get('menge', 0))
            order_map[art_nr] = qty

        matched = 0
        for inv_item in invoice_items:
            art_nr = str(inv_item.get('art_nr', '')).strip()
            inv_qty = float(inv_item.get('qty', 0))

            if art_nr in order_map:
                order_qty = order_map[art_nr]
                # Проверяем, близко ли количество (±10%)
                if order_qty > 0:
                    diff_percent = abs(inv_qty - order_qty) / order_qty
                    if diff_percent <= 0.1:  # 10% допуск
                        matched += 1
                    else:
                        # Частичное совпадение - артикул есть, но кол-во другое
                        matched += 0.5
                else:
                    # Количество 0 в заказе - странно, но считаем половиной совпадения
                    matched += 0.5

        return matched / len(invoice_items)