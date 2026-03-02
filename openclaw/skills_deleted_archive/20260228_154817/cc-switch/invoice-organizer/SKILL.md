---
name: "invoice-organizer"
description: "invoice-organizer 技能"
version: "1.0.0"
triggers:
  keywords:
    - "发票"
    - "票据整理"
    - "财务文件"
    - "invoice"
    - "收据"
    - "财务整理"
  auto_trigger: true
  confidence_threshold: 0.7
---

name: invoice-organizer
description: Automatically organizes invoices and receipts for tax preparation by reading messy files, extracting key information, renaming them consistently, and sorting them into logical folders. Turns hours of manual bookkeeping into minutes of automated organization.