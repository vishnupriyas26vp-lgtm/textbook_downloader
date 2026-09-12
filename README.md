# Tamil Nadu School Textbooks Auto-Downloader
## STRICT REQUIREMENT: TAMIL MEDIUM ONLY

This application is purpose-built specifically for downloading **Tamil Medium School Textbooks Only** (Classes: 8, 9, 10, 11, and 12; Terms 1, 2, and 3).

English Medium textbooks, other-medium textbooks, and unrelated files are **strictly excluded** at every level of scraping, filtering, and downloading.

---

### Core Security & Medium Constraints

1. **Zero-Tolerance English Rejection**:
   - The application inspects the live website DOM hierarchy.
   - Any resource discovered under an English Medium heading, table, or column is rejected immediately.
   - English URL markers (`_EM_`, `_EM.pdf`, `English_Medium`) trigger instant rejection.
2. **Dedicated Medium Validator (`is_tamil_medium`)**:
   - Every candidate resource must be affirmatively confirmed as Tamil Medium before entering the download queue.
   - Checks for verified Tamil Medium labels: `Tamil Medium`, `TAMIL MEDIUM`, `தமிழ் வழி`, `தமிழ் வழிக்கல்வி`, `தமிழ்`, and URL markers (`_TM_`, `_TM.pdf`).
3. **Ambiguous Resource Safety Protocol**:
   - If the system cannot determine the medium with 100% certainty, it **never** downloads the file automatically.
   - It is marked as `AMBIGUOUS_MEDIUM` and logged:
     ```
     [TAMIL MEDIUM CHECK]
     Unable to confidently determine medium.
     Resource skipped for safety.
     ```
   - Ambiguous resources are isolated in a dedicated review panel.
4. **Final 6-Point Pre-Save Validation**:
   Before committing any downloaded file to disk, the system performs a 6-point verification:
   1. Correct class?
   2. Correct edition?
   3. Confirmed Tamil Medium?
   4. Correct term?
   5. Correct subject?
   6. Valid PDF header (`%PDF-` magic bytes check)?
5. **Formatted Download Logs**:
   Every download activity is logged with full structured metadata:
   ```
   [INFO]
   Class: 8
   Medium: Tamil
   Term: 1
   Subject: Mathematics
   Book: 8th Standard Mathematics
   Status: Downloading
   ```

---

### Matching Hierarchy

```
CLASS (8, 9, 10, 11, 12)
  └── CURRENT / REQUIRED EDITION (e.g. 2024-25, 2019 Term-wise)
        └── TAMIL MEDIUM (Verified Context)
              └── TERM (Term 1, Term 2, Term 3, or Full Book)
                    └── SUBJECT (e.g. கணிதம் / Mathematics)
                          └── PDF (Magic bytes %PDF- verified)
```

---

### How to Run

#### 1. Launch Desktop GUI (Default)
```bash
python main.py
```
The GUI displays:
- Clear header badge: `MEDIUM: ● TAMIL MEDIUM ONLY`
- Notice: *"Only Tamil Medium textbooks will be downloaded."*
- English Medium is not an active option.
- Class multi-select checkboxes (Classes 8–12, Select All, Clear).
- Term and Edition filters.
- Real-time download log viewer and Ambiguous Resources review tab.

#### 2. Run via Command Line Interface (CLI)
```bash
# Scan only without downloading (e.g. Class 8 Term 1)
python main.py --cli --classes 8 --term "Term 1" --scan-only

# Download specific class and term
python main.py --cli --classes 8 --term "Term 1" --dest ./downloads -y

# Download specific subject (e.g. Mathematics)
python main.py --cli --classes 8 --subject "Mathematics" -y

# Download all classes (8, 9, 10, 11, 12)
python main.py --cli --classes all -y
```

---

### Running Tests
To run the full automated unit and integration test suite:
```bash
python -m unittest tests/test_tamil_downloader.py
```
