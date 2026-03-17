# Project Modules

---


* Landing Page - Add content about Makkal Nala Pani, Countdown for Event 

1. Master Data Entry 
   - **District** Beneficiaries:
        - Select District name, list of articles and its quantity, comments. 
        - Prices are autofilled from a Articles list. Articles with 
            0(unknown or Fluctuating) prices are manually entered.
        - Multiples entries are allowed in case of Aid or Project and advised to add comments to uniquely identify.
   - **Public** Beneficiaries
     - Beneficiaries have only one Article or Aid
     - Each Beneficiary is verified with their past records and present based on Aadhar Number. But can be considered in some cases.
     - No budget alloted. but we check the total 
   - **Institution & Other** Beneficiaries
     - Institutions handle multiple articles and aids. No verification needed
     - No Budget alloted, but we calculate only the total accrued.
2. Article Management
   - Manage list of articles , its high level and Medium level category, price, etc
3. Order Management - (Requirement overview)
    - Sum of its Requirement based on Beneficiaries and ordered status
4. Ordering and Fundraising
   - We need two tightly linked features built on a single item master so there is no duplication or mismatch: first, 
   an Order Overview menu that acts as a live dashboard showing every required item with total needed, ordered, pending 
   and funded quantities, where clicking an item reveals beneficiary types and counts, and where status indicators are 
   colour coded green if fully ordered and funded, red if not ordered or not funded, and amber if partial or excess; 
   second, an Order and Fundraising management menu where orders are created via a vendor-facing form capturing vendor 
   details, quoted article names, quantities, prices and tax, with each vendor article mandatorily mapped to an internal 
   item to generate and store a purchase order PDF, and where fundraising reuses the same order data without re-entry,
   adds Aid and Project Type which must be linked exactly to specific records and Article Type which can be linked generally, 
   and generates a separate fundraising PDF, with both order and fundraising outputs automatically updating the Order 
   Overview status based on computed required, ordered and funded values from Supabase-backed relational tables.

5. Waiting Hall Quantity vs Stage Quantity
      - After communicating with the Beneficiaries these values are decided
      - How many do they collect at Waiting Hall in Bulk vs How many they collect at the Stage
      - Tokens are alloted only for Stage Quantity and Acknowledgment Receipt is provided for Hall quantity
      - Chairs are alloted based on this Stage Quantity
6. Sequence List
    - Sequence order for Stage distribution. Major and Lite article are first moved and the heavy are kept in place for last.
    - numbers range from 1 to N.
    - Article list and sequence number colums are merged with the finalised Master data
    - display a  table that is editable with filters to add seq number
7. Token generation
    - based on the Finalised master data and the Sequence and within sequence in the order of  District, Public, instn.
    - Add a upload csv option , that will provide options to downlaod tokens by District level(beneficiary token) and article level(stick on article)
    - Chair Label, VIP label, 2L labels, etc 
    - Generate Declaration form for Public beneficiaries
8. Reports
    - From the Master record , we use it as final to create reports. 
      - Article wise District
      - District wise articles
      - Consolidated report for diaz and VIPs
      - other reports
9. Dashboards 
    - Summary of modules ( Inventory, Master data, Data collection completed or not status, etc)
10. User Management 
11. Audit Logs
12. Detailed documentation of the Project Workings, Credentials, for KT



# Data Available/Required

---
1. Master Record - From Data Entry
2. Article List
3. District Beneficiary info
4. Sequence list
5. Past Public & District beneficiary
6. Waiting Hall QTY vs Stage Quantity list
7. Order Requirements
