"""양형위 41개+ 범죄별 PDF 일괄 다운로드.

URL 패턴: https://sc.scourt.go.kr/sc/krsc/pdf/F{N}.Crimes_of_{name}.pdf
"""
import urllib.request
from pathlib import Path
import time

PROJECT_ROOT = Path(__file__).parent.parent
PDF_DIR = PROJECT_ROOT / "data" / "sentencing_pdfs"
PDF_DIR.mkdir(parents=True, exist_ok=True)

PDFS = [
    "F1.Crimes_of_Homicide.pdf",
    "F2.Crimes_of_Bribery.pdf",
    "F3.Crimes_of_Sexual_Assault.pdf",
    "F4.Crimes_of_Robbery.pdf",
    "F5.Crimes_of_Embezzlement_and_Breach_of_Trust.pdf",
    "F6.Crimes_of_Perjury_and_Destroy_of_evidence.pdf",
    "F7.Crimes_of_False_Accusation.pdf",
    "F8.Crimes_of_Capture_and_HumanTrafficking.pdf",
    "F9.Crimes_of_Fraud.pdf",
    "F10.Crimes_of_Larceny.pdf",
    "F11.Crimes_of_Official_Documents.pdf",
    "F12.Crimes_of_Private_Documents.pdf",
    "F13.Crimes_of_Execution_Disturbance.pdf",
    "F14.Crimes_of_Food_and_Health.pdf",
    "F15.Crimes_of_Narcotics.pdf",
    "F16.Crimes_of_Stock.pdf",
    "F17.Crimes_of_Intellectual_Property.pdf",
    "F18.Crimes_of_Violence.pdf",
    "F19.Crimes_of_Traffic.pdf",
    "F20.Crimes_of_Election.pdf",
    "F21.Crimes_of_Tax.pdf",
    "F22.Crimes_of_Blackmail.pdf",
    "F23.Crimes_of_Arson.pdf",
    "F24.Crimes_of_Malpractice.pdf",
    "F25.Crimes_of_Lawyer.pdf",
    "F26.Crimes_of_Prostitution.pdf",
    "F27.Crimes_of_Arrest_and_Confinement.pdf",
    "F28.Crimes_of_Stolen_goods.pdf",
    "F29.Crimes_of_Right_and_Interference.pdf",
    "F30.Crimes_of_Business_Obstruction.pdf",
    "F31.Crimes_of_Destruction.pdf",
    "F32.Crimes_of_Speculative_Game.pdf",
    "F33.Crimes_of_Labor_Standard.pdf",
    "F34.Crimes_of_Petroleum_Business.pdf",
    "F35.Crimes_of_Accidental_Homicide.pdf",
    "F36.Crimes_of_Escape_Concealment.pdf",
    "F37.Crimes_of_Illegal_Check_Control.pdf",
    "F38.Crimes_of_Loan_ClaimCollection.pdf",
    "F39.Crimes_of_Defamation.pdf",
    "F40.Crimes_of_Similar_Reception.pdf",
    "F41.Crimes_of_Electronic_Finance.pdf",
    "F42.Crimes_of_Digital__Sexual.pdf",
    "F50.Crimes_of_House__Breaking.pdf",
    "F51.Crimes_of__Environment.pdf",
    "F52.Crimes_of_Tariff.pdf",
    "F53.Crimes_of_Information_Network.pdf",
    "F54.Crimes_of_Stalking.pdf",
    "F55.Crimes_of_Animal_Protection.pdf",
]

# 양형기준 해설 + 종합본
EXTRA = [
    "sc_explan_doc.pdf",
    "2025_sentencing_guidelines.pdf",
]

BASE = "https://sc.scourt.go.kr/sc/krsc/pdf"

ok, fail = 0, 0
for fn in PDFS + EXTRA:
    out = PDF_DIR / fn
    if out.exists() and out.stat().st_size > 1000:
        ok += 1
        continue
    url = f"{BASE}/{fn}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        out.write_bytes(data)
        print(f"  ✅ {fn}: {len(data):,} bytes")
        ok += 1
        time.sleep(0.3)
    except Exception as e:
        print(f"  ❌ {fn}: {e}")
        fail += 1

print(f"\n총 {ok}개 다운로드 / {fail}개 실패")
print(f"저장 위치: {PDF_DIR}")
total_size = sum(p.stat().st_size for p in PDF_DIR.glob("*.pdf"))
print(f"총 용량: {total_size / 1024 / 1024:.1f} MB")
