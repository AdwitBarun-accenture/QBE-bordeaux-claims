"""Recreates the mockup's sample bordereaux as real files for testing:
  Markel_Premium_Apr26.csv     - premium, the mockup's 10 premium rows
  TMHCC_Claims_Apr26.csv       - claims, the mockup's 6 claims rows
  CNA_Premium_Apr26.xlsx       - same premium rows in Excel with a title row + 2 sheets
  Beazley_Claims_Apr26_pw.xlsx - password-protected Excel (password: beazley2026)
Run: python sample_data/make_samples.py
"""
import csv
import io
from pathlib import Path

HERE = Path(__file__).parent
PREMIUM_HEADERS = ['Insured', 'UMR', 'Our Ref', 'On Risk Date', 'Off Risk Date', 'Gross Prem', 'Net Prem Written', 'Ccy',
                   'Sum Ins', 'Class', 'EML', 'Location', 'Cntry', 'Broker', 'Bkr Code', 'Our Line %', 'Exp Ratio', 'Comm %', 'Notes']
PREMIUM_ROWS = [
    ['Apex Manufacturing Ltd', 'B0621XLS008832', 'POL-2026-001', '01/04/2026', '31/03/2027', '45200', '6780', 'GBP', '2500000', 'PROP', '35', '142 Industrial Way, Birmingham B12 0QX', 'GB', 'Marsh Ltd', 'MARS', '15', '28', '12.5', 'Endt 15/02/26 sprklr system installed prem adj -1200. See also POL-2026-001A. 30d cancel clause.'],
    ['Greenfield Logistics plc', 'B0621XLS008833', 'POL-2026-002', '04/15/2026', '04/14/2027', '28750', '5750', 'GBP', '1800000', 'PROP', '40', 'Unit 7 Trafford Park Manchester M17 1TZ', 'GB', 'MARSH LTD', 'MARS', '20', '25', '15', 'Renewal flat. Prev yr claim free disc applied. Subsidence excl endorsed.'],
    ['Pacific Rim Exports', 'B0621XLS008834', 'POL-2026-003', '01/03/2026', '28/02/2027', '62400', '45600', 'Sterling', '', 'MAR', '', 'Port of Felixstowe IP11 3SY', 'GB', 'Willis Towers Watson', 'WTWS', '10', '30', '12', 'Open cover cargo. War risk per addendum 3 dt 10 Jan 26. SI not declared - manifested value basis. USD equiv approx 480k.'],
    ['Northern Steel Works', 'B0621XLS008835', 'POL-2026-004', '20/04/2026', '19/04/2027', '89100', '22275', 'GBP', '5000000', 'Property', '', 'Middlesbrough Rd TS6 9BG', 'GB', 'Lockton', 'LOCK', '25', '22', '11', 'DA limit 2.5m - note cumulative line now 2.31m. Prior yr dev +45k reserve mvmt. Mach bkdwn sub-limit 500k.'],
    ['Sunrise Hotels Group', 'B0621XLS008836', 'POL-2026-005', '01/05/2026', '30/04/2027', '112000', '13440', 'GBP', '8500000', 'PROP', '30', 'Canary Wharf London E14 5AB', 'GB', 'Gallagher', 'GALG', '12', '27', '22', 'Endt 2 BI coverage added 01/05/26 prem uplift 8400 incl in above. Terrorism excl. PML cert attached separately.'],
    ['Eurofreight Carriers GmbH', '', 'POL-2026-006', '04/10/2026', '04/09/2027', '34500', '6210', 'EUR', '950000', 'Liability', '', 'Hanger Lane London W5 / Hamburg DE', 'DE', 'marsh', '', '18', '32', '14', ''],
    ['Highland Power Co Ltd', 'B0621XLS008838', 'POL-2026-007', '01/04/2026', '31/03/2027', '198000', '59400', 'GBP', '', 'ENGY', '45', 'Fort William PH33 7PT', 'GB', 'Aon UK Ltd', 'AONL', '30', '20', '10', 'Mach bkdwn ext. Ded 100k AOO. Ref also CLM-2025-0318 prior yr turbine loss still open. TRIA applies.'],
    ['Apex Manufacturing Ltd', 'B0621XLS008832', 'POL-2026-001', '01/04/2026', '31/03/2027', '46400', '6960', 'GBP', '2500000', 'PROP', '35', '142 Industrial Way Birmingham B12 0QX', 'GB', 'Marsh Ltd', 'MARS', '15', '28', '12.5', 'AMENDED - prem corrected from 45200, sprklr disc recalculated. Supersedes prev submission.'],
    ['City Towers Ltd', 'B0621XLS008839', 'POL-2026-008', '2026', '2027', '55000', '12100', 'GBP', '3200000', 'PROP', '20', '123 High St Leeds LS1 4DL', 'GB', 'JLT Group', 'JLTG', '22', '26', '12', 'Annual renewal. JLT ref JLT/2026/CTL/004. No changes to risk.'],
    ['Northern Steel Works', 'B0621XLS008835', 'CLM-2026-0442', '03/02/2026', '', '450000', '', 'GBP', '', 'CLAIM', '', 'Middlesbrough', 'GB', 'Lockton', 'LOCK', '', '', '', 'Flood loss - reserve 450000. Paid 225000. BI declared. Subrog potential vs drainage authority. Handler K Patel.'],
]
CLAIMS_HEADERS = ['Insured Name', 'Policy No', 'Claim Ref', 'Loss Date', 'Notified', 'Cause of Loss', 'Gross Reserve', 'Ccy', 'Paid',
                  'O/S Reserve', 'Total Incurred', 'Status', 'Handler', 'Type of Loss']
CLAIMS_ROWS = [
    ['Apex Manufacturing Ltd', 'POL-2026-001', 'CLM-2026-0441', '12/01/2026', '15/01/2026', 'Fire damage to warehouse roof and storage area. Sprinklers activated. Structural assessment underway. Temp roof covering in place.', '180000', 'GBP', '0', '180000', '180000', 'Open', 'J. Smith', 'Material Damage'],
    ['Northern Steel Works', 'POL-2026-004', 'CLM-2026-0442', '03/02/2026', '05/02/2026', 'Flood damage heavy machinery production hall. BI declared from 03/02. Subrogation potential drainage authority - legal instructed. Est BI period 4 months.', '450000', 'GBP', '225000', '225000', '430000', 'Part Paid', 'K. Patel', 'Machinery Breakdown'],
    ['Sunrise Hotels Group', 'POL-2026-005', 'CLM-2026-0443', '', '20/03/2026', 'Liability - guest slip and fall reception area. Settlement agreed without admission. See file note re: CCTV evidence.', '75000', 'GBP', '75000', '0', '75000', 'Settled', 'J. Smith', 'Public Liability'],
    ['Pacific Rim Exports', 'POL-2026-003', 'CLM-2026-0444', '05/03/2026', '01/03/2026', 'Container overboard during storm Bay of Biscay. Manifested cargo 320000 USD. Carrier liability disputed - General Average declared. GBP equiv at loss date approx 253k.', '320000', 'USD', '0', '320000', '320000', 'Open', 'M. Wong', 'Marine Cargo'],
    ['Apex Manufacturing Ltd', 'POL-2026-001', 'CLM-2026-0441', '12/01/2026', '15/01/2026', 'REVISED RESERVE - structural survey complete. See survey rpt APX/2026/03. Original reserve insufficient.', '265000', 'GBP', '0', '265000', '265000', 'Open', 'J. Smith', 'Material Damage'],
    ['Highland Power Co Ltd', 'POL-2026-007', 'CLM-2025-0318', '14/11/2025', '18/11/2025', 'Turbine blade failure unit 3. Prior year loss still developing. Additional reserve recommended by loss adjuster Clarke & Pratt ref CP/2025/HPL/7. TRIA notification filed.', '890000', 'GBP', '340000', '550000', '890000', 'Open', 'h.okonkwo@highland-power.co.uk', 'Machinery Breakdown'],
]


def write_csv(path, headers, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)


def make_xlsx(headers, rows, title=None, extra_sheet=True) -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    if extra_sheet:
        ws0 = wb.active
        ws0.title = "Cover"
        ws0["A1"] = "Bordereaux submission - see 'Premium' tab"
        ws = wb.create_sheet("Premium")
    else:
        ws = wb.active
        ws.title = "Data"
    if title:
        ws.append([title])
        ws.append([])
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def main():
    write_csv(HERE / "Markel_Premium_Apr26.csv", PREMIUM_HEADERS, PREMIUM_ROWS)
    write_csv(HERE / "TMHCC_Claims_Apr26.csv", CLAIMS_HEADERS, CLAIMS_ROWS)
    (HERE / "CNA_Premium_Apr26.xlsx").write_bytes(make_xlsx(PREMIUM_HEADERS, PREMIUM_ROWS, "CNA Hardy - Premium Bordereaux April 2026"))
    plain = make_xlsx(CLAIMS_HEADERS, CLAIMS_ROWS, extra_sheet=False)
    try:
        import msoffcrypto
        from msoffcrypto.format.ooxml import OOXMLFile
        out = io.BytesIO()
        OOXMLFile(io.BytesIO(plain)).encrypt("beazley2026", out)
        (HERE / "Beazley_Claims_Apr26_pw.xlsx").write_bytes(out.getvalue())
    except Exception as e:
        print(f"skipped encrypted sample: {e}")
    print("samples written to", HERE)


if __name__ == "__main__":
    main()
