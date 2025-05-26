import os
import ftplib
import re
from typing import List, Tuple
from fastapi import FastAPI
from dotenv import load_dotenv

load_dotenv()

FTP_HOST = os.getenv("FTP_HOST")
FTP_USER = os.getenv("FTP_USER")
FTP_PASS = os.getenv("FTP_PASS")
FTP_PORT = int(os.getenv("FTP_PORT", 21))
REMOTE_PATH = os.getenv("REMOTE_PATH", "/public_html/patterns/")

PATTERN_FILES = {
    "pattern_list1": "pattern1.txt",
    "pattern_list2": "pattern2.txt",
    "pattern_list3": "pattern3.txt"
}

LOCAL_SAVE_DIR = "ftp_patterns"
os.makedirs(LOCAL_SAVE_DIR, exist_ok=True)

app = FastAPI()
PATTERN_MODELS = {}

@app.on_event("startup")
def load_patterns():
    global PATTERN_MODELS
    PATTERN_MODELS = {}
    with ftplib.FTP() as ftp:
        ftp.connect(FTP_HOST, FTP_PORT)
        ftp.login(FTP_USER, FTP_PASS)
        ftp.cwd(REMOTE_PATH)
        for key, fname in PATTERN_FILES.items():
            local_path = os.path.join(LOCAL_SAVE_DIR, fname)
            with open(local_path, "wb") as f:
                ftp.retrbinary(f"RETR " + fname, f.write)
            with open(local_path, "r", encoding="utf-8") as f:
                PATTERN_MODELS[key] = f.read()

def classify_score(score: str) -> str:
    try:
        goals = list(map(int, score.split('-')))
        return 'O' if sum(goals) >= 3 else 'U'
    except:
        return 'X'

def get_score_sequence_label(seq):
    return ''.join(classify_score(score) for _, score in seq)

def parse_patterns(raw):
    blocks = re.split(r'\*{5,}', raw.strip())
    parsed = []
    for block in blocks:
        matches = re.findall(r'([A-Z]{2,3})\s+(\d+-\d+)', block)
        if len(matches) == 3:
            parsed.append(matches)
    return parsed

def find_pattern_matches(source, target):
    results = []
    for sequence in source:
        for i in range(len(sequence) - 2):
            window = sequence[i:i + 3]
            match_count = sum(1 for j in range(3) if window[j][0] == target[j])
            if match_count >= 2:
                results.append(window)
    return results

def extract_reference_predictions_after(raw):
    blocks = re.split(r'\*{5,}', raw.strip())
    parsed = []
    for block in blocks:
        matches = re.findall(r'([A-Z]{2,3})\s+(\d+-\d+)', block)
        if len(matches) == 3:
            parsed.append(matches)

    if len(parsed) < 2:
        return "", []

    last_ref = parsed[-1]
    last_label = get_score_sequence_label(last_ref)

    predictions = []
    for i in range(len(parsed) - 1):
        ref = parsed[i]
        next_seq = parsed[i + 1]
        if get_score_sequence_label(ref) == last_label:
            predictions.append((ref, next_seq))

    return last_label, predictions

def format_results(method_a, method_b, pattern_name, last_label):
    result = [f"--- Rezultate pentru {pattern_name.upper()} ---"]
    result.append("\n-- Metoda A: Potriviri directe --")
    if method_a:
        for match in method_a:
            result.append(" | ".join([f"{t} {s}" for t, s in match]))
    else:
        result.append("Nicio potrivire directă găsită.")

    result.append(f"\n-- Metoda B: Predictii imediat DUPĂ secvențe de tip {last_label} --")
    if method_b:
        for ref, pred in method_b:
            ref_line = " ".join([f"{t} {s}" for t, s in ref])
            pred_line = " ".join([f"Team{i+1} {s}" for i, (_, s) in enumerate(pred)])
            result.append(f"(secventa de referinta)  {ref_line}  => (secventa de predictie)  {pred_line}")
    else:
        result.append(f"Nicio secvență de referință de tip {last_label} găsită.")

    return "\n".join(result)

@app.get("/")
def root():
    return {"message": "API is up and running. Use /predict endpoint."}

@app.get("/predict")
def predict(p: str = "p1", t1: str = "spa", t2: str = "ita", t3: str = "por"):
    alias_map = {"p1": "pattern_list1", "p2": "pattern_list2", "p3": "pattern_list3"}
    patterns = [alias_map.get(p[i:i+2], "") for i in range(0, len(p), 2) if p[i:i+2] in alias_map]
    target_seq = {plist: [t1.upper(), t2.upper(), t3.upper()] for plist in patterns}

    out = []
    for plist in patterns:
        raw = PATTERN_MODELS.get(plist, "")
        parsed = parse_patterns(raw)
        method_a = find_pattern_matches(parsed, target_seq[plist])
        last_label, method_b = extract_reference_predictions_after(raw)
        out.append(format_results(method_a, method_b, plist, last_label))

    return {"results": out}
