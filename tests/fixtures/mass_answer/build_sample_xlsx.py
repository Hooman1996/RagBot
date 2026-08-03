"""Rebuild the committed synthetic XLSX fixture."""

from pathlib import Path

from openpyxl import Workbook


destination = Path(__file__).with_name("sample_persian.xlsx")
workbook = Workbook()
sheet = workbook.active
sheet.title = "questions"
sheet.append(["question", "category", "note"])
sheet.append([
    "چگونه کارت بانکی جدید درخواست کنم؟",
    "کارت",
    "نمونهٔ مصنوعی، بدون دادهٔ مشتری",
])
sheet.append([
    "شرایط دریافت تسهیلات چیست؟",
    "تسهیلات",
    "متن فارسی Unicode",
])
workbook.save(destination)
