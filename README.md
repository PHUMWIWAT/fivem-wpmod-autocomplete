# fivem-wpmod-autocomplete

สร้าง resource อาวุธ addon สำหรับ FiveM จากแม่แบบใน `wp-templates` และโมเดลใน `wp-models` ได้ไฟล์ที่ใส่เซิร์ฟเวอร์แล้ว `ensure` ได้เลย

ต้องมี Python 3 และคำสั่ง `py` บน Windows

## โฟลเดอร์

- `wp-templates/WEAPON_*` — แม่แบบ meta ของอาวุธแต่ละชนิด
- `wp-models/<ชื่อโมเดล>/` — ไฟล์สตรีม ต้องมี `<ชื่อโมเดล>.ydr` (และ `.ytd` ถ้ามี)
- `output/` — ผลที่สร้าง โฟลเดอร์นี้ไม่ถูกเก็บใน git

## วิธีใช้

เปิดเมนู:

```bat
auto-complete.cmd
```

แยกหนึ่งอาวุธต่อหนึ่ง resource:

```bat
auto-complete.cmd separate WEAPON_BAT WEAPON_BASEBALL_DX weapon_baseball_dx
```

รวมหลายอาวุธใน resource เดียว หลังชื่อ resource เป็นชุดละ 3 ค่า: template, ชื่อในเกม, ชื่อโมเดล

```bat
auto-complete.cmd pack weapons_pack WEAPON_BAT WEAPON_BASEBALL_DX weapon_baseball_dx WEAPON_POOLCUE WEAPON_POOL_DX weapon_pool_dx
```

ชื่อในเกมใช้ `A-Z`, `0-9` และ `_` ถ้ายิงในเกมด้วยชื่อนี้ เช่น `WEAPON_BASEBALL_DX` ช่องอาวุธจะเป็น `SLOT_` ตามด้วยชื่อนั้น เพื่อไม่ไปทับอาวุธ vanilla เลขเรียง weapon wheel เริ่มที่ `10000` และตัวถัดไปเก็บใน `output/.next-order`

ข้อความบน weapon wheel ยังเป็นชื่อของอาวุธต้นแบบ เช่น `WT_BAT` ชื่อที่เปลี่ยนคือชื่อที่ใช้ spawn

โหมด pack รวม meta เป็นไฟล์ละชุดใน resource เดียว ท่าในก้อน `Default` จึงไม่ทับกัน

## ไลเซนส์

แม่แบบอาวุธใน `wp-templates` มาจาก [FiveM-AddonWeaponTemplates](https://github.com/CENSOR37/FiveM-AddonWeaponTemplates) ของ CENSOR_1337 และยังอยู่ภายใต้ MIT License ตาม [`wp-templates/CREDITS.md`](wp-templates/CREDITS.md)
